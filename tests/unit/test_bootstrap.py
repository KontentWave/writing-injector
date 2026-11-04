import shutil
import subprocess
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "init_local_vault.ps1"


def run_bootstrap(vault: Path, lexicon: Path, *args: str) -> subprocess.CompletedProcess[str]:
    pwsh = shutil.which("pwsh")
    if pwsh is None:
        pytest.skip("PowerShell 7 is unavailable")
    return subprocess.run(
        [
            pwsh,
            "-NoProfile",
            "-File",
            str(SCRIPT),
            "-VaultDir",
            str(vault),
            "-LexiconPath",
            str(lexicon),
            *args,
        ],
        capture_output=True,
        text=True,
        encoding="utf-8",
    )


def test_bootstrap_initialization_idempotence_and_force(tmp_path: Path, fixtures: Path) -> None:
    vault = tmp_path / "synthetic-bootstrap-vault"
    lexicon = fixtures / "SLOVAK_LEXICON.md"
    first = run_bootstrap(vault, lexicon)
    assert first.returncode == 0, first.stderr
    assert (vault / "output").is_dir()
    assert (vault / ".env").read_text(encoding="utf-8") == "OPENROUTER_API_KEY=\n"
    assert "ordinary morning" in (vault / "TIER4_ADDON.txt").read_text(encoding="utf-8")
    (vault / ".env").write_text("OPENROUTER_API_KEY=synthetic-key", encoding="utf-8")
    (vault / "TIER4_ADDON.txt").write_text("Preserved synthetic addon.", encoding="utf-8")
    second = run_bootstrap(vault, tmp_path / "missing-lexicon.md")
    assert second.returncode == 0, second.stderr
    assert "synthetic-key" in (vault / ".env").read_text(encoding="utf-8")
    assert (vault / "TIER4_ADDON.txt").read_text(encoding="utf-8") == "Preserved synthetic addon."
    forced = run_bootstrap(vault, lexicon, "-Force")
    assert forced.returncode == 0, forced.stderr
    assert "synthetic-key" not in (vault / ".env").read_text(encoding="utf-8")
    assert "ordinary morning" in (vault / "TIER4_ADDON.txt").read_text(encoding="utf-8")


@pytest.mark.parametrize("path", [r"D:\must-not-be-created", r"\\?\D:\must-not-be-created"])
def test_bootstrap_rejects_d_before_creating(fixtures: Path, path: str) -> None:
    result = run_bootstrap(Path(path), fixtures / "SLOVAK_LEXICON.md")
    assert result.returncode != 0
    assert not Path(r"D:\must-not-be-created").exists()


def test_bad_lexicon_creates_nothing(tmp_path: Path) -> None:
    lexicon = tmp_path / "bad.md"
    lexicon.write_text("No numbered section.", encoding="utf-8")
    vault = tmp_path / "synthetic-bootstrap-vault"
    result = run_bootstrap(vault, lexicon)
    assert result.returncode != 0
    assert not vault.exists()


def test_bootstrap_preserves_headings_in_addon_and_refills_empty_file(tmp_path: Path) -> None:
    lexicon = tmp_path / "synthetic-lexicon.md"
    lexicon.write_text(
        "## §6 Addon\n```text\n## Voice rules\nMake coffee.\n```\n## 7. Other\n",
        encoding="utf-8",
    )
    vault = tmp_path / "synthetic-bootstrap-vault"
    vault.mkdir()
    (vault / ".env").write_text("PRESERVE=yes", encoding="utf-8")
    (vault / "TIER4_ADDON.txt").write_text(" \n ", encoding="utf-8")
    result = run_bootstrap(vault, lexicon)
    assert result.returncode == 0, result.stderr
    assert (vault / "TIER4_ADDON.txt").read_text(
        encoding="utf-8"
    ) == "## Voice rules\nMake coffee.\n"
    assert (vault / ".env").read_text(encoding="utf-8") == "PRESERVE=yes"
