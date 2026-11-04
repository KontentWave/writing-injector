import os
from dataclasses import replace
from pathlib import Path

import httpx
import pytest

from zafo_injector import cli
from zafo_injector.config import AirGapViolationError
from zafo_injector.models import CandidateResult, FrameDocument
from zafo_injector.openrouter_client import OpenRouterError
from zafo_injector.renderer import OutputError, render_outputs
from zafo_injector.slovak_lint import LexiconRules, lint_candidate

WORKSPACE = Path(__file__).resolve().parents[2]


@pytest.mark.parametrize("bom", ["", "\ufeff"])
def test_lossless_merge_preserves_source(
    frame: FrameDocument, rules: LexiconRules, candidate: str, vault: Path, tmp_path: Path, bom: str
) -> None:
    source = tmp_path / "source.md"
    original = (bom + frame.source_text.replace("\n", "\r\n")).encode("utf-8")
    source.write_bytes(original)
    from zafo_injector.parser import parse_frame

    doc = parse_frame(original.decode("utf-8"), source)
    before_stat = source.stat()
    result = CandidateResult(1, candidate, lint_candidate(candidate, doc, rules))
    report, merged = render_outputs(
        doc, [result], vault / "output", vault_dir=vault, workspace_root=WORKSPACE
    )
    assert source.read_bytes() == original
    assert source.stat().st_mtime_ns == before_stat.st_mtime_ns
    assert merged.read_bytes() == (
        doc.source_text[: doc.slot.slot_start_idx]
        + candidate
        + doc.source_text[doc.slot.slot_end_idx :]
    ).encode("utf-8")
    assert merged.parent == report.parent == vault / "output"
    assert "Score: 100" in report.read_text(encoding="utf-8")
    assert not list((vault / "output").glob(".zafo-*"))


def test_render_ranking_ties_and_no_overwrite(
    frame: FrameDocument, rules: LexiconRules, candidate: str, vault: Path
) -> None:
    report = lint_candidate(candidate, frame, rules)
    candidates = [
        CandidateResult(3, "Lower score", replace(report, score=75, passed=False)),
        CandidateResult(2, "Second", report),
        CandidateResult(1, candidate, report),
    ]
    review, merged = render_outputs(
        frame, candidates, vault / "output", vault_dir=vault, workspace_root=WORKSPACE
    )
    text = review.read_text(encoding="utf-8")
    assert text.index("Candidate 1") < text.index("Candidate 2") < text.index("Candidate 3")
    assert candidate in merged.read_text(encoding="utf-8")
    previous = merged.read_bytes()
    with pytest.raises(OutputError):
        render_outputs(
            frame, candidates, vault / "output", vault_dir=vault, workspace_root=WORKSPACE
        )
    assert merged.read_bytes() == previous


def test_renderer_rechecks_drive_boundary(
    frame: FrameDocument, rules: LexiconRules, candidate: str
) -> None:
    result = CandidateResult(1, candidate, lint_candidate(candidate, frame, rules))
    with pytest.raises(AirGapViolationError):
        render_outputs(
            frame,
            [result],
            Path(r"D:\private-vault\output"),
            vault_dir=Path(r"D:\private-vault"),
            workspace_root=WORKSPACE,
        )


