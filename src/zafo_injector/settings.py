import os
import tomllib
from dataclasses import dataclass, fields
from pathlib import Path

from .config import ConfigurationError
from .model_profiles import select_model_profiles
from .models import Language

TRACKS = ("blog", "serial", "dark-romance")


def _absolute_path(path: Path, base: Path | None = None) -> Path:
    if "\0" in str(path):
        raise ConfigurationError("TOML paths must not contain null characters.")
    try:
        path = path.expanduser()
    except RuntimeError:
        raise ConfigurationError("TOML path could not be interpreted.") from None
    if os.name == "nt" and bool(path.drive) != bool(path.root):
        raise ConfigurationError("TOML paths must be fully qualified or ordinary relative paths.")
    try:
        return Path(os.path.abspath(path if base is None else base / path))
    except (OSError, ValueError):
        raise ConfigurationError("TOML path could not be interpreted.") from None


def _text(data: dict[str, object], key: str) -> str | None:
    value = data.get(key)
    if value is None:
        return None
    if not isinstance(value, str) or not value.strip():
        raise ConfigurationError(f"TOML {key} must be a nonblank string.")
    return value


def _path(data: dict[str, object], key: str, base: Path) -> Path | None:
    value = _text(data, key)
    return None if value is None else _absolute_path(Path(value), base)


def _number(data: dict[str, object], key: str, maximum: int) -> float | None:
    value = data.get(key)
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not 0 <= value <= maximum:
        raise ConfigurationError(f"TOML {key} must be a finite number between 0 and {maximum}.")
    return float(value)


def _language(data: dict[str, object]) -> Language | None:
    value = _text(data, "language")
    if value is None:
        return None
    if value == "sk":
        return "sk"
    if value == "en":
        return "en"
    raise ConfigurationError("TOML language must be sk or en.")


def _models(data: dict[str, object]) -> str | None:
    value = data.get("models")
    if value is None:
        return None
    message = "TOML models must be an array of two or three distinct registered full IDs."
    if not isinstance(value, list):
        raise ConfigurationError(message)
    model_ids: list[str] = []
    for item in value:
        if not isinstance(item, str) or "," in item:
            raise ConfigurationError(message)
        model_ids.append(item)
    try:
        profiles = select_model_profiles(",".join(model_ids))
    except ConfigurationError:
        raise ConfigurationError(message) from None
    return ",".join(profile.model_id for profile in profiles)


@dataclass(frozen=True)
class RunSettings:
    language: Language | None = None
    candidates: int | None = None
    model: str | None = None
    models: str | None = None
    temp: float | None = None
    min_p: float | None = None
    track: str | None = None
    tracks_root: Path | None = None
    style_sheet: Path | None = None
    lexicon: Path | None = None
    vault_dir: Path | None = None

    @classmethod
    def load(cls, path: Path) -> "RunSettings":
        path = _absolute_path(path)
        if path.suffix.casefold() != ".toml":
            raise ConfigurationError("TOML settings require an explicitly selected .toml file.")
        try:
            with path.open("rb") as stream:
                data: dict[str, object] = tomllib.load(stream)
        except (ValueError, RecursionError):
            raise ConfigurationError("TOML settings must be valid UTF-8 TOML.") from None
        except OSError:
            raise ConfigurationError("TOML settings file could not be read.") from None
        if data.keys() - {field.name for field in fields(cls)}:
            raise ConfigurationError("TOML settings contain unsupported fields or tables.")
        if "model" in data and "models" in data:
            raise ConfigurationError("TOML model and models must not be supplied together.")
        candidates = data.get("candidates")
        if candidates is not None and (
            isinstance(candidates, bool) or not isinstance(candidates, int) or candidates < 1
        ):
            raise ConfigurationError("TOML candidates must be a positive integer.")
        track = _text(data, "track")
        if track is not None and track not in TRACKS:
            raise ConfigurationError("TOML track must be blog, serial, or dark-romance.")
        return cls(
            language=_language(data),
            candidates=candidates,
            model=_text(data, "model"),
            models=_models(data),
            temp=_number(data, "temp", 2),
            min_p=_number(data, "min_p", 1),
            track=track,
            tracks_root=_path(data, "tracks_root", path.parent),
            style_sheet=_path(data, "style_sheet", path.parent),
            lexicon=_path(data, "lexicon", path.parent),
            vault_dir=_path(data, "vault_dir", path.parent),
        )
