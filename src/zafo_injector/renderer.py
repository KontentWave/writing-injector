import json
import os
import tempfile
from pathlib import Path

from .config import AirGapViolationError, validate_output_dir, validate_storage_path
from .model_profiles import validate_matrix_request
from .models import (
    MAX_CONCURRENT_REQUESTS,
    MAX_MATRIX_REQUESTS,
    MAX_RETRIES,
    REQUEST_TIMEOUT_SECONDS,
    ArenaCandidate,
    ArenaRun,
    CandidateResult,
    FrameDocument,
)

QA_LIMITATIONS = (
    "Deterministic QA scores measure structure and Slovak-only configured heuristics, "
    "not grammar, prose quality, output language, scene compliance, or safety certification."
)


class OutputError(ValueError):
    """Output cannot safely be published."""


def rank_candidates(candidates: list[CandidateResult]) -> list[CandidateResult]:
    return sorted(candidates, key=lambda candidate: (-candidate.report.score, candidate.index))


def _cell(value: str) -> str:
    return value.replace("|", r"\|").replace("\r", " ").replace("\n", " ")


def _candidate_review(candidate: CandidateResult, heading: str) -> str:
    report = candidate.report
    status = "PASS" if report.passed else "FAIL"
    parts = [
        f"\n{heading} [{status}]\n\n"
        f"Score: {report.score}; words: {report.word_count}; "
        f"paragraphs: {report.paragraph_count}\n\n{candidate.text}\n\n"
        "| Rule | Severity | Line | Match | Suggestion |\n"
        "|---|---|---|---|---|\n"
    ]
    for issue in report.issues:
        parts.append(
            f"| {issue.rule_id} | {issue.severity} | {issue.line} | "
            f"{_cell(issue.match)} | {_cell(issue.suggestion)} |\n"
        )
    if not report.issues:
        parts.append("| - | PASS | - | - | No lint issues |\n")
    return "".join(parts)


def _slot_bounds(doc: FrameDocument) -> tuple[int, int]:
    start, end = doc.slot.slot_start_idx, doc.slot.slot_end_idx
    if doc.source_text[start:end] != doc.slot.raw_comment:
        raise OutputError("Slot offsets no longer match the original frame.")
    return start, end


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
    start, end = _slot_bounds(doc)
    parts = ["# Candidate review\n"]
    for candidate in ranked:
        parts.append(_candidate_review(candidate, f"## Candidate {candidate.index}"))
    merged = doc.source_text[:start] + ranked[0].text + doc.source_text[end:]
    return _publish_pair(
        ("".join(parts), merged),
        (f"{doc.source_path.stem}.candidates.md", f"{doc.source_path.stem}.merged.md"),
        output_dir,
        vault_dir=vault_dir,
        workspace_root=workspace_root,
    )


def _candidate_metadata(candidate: ArenaCandidate) -> dict[str, object]:
    response, report = candidate.response, candidate.report
    failure = response.failure
    return {
        "candidate_id": response.candidate_id,
        "index": response.index,
        "status": "api_failed"
        if failure is not None
        else "hard_pass"
        if report and report.passed
        else "lint_failed",
        "attempts": response.attempts,
        "score": report.score if report is not None else None,
        "word_count": report.word_count if report is not None else None,
        "paragraph_count": report.paragraph_count if report is not None else None,
        "hard_pass": report.passed if report is not None else None,
        "hard_error_count": sum(issue.severity == "error" for issue in report.issues)
        if report is not None
        else None,
        "warning_count": sum(issue.severity == "warn" for issue in report.issues)
        if report is not None
        else None,
        "issues": [
            {"rule_id": issue.rule_id, "severity": issue.severity, "line": issue.line}
            for issue in report.issues
        ]
        if report is not None
        else None,
        "failure": {
            "code": failure.code,
            "http_status": failure.http_status,
            "message": failure.message,
        }
        if failure is not None
        else None,
    }


def _model_scorecard(run: ArenaRun, model_id: str) -> dict[str, int | float]:
    candidates = run.for_model(model_id)
    api_failures = sum(candidate.response.failure is not None for candidate in candidates)
    reports = [candidate.report for candidate in candidates if candidate.report is not None]
    hard_passes = run.hard_pass_count(model_id)
    return {
        "requested": run.candidates_per_model,
        "succeeded": len(reports),
        "api_failed": api_failures,
        "hard_pass_count": hard_passes,
        "hard_pass_rate_requested": hard_passes / run.candidates_per_model,
        "hard_error_count": sum(
            issue.severity == "error" for report in reports for issue in report.issues
        ),
        "warning_count": sum(
            issue.severity == "warn" for report in reports for issue in report.issues
        ),
    }