def test_cli_dry_run_never_reads_private_files_or_calls_api(
    cli_args: list[str], vault: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    (vault / ".env").write_bytes(b"\xff")
    (vault / "TIER4_ADDON.txt").write_bytes(b"\xff")
    assert cli.main(cli_args + ["--dry-run"]) == 0
    captured = capsys.readouterr()
    assert "Prompt content redacted" in captured.out
    assert "Nasypal" not in captured.out
    assert "synthetic-test-key" not in captured.out + captured.err
    assert not (vault / "output").exists()


def test_mocked_cli_complete(
    cli_args: list[str],
    vault: Path,
    mock_api: list[httpx.Request],
    candidate: str,
    capsys: pytest.CaptureFixture[str],
) -> None:
    assert cli.main(cli_args) == 0
    assert len(mock_api) == 3
    assert len(list((vault / "output").glob("*.md"))) == 2
    assert candidate not in capsys.readouterr().out


def test_strict_all_fail_does_not_write(
    cli_args: list[str],
    vault: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(cli.OpenRouterClient, "generate_candidates", lambda *args: ["zrovna"])
    assert cli.main(cli_args + ["--strict"]) == 5
    assert not (vault / "output").exists()


def test_api_failure_no_drafts(
    cli_args: list[str],
    vault: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fail(*args: object) -> list[str]:
        raise OpenRouterError("Remote generation failed.")

    monkeypatch.setattr(cli.OpenRouterClient, "generate_candidates", fail)
    assert cli.main(cli_args) == 4
    assert not (vault / "output").exists()


def test_cli_airgap_exit_code(cli_args: list[str]) -> None:
    args = cli_args.copy()
    args[args.index("--vault-dir") + 1] = r"D:\private-vault"
    assert cli.main(args + ["--dry-run"]) == 3


def test_lint_only_does_not_need_vault(
    cli_args: list[str], fixtures: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    args = cli_args.copy()
    args[args.index("--vault-dir") + 1] = r"D:\forbidden-but-unused"
    assert cli.main(args + ["--lint-only", str(fixtures / "candidate.txt"), "--strict"]) == 0
    assert "[PASS]" in capsys.readouterr().out


def test_lint_only_strict_failure(cli_args: list[str], tmp_path: Path) -> None:
    text = tmp_path / "short.txt"
    text.write_text("zrovna", encoding="utf-8")
    assert cli.main(cli_args + ["--lint-only", str(text), "--strict"]) == 5


def test_missing_file_is_graceful(cli_args: list[str], capsys: pytest.CaptureFixture[str]) -> None:
    assert cli.main(["does-not-exist.md", *cli_args[1:], "--dry-run"]) == 2
    output = capsys.readouterr()
    assert "[FAIL]" in output.err
    assert "Traceback" not in output.err


def test_print_output_is_opt_in(
    cli_args: list[str],
    mock_api: list[httpx.Request],
    candidate: str,
    capsys: pytest.CaptureFixture[str],
) -> None:
    assert cli.main(cli_args + ["--print-output"]) == 0
    assert candidate in capsys.readouterr().out


def test_invalid_model_parameters_are_graceful(cli_args: list[str]) -> None:
    assert cli.main(cli_args + ["--temp", "nan", "--dry-run"]) == 2


def test_failed_second_publication_rolls_back_first(
    frame: FrameDocument,
    rules: LexiconRules,
    candidate: str,
    vault: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    link = os.link
    calls = 0

    def fail_second(source: Path, target: Path) -> None:
        nonlocal calls
        calls += 1
        if calls == 2:
            raise OSError("Synthetic publication failure.")
        link(source, target)

    monkeypatch.setattr(os, "link", fail_second)
    result = CandidateResult(1, candidate, lint_candidate(candidate, frame, rules))
    with pytest.raises(OSError):
        render_outputs(frame, [result], vault / "output", vault_dir=vault, workspace_root=WORKSPACE)
    assert list((vault / "output").iterdir()) == []


def test_default_source_paths_follow_frame(tmp_path: Path, fixtures: Path, vault: Path) -> None:
    blog = tmp_path / "synthetic-blog"
    (blog / "posts").mkdir(parents=True)
    (blog / "docs").mkdir()
    for name in ("STYLE_SHEET.md", "SLOVAK_LEXICON.md"):
        (blog / "docs" / name).write_bytes((fixtures / name).read_bytes())
    frame_path = blog / "posts" / "post.md"
    frame_path.write_bytes((fixtures / "frame.md").read_bytes())
    assert cli.main([str(frame_path), "--vault-dir", str(vault), "--dry-run"]) == 0
