import os
import subprocess
import sys
from pathlib import Path

import pytest


@pytest.mark.parametrize("entrypoint", ["module", "console"])
@pytest.mark.parametrize("language", [None, "sk", "en"])
@pytest.mark.parametrize(
    ("mode", "exit_code"),
    [
        ("dry", 0),
        ("lint", 0),
        ("lint-fail", 0),
        ("strict-fail", 5),
        ("forbidden", 3),
        ("missing", 2),
        ("arguments", 2),
        ("language", 2),
        ("header", 2),
        ("lexicon", 2),
        ("arena-dry", 0),
        ("arena-overrides", 0),
        ("arena-lint", 2),
        ("arena-model", 2),
        ("arena-budget", 2),
        ("arena-min-p", 2),
        ("arena-invalid", 2),
        ("arena-duplicate", 2),
        ("arena-empty", 2),
        ("arena-one", 2),
        ("arena-forbidden", 3),
        ("arena-lexicon", 2),
        ("arena-print", 0),
        ("arena-list-trim", 0),
    ],
)
def test_offline_cli_entrypoints(
    entrypoint: str,
    language: str | None,
    mode: str,
    exit_code: int,
    tmp_path: Path,
    fixtures: Path,
) -> None:
    blog = tmp_path / "synthetic-blog"
    posts = blog / "posts"
    docs = blog / "docs"
    posts.mkdir(parents=True)
    docs.mkdir()
    english = language == "en"
    style = "STYLE_SHEET_EN.md" if english else "STYLE_SHEET.md"
    (docs / "STYLE_SHEET.md").write_bytes((fixtures / style).read_bytes())
    if not english:
        (docs / "SLOVAK_LEXICON.md").write_bytes((fixtures / "SLOVAK_LEXICON.md").read_bytes())
    source = posts / "post.md"
    frame_name = "frame_en.md" if english else "frame.md"
    original = b"\xef\xbb\xbf" + (fixtures / frame_name).read_bytes().replace(b"\n", b"\r\n")
    if mode == "header":
        original = (
            original.replace(b"words", b"slov") if english else original.replace(b"slov", b"words")
        )
    source.write_bytes(original)
    before = source.stat().st_mtime_ns
    candidate = tmp_path / "synthetic-candidate.txt"
    candidate_name = "candidate_en.txt" if english else "candidate.txt"
    candidate.write_bytes((fixtures / candidate_name).read_bytes())
    vault = tmp_path / "synthetic-vault"
    vault.mkdir()
    # Any accidental credential/addon read would fail UTF-8 decoding.
    (vault / ".env").write_bytes(b"\xff")
    (vault / "TIER4_ADDON.txt").write_bytes(b"\xff")
    args = [str(source), "--vault-dir", str(vault)]
    if language is not None:
        args += ["--language", language]
    if mode in ("lint", "lint-fail", "strict-fail"):
        if mode != "lint":
            candidate.write_text("coffee" if english else "zrovna", encoding="utf-8")
        args += ["--lint-only", str(candidate)]
        if mode == "strict-fail":
            args += ["--strict"]
    else:
        args += ["--dry-run"]
        if mode == "forbidden":
            args[2] = r"D:\must-not-be-created"
        elif mode == "missing":
            args[0] = str(posts / "missing.md")
        elif mode == "arguments":
            args += ["--candidates", "0"]
        elif mode == "language":
            args += ["--language", "de"]
        elif mode == "lexicon":
            args += ["--lexicon", str(docs / "missing-synthetic-lexicon.md")]
    if mode.startswith("arena-"):
        magnum = "anthracite-org/magnum-v4-72b"
        deepseek = "deepseek/deepseek-chat-v3-0324"
        euryale = "sao10k/l3.1-euryale-70b"
        roster = f"{magnum},{deepseek},{euryale}"
        if mode == "arena-overrides":
            roster = f"{magnum},{euryale}"
            args += ["--temp", "0.4", "--min-p", "0.2"]
        elif mode == "arena-list-trim":
            roster = f" {euryale} , {magnum} "
        elif mode == "arena-model":
            args += ["--model", magnum]
        elif mode == "arena-budget":
            args += ["--candidates", "4"]
        elif mode == "arena-min-p":
            args += ["--min-p", "0.06"]
        elif mode == "arena-invalid":
            roster = f"{magnum},sao10k/l3.3-euryale-70b"
        elif mode == "arena-duplicate":
            roster = f"{magnum},{magnum}"
        elif mode == "arena-empty":
            roster = f"{magnum},"
        elif mode == "arena-one":
            roster = magnum
        elif mode == "arena-lint":
            args.remove("--dry-run")
            args += ["--lint-only", str(candidate)]
        elif mode == "arena-forbidden":
            args[2] = r"D:\must-not-be-created"
        elif mode == "arena-lexicon":
            args += ["--lexicon", str(docs / "missing-synthetic-lexicon.md")]
        elif mode == "arena-print":
            args += ["--print-output"]
        args += ["--models", roster]
    command = (
        [sys.executable, "-m", "zafo_injector"]
        if entrypoint == "module"
        else [str(Path(sys.executable).with_name("zafo-inject.exe"))]
    )
    env = os.environ.copy()
    for name in ("OPENROUTER_API_KEY", "ZAFO_VAULT_DIR", "GOOGLE_DRIVE_DIR"):
        env.pop(name, None)
    env.update(NO_COLOR="1", PYTHONIOENCODING="utf-8")
    result = subprocess.run(
        [*command, *args], capture_output=True, encoding="utf-8", env=env, timeout=30
    )
    assert result.returncode == exit_code, result.stdout + result.stderr
    output = result.stdout + result.stderr
    assert "Traceback" not in output
    assert "\x1b" not in output
    assert "Nasypal" not in output
    assert "I poured hot water" not in output
    assert "zrovna" not in output
    assert candidate.read_text(encoding="utf-8").strip() not in output
    if exit_code == 0:
        assert "[PASS]" in output or "[FAIL]" in output
        assert f"language={language or 'sk'}" in output
    else:
        assert "[FAIL]" in output or "error:" in output
    if mode in ("lexicon", "arena-lexicon") and english:
        assert "--lexicon is Slovak-only" in output
    if mode.startswith("arena-") and exit_code == 0:
        assert "Report-only arena:" in output
        assert "global concurrency cap=3" in output
        if mode == "arena-overrides":
            assert "temperature=0.4; min_p=0.2" in output
        elif mode == "arena-list-trim":
            assert output.index("Model " + euryale) < output.index("Model " + magnum)
        else:
            assert "initial requests=9/9" in output
            assert "HTTP attempt budget=27" in output
    if english:
        assert not (docs / "SLOVAK_LEXICON.md").exists()
    assert source.read_bytes() == original
    assert source.stat().st_mtime_ns == before
    assert not (vault / "output").exists()
    assert sorted(path.name for path in vault.iterdir()) == [".env", "TIER4_ADDON.txt"]


