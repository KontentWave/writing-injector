import hashlib
import json
import os
import subprocess
import sys
from pathlib import Path

import httpx
import pytest

from zafo_injector import cli
from zafo_injector.models import Language
from zafo_injector.parser import parse_frame
from zafo_injector.slovak_lint import LexiconRules

TRACKS = ("blog", "serial", "dark-romance")
ROSTER = "anthracite-org/magnum-v4-72b,deepseek/deepseek-chat-v3-0324,sao10k/l3.1-euryale-70b"
ARENA_KEYS = {
    "schema_version",
    "mode",
    "status",
    "exit_code",
    "strict",
    "language",
    "pov",
    "bounds",
    "qa",
    "execution",
    "models",
}


def _source(root: Path, track: str, language: Language) -> Path:
    directory = "posts" if track == "blog" else "episodes"
    name = "frame_en.md" if language == "en" else "frame.md"
    return root / track / directory / "nested" / name


def _args(root: Path, track: str, language: Language, vault: Path) -> list[str]:
    return [
        str(_source(root, track, language)),
        "--track",
        track,
        "--tracks-root",
        str(root),
        "--language",
        language,
        "--vault-dir",
        str(vault),
    ]


def _snapshot(root: Path) -> dict[Path, tuple[bytes, int]]:
    return {
        path.relative_to(root): (
            hashlib.sha256(path.read_bytes()).digest(),
            path.stat().st_mtime_ns,
        )
        for path in root.rglob("*")
        if path.is_file()
    }


def _blocked(*args: object, **kwargs: object) -> None:
    raise AssertionError("This mode must not access these files, the vault, or the network.")


@pytest.fixture
def candidate(language: Language, fixtures: Path) -> str:
    name = "candidate_en.txt" if language == "en" else "candidate.txt"
    return (fixtures / name).read_text(encoding="utf-8").strip()


