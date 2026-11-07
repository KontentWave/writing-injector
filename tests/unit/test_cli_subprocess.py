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
    if mode == "lexicon" and english:
        assert "--lexicon is Slovak-only" in output
    if english:
        assert not (docs / "SLOVAK_LEXICON.md").exists()
    assert source.read_bytes() == original
    assert source.stat().st_mtime_ns == before
    assert not (vault / "output").exists()
    assert sorted(path.name for path in vault.iterdir()) == [".env", "TIER4_ADDON.txt"]
