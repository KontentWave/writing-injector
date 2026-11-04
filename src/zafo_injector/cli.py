import argparse
import sys
from pathlib import Path
from typing import TextIO

from .config import AirGapViolationError, ConfigurationError, VaultConfig, vault_child
from .markdown import SourceFormatError
from .models import CandidateResult, ModelParams
from .openrouter_client import OpenRouterClient, OpenRouterError
from .parser import SlotParseError, parse_frame
from .prompt_builder import build_messages
from .renderer import OutputError, rank_candidates, render_outputs
from .slovak_lint import LexiconRules, lint_candidate


def _utf8(stream: TextIO) -> None:
    reconfigure = getattr(stream, "reconfigure", None)
    if reconfigure is not None:
        reconfigure(encoding="utf-8")


def _positive(value: str) -> int:
    number = int(value)
    if number < 1:
        raise argparse.ArgumentTypeError("must be positive")
    return number


def _arguments() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Lint Slovak slots and write drafts to an isolated local vault. "
        "Live generation sends frame context, style anchors, and the local addon to OpenRouter."
    )
    parser.add_argument("post_path", type=Path)
    parser.add_argument("--candidates", type=_positive, default=3)
    parser.add_argument("--model", default=ModelParams().model)
    parser.add_argument("--temp", type=float, default=0.68)
    parser.add_argument("--min-p", type=float, default=0.06)
    parser.add_argument("--vault-dir", type=Path)
    parser.add_argument("--style-sheet", type=Path)
    parser.add_argument("--lexicon", type=Path)
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--dry-run", action="store_true")
    mode.add_argument("--lint-only", type=Path, metavar="FILE")
    parser.add_argument("--strict", action="store_true")
    parser.add_argument("--print-output", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    _utf8(sys.stdout)
    _utf8(sys.stderr)
    args = _arguments().parse_args(argv)
    workspace = Path(__file__).resolve().parents[2]
    try:
        params = ModelParams(model=args.model, temperature=args.temp, min_p=args.min_p)
        doc = parse_frame(args.post_path.read_bytes().decode("utf-8"), args.post_path)
        source_docs = args.post_path.resolve().parent.parent / "docs"
        style_path = args.style_sheet or source_docs / "STYLE_SHEET.md"
        lexicon_path = args.lexicon or source_docs / "SLOVAK_LEXICON.md"
        rules = LexiconRules.from_markdown(lexicon_path)
        if args.lint_only is not None:
            report = lint_candidate(args.lint_only.read_text(encoding="utf-8-sig"), doc, rules)
            status = "PASS" if report.passed else "FAIL"
            print(f"[{status}] words={report.word_count} score={report.score}")
            for issue in report.issues:
                prefix = "FAIL" if issue.severity == "error" else "WARN"
                print(f"[{prefix}] {issue.rule_id} line={issue.line}")
            return 5 if args.strict and not report.passed else 0
        config = VaultConfig.load(args.vault_dir, workspace, require_api_key=not args.dry_run)
        if args.dry_run:
            messages = build_messages(doc, style_path, None)
            print(
                f"[PASS] POV={doc.pov}; words={doc.slot.min_words}-{doc.slot.max_words}; "
                f"context={len(doc.context_before)}/{len(doc.context_after)} paragraphs"
            )
            print("[PASS] Lexicon ready; prompt roles=" + "/".join(m["role"] for m in messages))
            print(
                "[PASS] Prompt content redacted; addon and credentials not read; no API or writes."
            )
            return 0
        addon = vault_child(config.vault_dir, "TIER4_ADDON.txt", workspace)
        messages = build_messages(doc, style_path, addon if addon.exists() else None)
        if not addon.exists():
            print("[WARN] No local addon found; proceeding without one.", file=sys.stderr)
        texts = OpenRouterClient(config.api_key).generate_candidates(
            messages, params, args.candidates
        )
        ranked = rank_candidates(
            [
                CandidateResult(index, text, lint_candidate(text, doc, rules))
                for index, text in enumerate(texts, 1)
            ]
        )
        for candidate in ranked:
            status = "PASS" if candidate.report.passed else "FAIL"
            print(
                f"[{status}] Candidate {candidate.index}: "
                f"score={candidate.report.score}; words={candidate.report.word_count}"
            )
        if args.strict and not any(candidate.report.passed for candidate in ranked):
            print(
                "[FAIL] All candidates failed hard lint rules; no output written.", file=sys.stderr
            )
            return 5
        if not ranked[0].report.passed:
            print(
                "[WARN] Selected draft has hard lint issues; manual review required.",
                file=sys.stderr,
            )
        paths = render_outputs(
            doc, ranked, config.output_dir, vault_dir=config.vault_dir, workspace_root=workspace
        )
        for path in paths:
            print(f"[PASS] Wrote {path}")
        if args.print_output:
            print(ranked[0].text)
        return 0
    except AirGapViolationError as exc:
        print(f"[FAIL] {exc}", file=sys.stderr)
        return 3
    except OpenRouterError as exc:
        print(f"[FAIL] {exc}", file=sys.stderr)
        return 4
    except (ConfigurationError, SlotParseError, SourceFormatError, OutputError, ValueError) as exc:
        print(f"[FAIL] {exc}", file=sys.stderr)
        return 2
    except OSError:
        print(
            "[FAIL] File access failed; check input files and vault permissions.", file=sys.stderr
        )
        return 2
