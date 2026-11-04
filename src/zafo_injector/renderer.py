import os
import tempfile
from pathlib import Path

from .config import AirGapViolationError, validate_output_dir, validate_storage_path
from .models import CandidateResult, FrameDocument


class OutputError(ValueError):
    """Output cannot safely be published."""


def rank_candidates(candidates: list[CandidateResult]) -> list[CandidateResult]:
    return sorted(candidates, key=lambda candidate: (-candidate.report.score, candidate.index))


def _cell(value: str) -> str:
    return value.replace("|", r"\|").replace("\r", " ").replace("\n", " ")


def render_outputs(
    doc: FrameDocument,
    ranked_candidates: list[CandidateResult],
    output_dir: Path,
    *,
    vault_dir: Path,
    workspace_root: Path,
) -> tuple[Path, Path]:
    if not ranked_candidates:
        raise OutputError("There are no candidates to render.")
    ranked = rank_candidates(ranked_candidates)
    start, end = doc.slot.slot_start_idx, doc.slot.slot_end_idx
    if doc.source_text[start:end] != doc.slot.raw_comment:
        raise OutputError("Slot offsets no longer match the original frame.")
    output = validate_output_dir(output_dir, vault_dir, workspace_root)
    output.mkdir(parents=True, exist_ok=True)
    targets = (
        output / f"{doc.source_path.stem}.candidates.md",
        output / f"{doc.source_path.stem}.merged.md",
    )
    for target in targets:
        validate_storage_path(target, workspace_root)
        if target.exists() or target.is_symlink():
            raise OutputError("Output already exists; move existing drafts before running again.")
    parts = ["# Candidate review\n"]
    for candidate in ranked:
        report = candidate.report
        status = "PASS" if report.passed else "FAIL"
        parts.append(
            f"\n## Candidate {candidate.index} [{status}]\n\n"
            f"Score: {report.score}; words: {report.word_count}; "
            f"paragraphs: {report.paragraph_count}\n\n{candidate.text}\n\n"
            "| Rule | Severity | Line | Match | Suggestion |\n"
            "|---|---|---|---|---|\n"
        )
        for issue in report.issues:
            parts.append(
                f"| {issue.rule_id} | {issue.severity} | {issue.line} | "
                f"{_cell(issue.match)} | {_cell(issue.suggestion)} |\n"
            )
        if not report.issues:
            parts.append("| - | PASS | - | - | No lint issues |\n")
    merged = doc.source_text[:start] + ranked[0].text + doc.source_text[end:]
    staged: list[Path] = []
    published: list[Path] = []
    try:
        for content in ("".join(parts), merged):
            validate_output_dir(output, vault_dir, workspace_root)
            with tempfile.NamedTemporaryFile(
                mode="w",
                encoding="utf-8",
                newline="",
                dir=output,
                prefix=".zafo-",
                suffix=".tmp",
                delete=False,
            ) as handle:
                staged.append(Path(handle.name))
                handle.write(content)
        for temporary, target in zip(staged, targets, strict=True):
            validate_output_dir(output, vault_dir, workspace_root)
            if validate_storage_path(target, workspace_root) != target:
                raise AirGapViolationError("Output file was redirected by a link.")
            # Atomic publication without replacing another run's files.
            os.link(temporary, target)
            published.append(target)
    except (OSError, ValueError):
        for target in published:
            target.unlink()
        raise
    finally:
        for temporary in staged:
            temporary.unlink(missing_ok=True)
    return targets