@pytest.mark.parametrize("track", TRACKS)
@pytest.mark.parametrize("language", ["sk", "en"])
def test_track_dry_run_selects_only_effective_resources_without_writes(
    track: str,
    language: Language,
    tracks_root: Path,
    vault: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    (vault / ".env").write_bytes(b"\xff")
    (vault / "TIER4_ADDON.txt").write_bytes(b"\xff")
    before = _snapshot(tracks_root), _snapshot(vault)
    reads: list[Path] = []
    original_read = Path.read_text

    def read_text(path: Path, encoding: str | None = None, errors: str | None = None) -> str:
        assert path.name not in (".env", "TIER4_ADDON.txt")
        reads.append(path)
        return original_read(path, encoding=encoding, errors=errors)

    monkeypatch.setattr(Path, "read_text", read_text)
    monkeypatch.setattr(cli, "OpenRouterClient", _blocked)
    if language == "en":
        monkeypatch.setattr(LexiconRules, "from_markdown", _blocked)
    assert (
        cli.main(_args(tracks_root, track, language, vault) + ["--dry-run", "--print-output"]) == 0
    )
    style_name = "STYLE_SHEET_EN.md" if language == "en" else "STYLE_SHEET.md"
    expected = [tracks_root / "docs" / "SLOVAK_LEXICON.md"] if language == "sk" else []
    assert reads == [*expected, tracks_root / track / "docs" / style_name]
    captured = capsys.readouterr()
    output = captured.out + captured.err
    assert f"track={track}" in output and f"language={language}" in output
    assert "style=track-default" in output
    assert f"lexicon={'shared-default' if language == 'sk' else 'none'}" in output
    assert "SYNTHETIC_STYLE" not in output
    assert str(tracks_root) not in output and str(vault) not in output
    assert (_snapshot(tracks_root), _snapshot(vault)) == before


@pytest.mark.parametrize("flag", ["--track", "--tracks-root"])
def test_track_and_root_must_be_paired_before_reads(
    flag: str, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setattr(Path, "read_bytes", _blocked)
    monkeypatch.setattr(Path, "read_text", _blocked)
    monkeypatch.setattr(cli.VaultConfig, "load", _blocked)
    value = "blog" if flag == "--track" else "missing-synthetic-root"
    assert cli.main(["missing-frame.md", flag, value, "--dry-run"]) == 2
    assert "--track and --tracks-root" in capsys.readouterr().err


@pytest.mark.parametrize("track", ["BLOG", "unknown", ""])
def test_invalid_track_rejects_before_reads(track: str, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(Path, "read_bytes", _blocked)
    monkeypatch.setattr(Path, "read_text", _blocked)
    with pytest.raises(SystemExit) as exc:
        cli.main(
            ["missing-frame.md", "--track", track, "--tracks-root", "missing-root", "--dry-run"]
        )
    assert exc.value.code == 2


@pytest.mark.parametrize(
    "kind", ["missing-root", "file-root", "missing-track", "other-track", "outside"]
)
def test_invalid_track_layout_rejects_before_source_or_vault_reads(
    kind: str,
    tracks_root: Path,
    tmp_path: Path,
    vault: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    args = _args(tracks_root, "blog", "en", vault)
    if kind in ("missing-root", "file-root", "missing-track"):
        root = tmp_path / kind
        if kind == "file-root":
            root.write_text("Synthetic non-directory.", encoding="utf-8")
        elif kind == "missing-track":
            root.mkdir()
        args[args.index("--tracks-root") + 1] = str(root)
    elif kind == "other-track":
        args[0] = str(_source(tracks_root, "serial", "en"))
    else:
        args[0] = str(tmp_path / "outside.md")
    monkeypatch.setattr(Path, "read_bytes", _blocked)
    monkeypatch.setattr(Path, "read_text", _blocked)
    monkeypatch.setattr(cli.VaultConfig, "load", _blocked)
    assert cli.main(args + ["--dry-run"]) == 2
    assert "[FAIL]" in capsys.readouterr().err
    assert not (vault / "output").exists()


@pytest.mark.parametrize(
    ("language", "style_override", "lexicon_override"),
    [("sk", True, False), ("sk", False, True), ("sk", True, True), ("en", True, False)],
)
def test_explicit_overrides_replace_missing_defaults_without_fallback(
    language: Language,
    style_override: bool,
    lexicon_override: bool,
    tracks_root: Path,
    fixtures: Path,
    tmp_path: Path,
    vault: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    args = _args(tracks_root, "serial", language, vault)
    shared = tmp_path / "explicit-shared-resources"
    shared.mkdir()
    if style_override:
        name = "STYLE_SHEET_EN.md" if language == "en" else "STYLE_SHEET.md"
        style = shared / name
        style.write_bytes((fixtures / name).read_bytes())
        (tracks_root / "serial" / "docs" / name).unlink()
        args += ["--style-sheet", str(style)]
    if lexicon_override:
        lexicon = shared / "SLOVAK_LEXICON.md"
        lexicon.write_bytes((fixtures / lexicon.name).read_bytes())
        (tracks_root / "docs" / lexicon.name).unlink()
        args += ["--lexicon", str(lexicon)]
    before = _snapshot(tracks_root), _snapshot(shared)
    assert cli.main(args + ["--dry-run"]) == 0
    output = capsys.readouterr().out
    assert f"style={'override' if style_override else 'track-default'}" in output
    expected_lexicon = (
        "none" if language == "en" else "override" if lexicon_override else "shared-default"
    )
    assert f"lexicon={expected_lexicon}" in output
    assert (_snapshot(tracks_root), _snapshot(shared)) == before
    assert not (vault / "output").exists()


@pytest.mark.parametrize(
    ("language", "resource"), [("sk", "style"), ("sk", "lexicon"), ("en", "style")]
)
@pytest.mark.parametrize("override", [False, True])
@pytest.mark.parametrize("malformed", [False, True])
def test_missing_or_malformed_effective_resources_fail_without_fallback(
    language: Language,
    resource: str,
    override: bool,
    malformed: bool,
    tracks_root: Path,
    tmp_path: Path,
    vault: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    args = _args(tracks_root, "dark-romance", language, vault)
    if resource == "style":
        name = "STYLE_SHEET_EN.md" if language == "en" else "STYLE_SHEET.md"
        path = tracks_root / "dark-romance" / "docs" / name
        flag = "--style-sheet"
    else:
        path = tracks_root / "docs" / "SLOVAK_LEXICON.md"
        flag = "--lexicon"
    if override:
        path = tmp_path / "broken-override.md"
        args += [flag, str(path)]
    else:
        path.unlink()
    if malformed:
        path.write_text("## 1. Sample\nSynthetic incomplete resource.\n", encoding="utf-8")
    monkeypatch.setattr(cli, "OpenRouterClient", _blocked)
    assert cli.main(args + ["--dry-run"]) == 2
    output = capsys.readouterr()
    assert "[FAIL]" in output.err
    assert "Synthetic incomplete resource" not in output.out + output.err
    assert not (vault / "output").exists()


@pytest.mark.parametrize("track", TRACKS)
@pytest.mark.parametrize("language", ["sk", "en"])
def test_track_lint_only_ignores_styles_and_never_accesses_vault(
    track: str,
    language: Language,
    tracks_root: Path,
    fixtures: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    for name in ("STYLE_SHEET.md", "STYLE_SHEET_EN.md"):
        (tracks_root / track / "docs" / name).unlink()
    args = _args(tracks_root, track, language, Path(r"D:\forbidden-but-unused"))
    name = "candidate_en.txt" if language == "en" else "candidate.txt"
    args += ["--lint-only", str(fixtures / name), "--strict"]
    monkeypatch.setattr(cli.VaultConfig, "load", _blocked)
    monkeypatch.setattr(cli, "OpenRouterClient", _blocked)
    if language == "en":
        monkeypatch.setattr(LexiconRules, "from_markdown", _blocked)
    assert cli.main(args) == 0
    assert cli.main(args + ["--style-sheet", "missing-unused-style.md"]) == 0
    output = capsys.readouterr().out
    assert f"track={track}" in output and "score=100" in output
    assert "SYNTHETIC_STYLE" not in output


@pytest.mark.parametrize("mode", ["dry", "lint", "legacy", "arena-dry", "arena"])
def test_track_english_lexicon_rejects_before_reads(
    mode: str, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    args = _args(Path("missing-root"), "blog", "en", Path("unused-vault"))
    args += ["--lexicon", "missing-lexicon.md"]
    if mode in ("dry", "arena-dry"):
        args += ["--dry-run"]
    elif mode == "lint":
        args += ["--lint-only", "missing-candidate.txt"]
    if mode.startswith("arena"):
        args += ["--models", ROSTER]
    monkeypatch.setattr(Path, "read_bytes", _blocked)
    monkeypatch.setattr(Path, "read_text", _blocked)
    monkeypatch.setattr(cli.VaultConfig, "load", _blocked)
    assert cli.main(args) == 2
    assert "--lexicon is Slovak-only" in capsys.readouterr().err


@pytest.mark.parametrize("mode", ["legacy", "arena"])
@pytest.mark.parametrize("track", TRACKS)
@pytest.mark.parametrize("language", ["sk", "en"])
def test_track_mocked_generation_preserves_prompts_reports_and_sources(
    mode: str,
    track: str,
    language: Language,
    tracks_root: Path,
    vault: Path,
    candidate: str,
    mock_api: list[httpx.Request],
    capsys: pytest.CaptureFixture[str],
) -> None:
    args = _args(tracks_root, track, language, vault) + ["--candidates", "1", "--strict"]
    args += ["--models", ROSTER] if mode == "arena" else ["--model", "synthetic/legacy-model"]
    source = _source(tracks_root, track, language)
    original = source.read_bytes()
    before = _snapshot(tracks_root)
    assert cli.main(args) == 0
    assert len(mock_api) == (3 if mode == "arena" else 1)
    payloads = [json.loads(request.content) for request in mock_api]
    assert all(payload["messages"] == payloads[0]["messages"] for payload in payloads)
    system = payloads[0]["messages"][0]["content"]
    assert f"SYNTHETIC_STYLE_{track}_{language}" in system
    assert f"Write only in {'English' if language == 'en' else 'Slovak'}" in system
    assert "Word bounds: 20-80 words, inclusive." in system
    output = vault / "output"
    stem = source.stem
    if mode == "arena":
        assert sorted(path.name for path in output.iterdir()) == [
            f"{stem}.arena.json",
            f"{stem}.arena.md",
        ]
        metadata = json.loads((output / f"{stem}.arena.json").read_text(encoding="utf-8"))
        assert set(metadata) == ARENA_KEYS and metadata["schema_version"] == 1
        assert metadata["status"] == "completed" and metadata["exit_code"] == 0
        assert metadata["execution"]["http_attempts"] == 3
        assert metadata["execution"]["http_attempt_budget"] == 9
        assert metadata["execution"]["concurrency_cap"] == 3
        assert [model["model_id"] for model in metadata["models"]] == ROSTER.split(",")
    else:
        assert payloads[0]["model"] == "synthetic/legacy-model"
        assert sorted(path.name for path in output.iterdir()) == [
            f"{stem}.candidates.md",
            f"{stem}.merged.md",
        ]
        doc = parse_frame(original.decode("utf-8"), source, language=language)
        assert (output / f"{stem}.merged.md").read_bytes() == (
            doc.source_text[: doc.slot.slot_start_idx]
            + candidate
            + doc.source_text[doc.slot.slot_end_idx :]
        ).encode("utf-8")
    assert _snapshot(tracks_root) == before
    captured = capsys.readouterr()
    assert f"track={track}" in captured.out
    assert candidate not in captured.out + captured.err
    assert "SYNTHETIC_STYLE" not in captured.out + captured.err


def test_no_track_keeps_legacy_english_default_and_does_not_infer_from_path(
    tracks_root: Path, vault: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    source = tracks_root / "serial" / "episodes" / "frame_en.md"
    source.write_bytes(_source(tracks_root, "serial", "en").read_bytes())
    (tracks_root / "serial" / "docs" / "STYLE_SHEET_EN.md").write_bytes(b"\xff")
    assert cli.main([str(source), "--language", "en", "--vault-dir", str(vault), "--dry-run"]) == 0
    assert "track=" not in capsys.readouterr().out
    assert not (vault / "output").exists()


@pytest.mark.parametrize("entrypoint", ["module", "console"])
@pytest.mark.parametrize("language", ["sk", "en"])
@pytest.mark.parametrize("mode", ["dry", "lint", "arena-dry", "invalid-track", "mismatch"])
def test_track_offline_entrypoints(
    entrypoint: str,
    language: Language,
    mode: str,
    tracks_root: Path,
    fixtures: Path,
    vault: Path,
) -> None:
    (vault / ".env").write_bytes(b"\xff")
    (vault / "TIER4_ADDON.txt").write_bytes(b"\xff")
    before = _snapshot(tracks_root), _snapshot(vault)
    args = _args(tracks_root, "dark-romance", language, vault)
    if mode == "lint":
        name = "candidate_en.txt" if language == "en" else "candidate.txt"
        args += ["--lint-only", str(fixtures / name), "--strict"]
        args[args.index("--vault-dir") + 1] = r"D:\forbidden-but-unused"
    else:
        args += ["--dry-run"]
    if mode == "arena-dry":
        args += ["--models", ROSTER, "--print-output"]
    elif mode == "invalid-track":
        args[args.index("--track") + 1] = "unknown"
    elif mode == "mismatch":
        args[args.index("--track") + 1] = "blog"
    command = (
        [sys.executable, "-B", "-m", "zafo_injector"]
        if entrypoint == "module"
        else [str(Path(sys.executable).with_name("zafo-inject.exe"))]
    )
    env = os.environ.copy()
    for name in ("OPENROUTER_API_KEY", "ZAFO_VAULT_DIR", "GOOGLE_DRIVE_DIR"):
        env.pop(name, None)
    env.update(NO_COLOR="1", PYTHONIOENCODING="utf-8", PYTHONDONTWRITEBYTECODE="1")
    result = subprocess.run(
        [*command, *args], capture_output=True, encoding="utf-8", env=env, timeout=30
    )
    assert result.returncode == (2 if mode in ("invalid-track", "mismatch") else 0)
    output = result.stdout + result.stderr
    assert "Traceback" not in output and "\x1b" not in output
    assert "SYNTHETIC_STYLE" not in output and "synthetic-test-key" not in output
    if result.returncode == 0:
        assert f"language={language}" in output and "track=dark-romance" in output
    if mode == "arena-dry":
        assert "initial requests=9/9" in output and "HTTP attempt budget=27" in output
    assert (_snapshot(tracks_root), _snapshot(vault)) == before


@pytest.mark.skipif(os.name != "nt", reason="Windows junction containment")
@pytest.mark.parametrize("kind", ["track", "frame", "style", "lexicon"])
def test_track_default_redirections_are_rejected(
    kind: str, tracks_root: Path, tmp_path: Path, vault: Path, fixtures: Path
) -> None:
    language: Language = "sk" if kind == "lexicon" else "en"
    args = _args(tracks_root, "blog", language, vault)
    if kind == "track":
        link, target = tracks_root / "blog", tracks_root / "serial"
        link.rename(tracks_root / "original-blog")
    elif kind == "frame":
        link = tracks_root / "blog" / "posts" / "alias"
        target = tracks_root / "serial" / "episodes" / "nested"
        args[0] = str(link / "frame_en.md")
    elif kind == "style":
        link, target = tracks_root / "blog" / "docs", tracks_root / "serial" / "docs"
        link.rename(tracks_root / "blog" / "original-docs")
    else:
        link, target = tracks_root / "docs", tmp_path / "redirected-docs"
        link.rename(tracks_root / "original-shared-docs")
        target.mkdir()
        (target / "SLOVAK_LEXICON.md").write_bytes((fixtures / "SLOVAK_LEXICON.md").read_bytes())
    subprocess.run(
        [
            "pwsh",
            "-NoProfile",
            "-Command",
            f"New-Item -ItemType Junction -Path '{link}' -Target '{target}' | Out-Null",
        ],
        check=True,
        capture_output=True,
    )
    try:
        assert cli.main(args + ["--dry-run"]) == 2
        assert not (vault / "output").exists()
    finally:
        link.rmdir()
