import argparse
import sys
from pathlib import Path
from typing import TextIO

from .config import AirGapViolationError, ConfigurationError, VaultConfig, vault_child
from .markdown import SourceFormatError
from .model_profiles import MODEL_PROFILES, select_model_profiles, validate_matrix_request
from .models import (
    MAX_CONCURRENT_REQUESTS,
    MAX_MATRIX_REQUESTS,
    MAX_RETRIES,
    ArenaCandidate,
    ArenaRun,
    CandidateResult,
    Language,
    LintReport,
    ModelParams,
    ModelProfile,
)
from .openrouter_client import OpenRouterClient, OpenRouterError
from .parser import SlotParseError, parse_frame
from .prompt_builder import build_messages
from .renderer import QA_LIMITATIONS, OutputError, rank_candidates, render_arena, render_outputs
from .slovak_lint import LexiconRules, lint_candidate

_TRACKS = ("blog", "serial", "dark-romance")


def _utf8(stream: TextIO) -> None:
    reconfigure = getattr(stream, "reconfigure", None)
    if reconfigure is not None:
        reconfigure(encoding="utf-8")


def _positive(value: str) -> int:
    number = int(value)
    if number < 1:
        raise argparse.ArgumentTypeError("must be positive")
    return number


def _default_track_resource(path: Path, docs_dir: Path) -> Path:
    if not path.resolve(strict=True).is_relative_to(docs_dir):
        raise ConfigurationError(
            "Default track resources must remain inside their designated docs directory."
        )
    return path


def _resource_paths(
    post_path: Path,
    *,
    language: Language,
    track: str | None,
    tracks_root: Path | None,
    style_sheet: Path | None,
    lexicon: Path | None,
    require_style: bool,
) -> tuple[Path, Path | None]:
    if track is None:
        if tracks_root is not None:
            raise ConfigurationError("--track and --tracks-root must be supplied together.")
        docs = post_path.resolve().parent.parent / "docs"
        return (
            style_sheet or docs / "STYLE_SHEET.md",
            (lexicon or docs / "SLOVAK_LEXICON.md") if language == "sk" else None,
        )
    if tracks_root is None:
        raise ConfigurationError("--track and --tracks-root must be supplied together.")
    if track not in _TRACKS:
        raise ConfigurationError("Track must be blog, serial, or dark-romance.")
    root = tracks_root.expanduser().resolve(strict=True)
    if not root.is_dir():
        raise ConfigurationError("Track root must be an existing directory.")
    selected = root / track
    if not selected.is_dir():
        raise ConfigurationError("Selected track directory is missing or not a directory.")
    if selected.resolve(strict=True) != selected:
        raise ConfigurationError("Selected track directory must not be redirected by links.")
    if not post_path.resolve(strict=True).is_relative_to(selected):
        raise ConfigurationError("Frame must be inside the explicitly selected track directory.")
    docs = selected / "docs"
    style = style_sheet
    if style is None:
        style = docs / ("STYLE_SHEET_EN.md" if language == "en" else "STYLE_SHEET.md")
        if require_style:
            style = _default_track_resource(style, docs)
    rules_path = None
    if language == "sk":
        rules_path = lexicon or _default_track_resource(
            root / "docs" / "SLOVAK_LEXICON.md", root / "docs"
        )
    return style, rules_path


def _print_lint_issues(
    report: LintReport, *, candidate_index: int | None = None, model_id: str | None = None
) -> None:
    owner = "" if candidate_index is None else f"Candidate {candidate_index}: "
    if model_id is not None:
        owner = f"Model {model_id}, {owner}"
    for issue in report.issues:
        prefix = "FAIL" if issue.severity == "error" else "WARN"
        print(f"[{prefix}] {owner}{issue.rule_id} line={issue.line}")


