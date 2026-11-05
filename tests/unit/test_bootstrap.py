import os
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


def test_bootstrap_ignores_section_heading_inside_fenced_example(tmp_path: Path) -> None:
    lexicon = tmp_path / "synthetic-lexicon.md"
    lexicon.write_text(
        "## 1. Example\n````markdown\n## 6. Fake section\n"
        "```text\nWrong skeleton.\n```\n````\n"
        "## 6. Actual addon\n```text\nCorrect synthetic skeleton.\n```\n",
        encoding="utf-8",
    )
    vault = tmp_path / "synthetic-bootstrap-vault"
    result = run_bootstrap(vault, lexicon)
    assert result.returncode == 0, result.stderr
    assert (vault / "TIER4_ADDON.txt").read_text(
        encoding="utf-8"
    ) == "Correct synthetic skeleton.\n"


@pytest.mark.skipif(os.name != "nt", reason="Windows junction containment")
@pytest.mark.parametrize("name", ["output", ".env", "TIER4_ADDON.txt"])
def test_bootstrap_rejects_redirected_children(tmp_path: Path, fixtures: Path, name: str) -> None:
    vault = tmp_path / "synthetic-bootstrap-vault"
    vault.mkdir()
    target = tmp_path / "synthetic-redirect-target"
    target.mkdir()
    junction = vault / name
    subprocess.run(
        [
            "pwsh",
            "-NoProfile",
            "-Command",
            f"New-Item -ItemType Junction -Path '{junction}' -Target '{target}' | Out-Null",
        ],
        capture_output=True,
        check=True,
    )
    try:
        result = run_bootstrap(vault, fixtures / "SLOVAK_LEXICON.md", "-Force")
        assert result.returncode == 2
        assert list(target.iterdir()) == []
        assert list(vault.iterdir()) == [junction]
    finally:
        junction.rmdir()


def test_failed_force_keeps_existing_files(tmp_path: Path) -> None:
    vault = tmp_path / "synthetic-bootstrap-vault"
    vault.mkdir()
    originals = {".env": b"OPENROUTER_API_KEY=synthetic-key", "TIER4_ADDON.txt": b"Keep."}
    for name, content in originals.items():
        (vault / name).write_bytes(content)
    lexicon = tmp_path / "synthetic-bad-lexicon.md"
    lexicon.write_text("## 6. Addon\n```text\nNo closing fence.", encoding="utf-8")
    result = run_bootstrap(vault, lexicon, "-Force")
    assert result.returncode == 2
    assert "synthetic-key" not in result.stdout + result.stderr
    assert not (vault / "output").exists()
    assert all((vault / name).read_bytes() == content for name, content in originals.items())


@pytest.mark.skipif(os.name != "nt", reason="Windows PowerShell drive locations")
@pytest.mark.parametrize("relative", ["lexicon", "vault", "forbidden-vault"])
def test_bootstrap_relative_paths_use_powershell_location(
    tmp_path: Path, fixtures: Path, relative: str
) -> None:
    pwsh = shutil.which("pwsh")
    if pwsh is None:
        pytest.skip("PowerShell 7 is unavailable")
    workspace = SCRIPT.parents[1]
    vault = tmp_path / "synthetic-bootstrap-vault"
    if relative == "lexicon":
        process_dir, location = tmp_path, workspace
        vault_arg = str(vault)
        lexicon_arg = r".\tests\fixtures\SLOVAK_LEXICON.md"
    else:
        process_dir, location = workspace, tmp_path
        vault_arg = r".\synthetic-bootstrap-vault"
        lexicon_arg = str(fixtures / "SLOVAK_LEXICON.md")
        if relative == "forbidden-vault":
            process_dir, location = tmp_path, workspace

    def quote(path: str | Path) -> str:
        return "'" + str(path).replace("'", "''") + "'"

    result = subprocess.run(
        [
            pwsh,
            "-NoProfile",
            "-Command",
            f"Set-Location -LiteralPath {quote(location)}; "
            f"& {quote(SCRIPT)} -VaultDir {quote(vault_arg)} "
            f"-LexiconPath {quote(lexicon_arg)}; exit $LASTEXITCODE",
        ],
        cwd=process_dir,
        capture_output=True,
        encoding="utf-8",
        timeout=30,
    )
    if relative == "forbidden-vault":
        assert result.returncode == 2, result.stdout + result.stderr
        assert not vault.exists()
        assert not (workspace / "synthetic-bootstrap-vault").exists()
    else:
        assert result.returncode == 0, result.stdout + result.stderr
        assert (vault / "output").is_dir()
        assert "ordinary morning" in (vault / "TIER4_ADDON.txt").read_text(encoding="utf-8")


@pytest.mark.parametrize("initialized", [False, True])
def test_success_resets_stale_exit_code_in_same_powershell_session(
    tmp_path: Path, fixtures: Path, initialized: bool
) -> None:
    pwsh = shutil.which("pwsh")
    if pwsh is None:
        pytest.skip("PowerShell 7 is unavailable")
    vault = tmp_path / "synthetic-bootstrap-vault"
    if initialized:
        first = run_bootstrap(vault, fixtures / "SLOVAK_LEXICON.md")
        assert first.returncode == 0, first.stderr

    def quote(path: Path) -> str:
        return "'" + str(path).replace("'", "''") + "'"

    result = subprocess.run(
        [
            pwsh,
            "-NoProfile",
            "-Command",
            "$global:LASTEXITCODE = 2; "
            f"& {quote(SCRIPT)} -VaultDir {quote(vault)} "
            f"-LexiconPath {quote(fixtures / 'SLOVAK_LEXICON.md')}; "
            "Write-Output 'Caller continues'; exit $LASTEXITCODE",
        ],
        capture_output=True,
        encoding="utf-8",
        timeout=30,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert "[PASS] Vault initialized." in result.stdout
    assert "Caller continues" in result.stdout
    assert (vault / "output").is_dir()
