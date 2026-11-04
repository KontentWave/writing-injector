import os
from dataclasses import dataclass, field
from pathlib import Path, PureWindowsPath


class AirGapViolationError(ValueError):
    """A private storage path crosses a forbidden boundary."""


class ConfigurationError(ValueError):
    """The local vault configuration is invalid."""


def validate_api_key(key: str) -> None:
    if not key or not all("!" <= character <= "~" for character in key):
        raise ConfigurationError("A valid ASCII OPENROUTER_API_KEY is required for generation.")


_CLOUD_NAMES = {
    "google drive",
    "googledrive",
    "my drive",
    "shared drives",
    ".shortcut-targets-by-id",
}


def validate_storage_path(path: Path, workspace_root: Path) -> Path:
    resolved = path.expanduser().resolve()
    for candidate in (path, resolved):
        if PureWindowsPath(str(candidate)).drive.removeprefix("\\\\?\\").casefold() == "d:":
            raise AirGapViolationError("All of drive D: is forbidden for private storage.")
    if resolved.is_relative_to(workspace_root.resolve()):
        raise AirGapViolationError("Private storage must be outside the workspace.")
    if any(part.casefold() in _CLOUD_NAMES for part in resolved.parts):
        raise AirGapViolationError("Google Drive storage is forbidden.")
    cloud_root = os.environ.get("GOOGLE_DRIVE_DIR")
    if cloud_root and resolved.is_relative_to(Path(cloud_root).expanduser().resolve()):
        raise AirGapViolationError("Configured Google Drive storage is forbidden.")
    for ancestor in (resolved, *resolved.parents):
        if ancestor.is_dir() and (
            any(ancestor.glob("*.gdoc")) or any(ancestor.glob("*.code-workspace"))
        ):
            raise AirGapViolationError("Private storage has cloud or workspace markers.")
    return resolved


def vault_child(vault_dir: Path, name: str, workspace_root: Path) -> Path:
    child = validate_storage_path(vault_dir / name, workspace_root)
    if child != vault_dir / name:
        raise AirGapViolationError("Vault children must not be redirected by links.")
    return child


def validate_output_dir(output_dir: Path, vault_dir: Path, workspace_root: Path) -> Path:
    vault = validate_storage_path(vault_dir, workspace_root)
    output = validate_storage_path(output_dir, workspace_root)
    if output != vault / "output" or output_dir.absolute() != vault / "output":
        raise AirGapViolationError("Output must be the vault's unredirected output directory.")
    return output


def _read_env(path: Path) -> dict[str, str]:
    if not path.exists():
        return {}
    values: dict[str, str] = {}
    for line in path.read_text(encoding="utf-8-sig").splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        key, sep, value = line.removeprefix("export ").partition("=")
        if not sep or not key.strip().isidentifier():
            raise ConfigurationError("Malformed vault .env entry.")
        value = value.strip()
        if value.startswith(("'", '"')):
            if len(value) < 2 or value[-1] != value[0]:
                raise ConfigurationError("Malformed quoted vault .env entry.")
            value = value[1:-1]
        else:
            value = value.split(" #", 1)[0].rstrip()
        values[key.strip()] = value
    return values


@dataclass(frozen=True)
class VaultConfig:
    vault_dir: Path
    output_dir: Path
    workspace_root: Path
    api_key: str = field(default="", repr=False)

    @classmethod
    def load(
        cls, vault_dir: Path | None, workspace_root: Path, *, require_api_key: bool = True
    ) -> "VaultConfig":
        raw = vault_dir or Path(os.environ.get("ZAFO_VAULT_DIR", str(Path.home() / "zafo-local")))
        vault = validate_storage_path(raw, workspace_root)
        output = validate_output_dir(vault / "output", vault, workspace_root)
        key = ""
        if require_api_key:
            env_path = vault_child(vault, ".env", workspace_root)
            key = os.environ.get("OPENROUTER_API_KEY", "") or _read_env(env_path).get(
                "OPENROUTER_API_KEY", ""
            )
            validate_api_key(key)
        return cls(vault, output, workspace_root.resolve(), key)