def _arena_metadata(doc: FrameDocument, run: ArenaRun) -> dict[str, object]:
    models: list[dict[str, object]] = []
    for profile in run.profiles:
        scorecard = _model_scorecard(run, profile.model_id)
        status = (
            "api_failed"
            if scorecard["api_failed"]
            else "lint_failed"
            if not scorecard["hard_pass_count"]
            else "lint_findings"
            if scorecard["hard_error_count"]
            else "hard_pass"
        )
        models.append(
            {
                "model_id": profile.model_id,
                "status": status,
                "sampling": profile.sampling_parameters(),
                "omitted_sampling_parameters": list(profile.omitted_parameters),
                "provider": profile.provider_settings(),
                "scorecard": scorecard,
                "candidates": [
                    _candidate_metadata(candidate) for candidate in run.for_model(profile.model_id)
                ],
            }
        )
    return {
        "schema_version": 1,
        "mode": "arena",
        "status": run.status,
        "exit_code": run.exit_code,
        "strict": run.strict,
        "language": doc.language,
        "pov": doc.pov,
        "bounds": {
            "min_words": doc.slot.min_words,
            "max_words": doc.slot.max_words,
            "min_paragraphs": 2,
            "max_paragraphs": 4,
        },
        "qa": {"score_formula": "100 - 25 * errors - 5 * warnings", "limitations": QA_LIMITATIONS},
        "execution": {
            "candidates_per_model": run.candidates_per_model,
            "initial_requests": run.initial_requests,
            "initial_request_limit": MAX_MATRIX_REQUESTS,
            "http_attempts": run.http_attempts,
            "http_attempt_budget": run.initial_requests * (MAX_RETRIES + 1),
            "concurrency_cap": MAX_CONCURRENT_REQUESTS,
            "timeout_seconds": REQUEST_TIMEOUT_SECONDS,
            "max_retries": MAX_RETRIES,
            "retry_backoff_seconds": [0.5, 1.0],
        },
        "models": models,
    }


def render_arena(
    doc: FrameDocument,
    run: ArenaRun,
    output_dir: Path,
    *,
    vault_dir: Path,
    workspace_root: Path,
) -> tuple[Path, Path]:
    validate_matrix_request(run.profiles, run.candidates_per_model)
    _slot_bounds(doc)
    metadata = _arena_metadata(doc, run)
    parts = [
        "# Multi-model comparison arena\n\n",
        f"Status: {run.status}; exit code: {run.exit_code}; strict: {run.strict}\n\n",
        f"Language: {doc.language}; POV: {doc.pov}; "
        f"word bounds: {doc.slot.min_words}-{doc.slot.max_words}; paragraphs: 2-4\n\n",
        f"{QA_LIMITATIONS}\n\n",
        "Report-only: no winner selected and no merged draft. Sampling differences are recorded; "
        "this is not necessarily a controlled model-only experiment.\n\n",
        f"Initial requests: {run.initial_requests}/{MAX_MATRIX_REQUESTS}; "
        f"HTTP attempts: {run.http_attempts}/{run.initial_requests * (MAX_RETRIES + 1)}; "
        f"global concurrency cap: {MAX_CONCURRENT_REQUESTS}; timeout: {REQUEST_TIMEOUT_SECONDS}s; "
        f"max retries: {MAX_RETRIES}\n\n",
        "Hard-pass rates use all requested candidates, including API failures, "
        "as the denominator.\n\n",
        "| Model | Requested | Succeeded | API failed | Hard passes | "
        "Hard-pass rate | Warnings |\n",
        "|---|---|---|---|---|---|---|\n",
    ]
    for profile in run.profiles:
        scorecard = _model_scorecard(run, profile.model_id)
        parts.append(
            f"| {profile.model_id} | {scorecard['requested']} | {scorecard['succeeded']} | "
            f"{scorecard['api_failed']} | {scorecard['hard_pass_count']} | "
            f"{scorecard['hard_pass_rate_requested']:.1%} | {scorecard['warning_count']} |\n"
        )
    for profile in run.profiles:
        parts.append(
            f"\n## Model {profile.model_id}\n\n"
            f"Sampling: {json.dumps(profile.sampling_parameters(), sort_keys=True)}\n\n"
            "Omitted unsupported sampling parameters: "
            f"{', '.join(profile.omitted_parameters) or 'none'}\n\n"
            f"Provider: {json.dumps(profile.provider_settings(), sort_keys=True)}\n"
        )
        candidates = run.for_model(profile.model_id)
        successes = rank_candidates(
            [
                CandidateResult(candidate.response.index, candidate.response.text, candidate.report)
                for candidate in candidates
                if candidate.response.text is not None and candidate.report is not None
            ]
        )
        by_index = {candidate.response.index: candidate.response for candidate in candidates}
        for result in successes:
            response = by_index[result.index]
            parts.append(f"\nAttempts for {response.candidate_id}: {response.attempts}\n")
            parts.append(_candidate_review(result, f"### {response.candidate_id}"))
        for candidate in candidates:
            response = candidate.response
            if response.failure is not None:
                parts.append(
                    f"\n### {response.candidate_id} [API FAIL]\n\n"
                    f"Attempts: {response.attempts}; failure: {response.failure.code}\n\n"
                    f"{response.failure.message} No candidate text or QA metrics are available.\n"
                )
    return _publish_pair(
        ("".join(parts), json.dumps(metadata, indent=2, sort_keys=True) + "\n"),
        (f"{doc.source_path.stem}.arena.md", f"{doc.source_path.stem}.arena.json"),
        output_dir,
        vault_dir=vault_dir,
        workspace_root=workspace_root,
    )


def _publish_pair(
    contents: tuple[str, str],
    filenames: tuple[str, str],
    output_dir: Path,
    *,
    vault_dir: Path,
    workspace_root: Path,
) -> tuple[Path, Path]:
    output = validate_output_dir(output_dir, vault_dir, workspace_root)
    output.mkdir(parents=True, exist_ok=True)
    targets = (output / filenames[0], output / filenames[1])
    for target in targets:
        validate_storage_path(target, workspace_root)
        if target.exists() or target.is_symlink():
            raise OutputError("Output already exists; move existing drafts before running again.")
    staged: list[Path] = []
    published: list[Path] = []
    try:
        for content in contents:
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