@pytest.mark.parametrize("entrypoint", ["module", "console"])
@pytest.mark.parametrize("language", ["sk", "en"])
@pytest.mark.parametrize(
    ("mode", "exit_code"),
    [
        ("help", 0),
        ("dry", 0),
        ("matrix", 0),
        ("lint", 0),
        ("strict", 5),
        ("override", 0),
        ("unknown", 2),
        ("recursion", 2),
        ("missing", 2),
        ("forbidden", 3),
        ("environment", 0),
        ("model-replacement", 0),
        ("bad-combination", 2),
    ],
)
def test_configured_offline_entrypoints(
    entrypoint: str,
    language: str,
    mode: str,
    exit_code: int,
    tmp_path: Path,
    tracks_root: Path,
    fixtures: Path,
) -> None:
    directory = tmp_path / "settings"
    directory.mkdir()
    caller = tmp_path / "caller"
    caller.mkdir()
    suffix = "_en" if language == "en" else ""
    source = tracks_root / "serial" / "episodes" / "nested" / f"frame{suffix}.md"
    candidate = tmp_path / "candidate.txt"
    candidate.write_bytes((fixtures / f"candidate{suffix}.txt").read_bytes())
    vault = tmp_path / "configured-vault"
    environment_vault = tmp_path / "environment-vault"
    for path in (vault, environment_vault):
        path.mkdir()
        (path / ".env").write_bytes(b"\xff")
        (path / "TIER4_ADDON.txt").write_bytes(b"\xff")
    selected_language = ("en" if language == "sk" else "sk") if mode == "override" else language
    content = (
        f"language = '{selected_language}'\n"
        "track = 'serial'\ntracks_root = '..\\synthetic-tracks'\ncandidates = 1\n"
        "vault_dir = '..\\configured-vault'\n"
    )
    args = [str(source), "--config", "..\\settings\\settings.toml"]
    if mode in ("matrix", "model-replacement", "bad-combination"):
        content += "models = ['anthracite-org/magnum-v4-72b', 'sao10k/l3.1-euryale-70b']\n"
    if mode == "unknown":
        content += "OPENROUTER_API_KEY = 'SYNTHETIC_SETTINGS_SENTINEL'\n"
    elif mode == "recursion":
        depth = max(2000, sys.getrecursionlimit() * 2)
        content += "models = " + "[" * depth + "'SYNTHETIC_SETTINGS_SENTINEL'" + "]" * depth + "\n"
        args += ["--model", "anthracite-org/magnum-v4-72b"]
    if mode in ("forbidden", "environment", "lint", "strict"):
        content = content.replace(
            "vault_dir = '..\\configured-vault'", r"vault_dir = 'D:\synthetic-forbidden-but-unused'"
        )
    if mode in ("lint", "strict", "bad-combination"):
        content += "style_sheet = 'missing-unused-style.md'\n"
        args += ["--lint-only", str(candidate), "--strict"]
        if mode == "strict":
            candidate.write_text("coffee" if language == "en" else "zrovna", encoding="utf-8")
    else:
        args += ["--dry-run"]
    if mode == "override":
        args += ["--language", language, "--candidates", "3"]
    elif mode == "model-replacement":
        args += ["--model", "anthracite-org/magnum-v4-72b"]
    config = directory / "settings.toml"
    if mode != "missing":
        config.write_text(content, encoding="utf-8")
    if mode == "help":
        config.unlink()
        args = ["--config", "..\\settings\\settings.toml", "--help"]
    original = source.read_bytes(), source.stat().st_mtime_ns
    command = (
        [sys.executable, "-m", "zafo_injector"]
        if entrypoint == "module"
        else [str(Path(sys.executable).with_name("zafo-inject.exe"))]
    )
    env = os.environ.copy()
    for name in ("OPENROUTER_API_KEY", "ZAFO_VAULT_DIR", "GOOGLE_DRIVE_DIR"):
        env.pop(name, None)
    env.update(
        NO_COLOR="1",
        PYTHONIOENCODING="utf-8",
        PYTHONDONTWRITEBYTECODE="1",
        TEMP=str(tmp_path),
        TMP=str(tmp_path),
    )
    if mode == "environment":
        env["ZAFO_VAULT_DIR"] = str(environment_vault)
    result = subprocess.run(
        [*command, *args], cwd=caller, capture_output=True, encoding="utf-8", env=env, timeout=30
    )
    output = result.stdout + result.stderr
    assert result.returncode == exit_code, output
    assert "SYNTHETIC_SETTINGS_SENTINEL" not in output
    assert "SYNTHETIC_STYLE" not in output
    assert candidate.read_text(encoding="utf-8").strip() not in output
    assert "Traceback" not in output
    assert "\x1b" not in output
    if mode == "help":
        assert "--config FILE" in output
    elif exit_code in (0, 5):
        assert f"language={language}" in output
        assert "track=serial" in output
    if mode == "matrix":
        assert "initial requests=2/9" in output
    elif mode == "model-replacement":
        assert "Report-only arena" not in output
    assert (source.read_bytes(), source.stat().st_mtime_ns) == original
    for path in (vault, environment_vault):
        assert sorted(child.name for child in path.iterdir()) == [".env", "TIER4_ADDON.txt"]
