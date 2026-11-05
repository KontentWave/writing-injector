import os
import subprocess
import sys
from pathlib import Path

import pytest


@pytest.mark.parametrize("entrypoint", ["module", "console"])
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
    ],
)
def test_offline_cli_entrypoints(
    entrypoint: str, mode: str, exit_code: int, tmp_path: Path, fixtures: Path
) -> None:
    blog = tmp_path / "synthetic-blog"
    posts = blog / "posts"
    docs = blog / "docs"
    posts.mkdir(parents=True)
    docs.mkdir()
    for name in ("STYLE_SHEET.md", "SLOVAK_LEXICON.md"):
        (docs / name).write_bytes((fixtures / name).read_bytes())
    source = posts / "post.md"
    original = b"\xef\xbb\xbf" + (fixtures / "frame.md").read_bytes().replace(b"\n", b"\r\n")
    source.write_bytes(original)
    before = source.stat().st_mtime_ns
    candidate = tmp_path / "synthetic-candidate.txt"
    candidate.write_bytes((fixtures / "candidate.txt").read_bytes())
    vault = tmp_path / "synthetic-vault"
    vault.mkdir()
    # Any accidental credential/addon read would fail UTF-8 decoding.
    (vault / ".env").write_bytes(b"\xff")
    (vault / "TIER4_ADDON.txt").write_bytes(b"\xff")
    args = [str(source), "--vault-dir", str(vault)]
    if mode in ("lint", "lint-fail", "strict-fail"):
        if mode != "lint":
            candidate.write_text("zrovna", encoding="utf-8")
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
    assert "zrovna" not in output
    assert candidate.read_text(encoding="utf-8").strip() not in output
    if exit_code == 0:
        assert "[PASS]" in output or "[FAIL]" in output
    else:
        assert "[FAIL]" in output or "error:" in output
    assert source.read_bytes() == original
    assert source.stat().st_mtime_ns == before
    assert not (vault / "output").exists()
    assert sorted(path.name for path in vault.iterdir()) == [".env", "TIER4_ADDON.txt"]
