import os
import subprocess
from pathlib import Path

import pytest

from zafo_injector.config import (
    AirGapViolationError,
    ConfigurationError,
    VaultConfig,
    validate_output_dir,
    validate_storage_path,
    vault_child,
)

WORKSPACE = Path(__file__).resolve().parents[2]


@pytest.mark.parametrize(
    "path", [r"D:\private-vault", r"d:\zafo-injector\private", r"\\?\D:\private-vault"]
)
def test_entire_d_drive_is_forbidden(path: str) -> None:
    with pytest.raises(AirGapViolationError):
        VaultConfig.load(Path(path), WORKSPACE, require_api_key=False)


def test_workspace_is_forbidden_on_other_drives(tmp_path: Path) -> None:
    with pytest.raises(AirGapViolationError):
        VaultConfig.load(tmp_path / "nested", tmp_path, require_api_key=False)


@pytest.mark.parametrize("name", ["Google Drive", "GoogleDrive", "My Drive", "Shared drives"])
def test_google_drive_names_are_forbidden(tmp_path: Path, name: str) -> None:
    with pytest.raises(AirGapViolationError):
        validate_storage_path(tmp_path / name / "vault", WORKSPACE)


@pytest.mark.parametrize("marker", ["document.gdoc", "project.code-workspace"])
def test_ancestor_markers_are_forbidden(tmp_path: Path, marker: str) -> None:
    (tmp_path / marker).touch()
    with pytest.raises(AirGapViolationError):
        validate_storage_path(tmp_path / "nested" / "vault", WORKSPACE)


def test_configured_cloud_root(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("GOOGLE_DRIVE_DIR", str(tmp_path))
    with pytest.raises(AirGapViolationError):
        validate_storage_path(tmp_path / "vault", WORKSPACE)


def test_env_redaction_and_no_global_mutation(vault: Path) -> None:
    (vault / ".env").write_text(
        "# comment\nexport OPENROUTER_API_KEY='synthetic-key'\nIGNORED=value # note\n",
        encoding="utf-8",
    )
    config = VaultConfig.load(vault, WORKSPACE)
    assert config.api_key == "synthetic-key"
    assert "synthetic-key" not in repr(config)
    assert "OPENROUTER_API_KEY" not in os.environ


def test_process_env_takes_precedence(vault: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("OPENROUTER_API_KEY", "synthetic-process-key")
    monkeypatch.setenv("ZAFO_VAULT_DIR", str(vault))
    assert VaultConfig.load(None, WORKSPACE).api_key == "synthetic-process-key"


@pytest.mark.parametrize("content", ["OPENROUTER_API_KEY=", "SECRET SENTINEL", "KEY='SECRET"])
def test_configuration_errors_do_not_echo_secret(vault: Path, content: str) -> None:
    (vault / ".env").write_text(content, encoding="utf-8")
    with pytest.raises(ConfigurationError) as error:
        VaultConfig.load(vault, WORKSPACE)
    assert "SECRET" not in str(error.value)


def test_dry_configuration_does_not_read_env(vault: Path) -> None:
    (vault / ".env").write_bytes(b"\xff")
    assert VaultConfig.load(vault, WORKSPACE, require_api_key=False).api_key == ""


@pytest.mark.parametrize("key", ["synthetic-secret-ľ", "synthetic\tkey", "synthetic key"])
def test_invalid_header_keys_are_rejected_without_disclosure(vault: Path, key: str) -> None:
    (vault / ".env").write_text(f"OPENROUTER_API_KEY='{key}'", encoding="utf-8")
    with pytest.raises(ConfigurationError) as error:
        VaultConfig.load(vault, WORKSPACE)
    assert key not in str(error.value)


def test_output_must_be_exact_child(vault: Path, tmp_path: Path) -> None:
    with pytest.raises(AirGapViolationError):
        validate_output_dir(tmp_path / "other", vault, WORKSPACE)


@pytest.mark.skipif(os.name != "nt", reason="Windows junction containment")
def test_junction_to_workspace_is_rejected(tmp_path: Path) -> None:
    junction = tmp_path / "redirect"
    subprocess.run(
        [
            "pwsh",
            "-NoProfile",
            "-Command",
            f"New-Item -ItemType Junction -Path '{junction}' -Target '{WORKSPACE}' | Out-Null",
        ],
        check=True,
        capture_output=True,
    )
    try:
        with pytest.raises(AirGapViolationError):
            validate_storage_path(junction / "vault", WORKSPACE)
    finally:
        junction.rmdir()


@pytest.mark.skipif(os.name != "nt", reason="Windows junction containment")
@pytest.mark.parametrize("name", ["output", ".env", "TIER4_ADDON.txt"])
def test_child_junction_outside_vault_is_rejected(vault: Path, tmp_path: Path, name: str) -> None:
    target = tmp_path / "elsewhere"
    target.mkdir()
    junction = vault / name
    if junction.is_file():
        junction.unlink()
    subprocess.run(
        [
            "pwsh",
            "-NoProfile",
            "-Command",
            f"New-Item -ItemType Junction -Path '{junction}' -Target '{target}' | Out-Null",
        ],
        check=True,
        capture_output=True,
    )
    try:
        with pytest.raises(AirGapViolationError):
            vault_child(vault, name, WORKSPACE)
        if name == ".env":
            with pytest.raises(AirGapViolationError):
                VaultConfig.load(vault, WORKSPACE)
        elif name == "output":
            with pytest.raises(AirGapViolationError):
                validate_output_dir(junction, vault, WORKSPACE)
    finally:
        junction.rmdir()


def test_canonical_paths_and_explicit_vault_precedence(
    vault: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("ZAFO_VAULT_DIR", r"D:\must-not-be-accessed")
    raw = vault / ".." / vault.name
    config = VaultConfig.load(raw, WORKSPACE)
    assert config.vault_dir == vault.resolve()
    assert config.output_dir == vault.resolve() / "output"
    assert validate_storage_path(tmp_path / "missing" / ".." / "new", WORKSPACE) == (
        tmp_path / "new"
    )