def _arguments() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Lint Slovak or English slots and write drafts to an isolated local vault. "
        "Live generation sends frame context, style anchors, and the local addon to OpenRouter."
    )
    parser.add_argument("post_path", type=Path)
    parser.add_argument(
        "--language", choices=("sk", "en"), default="sk", help="Output language (default: sk)."
    )
    parser.add_argument(
        "--track",
        choices=_TRACKS,
        help="Explicit track; requires --tracks-root. Never inferred from source paths or prose.",
    )
    parser.add_argument(
        "--tracks-root",
        type=Path,
        help="Explicit root containing track directories; requires --track.",
    )
    parser.add_argument("--candidates", type=_positive, default=3)
    models = parser.add_mutually_exclusive_group()
    models.add_argument("--model", help=f"Single-model ID (default: {ModelParams().model}).")
    models.add_argument(
        "--models",
        metavar="ID,ID,...",
        help="Report-only comparison of 2-3 registered full IDs: " + ", ".join(MODEL_PROFILES),
    )
    parser.add_argument("--temp", type=float, help="Temperature override (default/profile: 0.68).")
    parser.add_argument(
        "--min-p", type=float, help="Min-p override (default/supported profile: 0.06)."
    )
    parser.add_argument("--vault-dir", type=Path)
    parser.add_argument("--style-sheet", type=Path)
    parser.add_argument("--lexicon", type=Path, help="Slovak lexicon; rejected with --language en.")
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
        language: Language = args.language
        if language == "en" and args.lexicon is not None:
            raise ConfigurationError("--lexicon is Slovak-only; omit it with --language en.")
        if args.models is not None and args.lint_only is not None:
            raise ConfigurationError("--models cannot be combined with --lint-only.")
        params = ModelParams(
            model=ModelParams().model if args.model is None else args.model,
            temperature=0.68 if args.temp is None else args.temp,
            min_p=0.06 if args.min_p is None else args.min_p,
        )
        profiles: tuple[ModelProfile, ...] = ()
        if args.models is not None:
            profiles = select_model_profiles(args.models, temperature=args.temp, min_p=args.min_p)
            validate_matrix_request(profiles, args.candidates)
        style_path, lexicon_path = _resource_paths(
            args.post_path,
            language=language,
            track=args.track,
            tracks_root=args.tracks_root,
            style_sheet=args.style_sheet,
            lexicon=args.lexicon,
            require_style=args.lint_only is None,
        )
        doc = parse_frame(
            args.post_path.read_bytes().decode("utf-8"), args.post_path, language=language
        )
        rules: LexiconRules | None = None
        if lexicon_path is not None:
            rules = LexiconRules.from_markdown(lexicon_path)
        if args.track is not None:
            lexicon_source = (
                "none"
                if doc.language == "en"
                else "override"
                if args.lexicon is not None
                else "shared-default"
            )
            print(
                f"[PASS] Track selection: track={args.track}; "
                f"style={'override' if args.style_sheet is not None else 'track-default'}; "
                f"lexicon={lexicon_source}"
            )
        if args.lint_only is not None:
            report = lint_candidate(args.lint_only.read_text(encoding="utf-8-sig"), doc, rules)
            status = "PASS" if report.passed else "FAIL"
            print(
                f"[{status}] words={report.word_count} score={report.score}; "
                f"language={doc.language}"
            )
            _print_lint_issues(report)
            return 5 if args.strict and not report.passed else 0
        config = VaultConfig.load(args.vault_dir, workspace, require_api_key=not args.dry_run)
        if args.dry_run:
            messages = build_messages(doc, style_path, None)
            print(
                f"[PASS] POV={doc.pov}; words={doc.slot.min_words}-{doc.slot.max_words}; "
                f"context={len(doc.context_before)}/{len(doc.context_after)} paragraphs; "
                f"language={doc.language}"
            )
            readiness = (
                "Lexicon ready"
                if doc.language == "sk"
                else "English structural QA ready (no lexicon or grammar checks)"
            )
            print(f"[PASS] {readiness}; prompt roles=" + "/".join(m["role"] for m in messages))
            if profiles:
                total = len(profiles) * args.candidates
                print(
                    f"[PASS] Report-only arena: models={len(profiles)}; "
                    f"candidates/model={args.candidates}; "
                    f"initial requests={total}/{MAX_MATRIX_REQUESTS}; "
                    f"HTTP attempt budget={total * (MAX_RETRIES + 1)}; "
                    f"global concurrency cap={MAX_CONCURRENT_REQUESTS}"
                )
                for profile in profiles:
                    settings = "; ".join(
                        f"{name}={value}" for name, value in profile.sampling_parameters().items()
                    )
                    print(
                        f"[PASS] Model {profile.model_id}: {settings}; "
                        f"omitted={','.join(profile.omitted_parameters) or 'none'}; "
                        "require_parameters=True; quantizations=bf16/fp16/fp8"
                    )
                print(f"[WARN] {QA_LIMITATIONS}")
            print(
                "[PASS] Prompt content redacted; addon and credentials not read; no API or writes."
            )
            return 0
        addon = vault_child(config.vault_dir, "TIER4_ADDON.txt", workspace)
        messages = build_messages(doc, style_path, addon if addon.exists() else None)
        if not addon.exists():
            print("[WARN] No local addon found; proceeding without one.", file=sys.stderr)
        if profiles:
            responses = OpenRouterClient(config.api_key).generate_matrix(
                messages, profiles, args.candidates
            )
            run = ArenaRun(
                profiles,
                args.candidates,
                tuple(
                    ArenaCandidate(
                        response,
                        lint_candidate(response.text, doc, rules)
                        if response.text is not None
                        else None,
                    )
                    for response in responses
                ),
                strict=args.strict,
            )
            print(f"[WARN] {QA_LIMITATIONS}")
            print("| Model | Requested | API failed | Hard passes | Warnings |")
            print("|---|---|---|---|---|")
            for profile in profiles:
                candidates = run.for_model(profile.model_id)
                api_failures = sum(
                    candidate.response.failure is not None for candidate in candidates
                )
                warnings = sum(
                    issue.severity == "warn"
                    for candidate in candidates
                    if candidate.report is not None
                    for issue in candidate.report.issues
                )
                print(
                    f"| {profile.model_id} | {args.candidates} | {api_failures} | "
                    f"{run.hard_pass_count(profile.model_id)} | {warnings} |"
                )
                for arena_candidate in candidates:
                    response, qa_report = arena_candidate.response, arena_candidate.report
                    if response.failure is not None:
                        print(
                            f"[FAIL] {response.candidate_id}: {response.failure.message} "
                            f"attempts={response.attempts}"
                        )
                    elif qa_report is not None:
                        status = "PASS" if qa_report.passed else "FAIL"
                        print(
                            f"[{status}] {response.candidate_id}: score={qa_report.score}; "
                            f"words={qa_report.word_count}; "
                            f"target={doc.slot.min_words}-{doc.slot.max_words}; "
                            f"paragraphs={qa_report.paragraph_count}; language={doc.language}; "
                            f"attempts={response.attempts}"
                        )
                        _print_lint_issues(
                            qa_report, candidate_index=response.index, model_id=response.model_id
                        )
            if run.status == "api_failed":
                print(
                    "[FAIL] Arena has API failures; publishing explicitly failed reports.",
                    file=sys.stderr,
                )
            elif run.status == "strict_lint_failed":
                print(
                    "[FAIL] At least one model has no hard-passing candidates; "
                    "publishing explicitly strict-failed reports.",
                    file=sys.stderr,
                )
            paths = render_arena(
                doc, run, config.output_dir, vault_dir=config.vault_dir, workspace_root=workspace
            )
            status = "FAIL" if run.exit_code else "PASS"
            for path in paths:
                print(f"[{status}] Arena report published: {path}; status={run.status}")
            print(f"[{status}] Report-only arena; no winner or merged draft; exit={run.exit_code}")
            if args.print_output:
                for arena_candidate in run.candidates:
                    if arena_candidate.response.text is not None:
                        print(
                            f"\n{arena_candidate.response.candidate_id}\n"
                            f"{arena_candidate.response.text}"
                        )
            return run.exit_code
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
                f"score={candidate.report.score}; words={candidate.report.word_count}; "
                f"target={doc.slot.min_words}-{doc.slot.max_words}; "
                f"paragraphs={candidate.report.paragraph_count}; language={doc.language}"
            )
            _print_lint_issues(candidate.report, candidate_index=candidate.index)
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
