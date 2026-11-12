import builtins
import hashlib
import io
import json
import os
import subprocess
import sys
from pathlib import Path
from unittest.mock import DEFAULT, Mock

import httpx
import pytest

from zafo_injector import cli
from zafo_injector.models import ModelParams

MAGNUM = "anthracite-org/magnum-v4-72b"
EURYALE = "sao10k/l3.1-euryale-70b"
DEEPSEEK = "deepseek/deepseek-chat-v3-0324"


def _settings(directory: Path, text: str) -> Path:
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / "settings.toml"
    path.write_text(text, encoding="utf-8")
    return path


def _without(arguments: list[str], flag: str) -> list[str]:
    index = arguments.index(flag)
    return arguments[:index] + arguments[index + 2 :]


def _blocked(*args: object, **kwargs: object) -> None:
    raise AssertionError("Unexpected source, vault, output, or network access.")


@pytest.mark.parametrize("explicit_defaults", [False, True])
def test_configuration_defaults_and_explicit_default_values(
    tmp_path: Path,
    cli_args: list[str],
    english_cli_args: list[str],
    mock_api: list[httpx.Request],
    explicit_defaults: bool,
) -> None:
    config = _settings(
        tmp_path,
        f"language = 'en'\ncandidates = 1\nmodel = '{EURYALE}'\ntemp = 0.4\nmin_p = 0.2\n",
    )
    args = cli_args if explicit_defaults else _without(english_cli_args, "--language")
    if explicit_defaults:
        args = [
            *args,
            "--language",
            "sk",
            "--candidates",
            "3",
            "--model",
            ModelParams().model,
            "--temp",
            "0.68",
            "--min-p",
            "0.06",
        ]
    assert cli.main([*args, "--config", str(config)]) == 0
    assert len(mock_api) == (3 if explicit_defaults else 1)
    for request in mock_api:
        payload = json.loads(request.content)
        assert payload["model"] == (MAGNUM if explicit_defaults else EURYALE)
        assert payload["temperature"] == (0.68 if explicit_defaults else 0.4)
        assert payload["min_p"] == (0.06 if explicit_defaults else 0.2)
        language = "Slovak" if explicit_defaults else "English"
        assert f"Write only in {language}, including dialogue." in payload["messages"][0]["content"]


@pytest.mark.parametrize(("temperature", "min_p"), [(0, 0), (2, 1)])
def test_toml_sampling_inclusive_boundaries(
    tmp_path: Path,
    cli_args: list[str],
    mock_api: list[httpx.Request],
    temperature: int,
    min_p: int,
) -> None:
    config = _settings(tmp_path, f"candidates = 1\ntemp = {temperature}\nmin_p = {min_p}\n")
    assert cli.main([*cli_args, "--config", str(config)]) == 0
    payload = json.loads(mock_api[0].content)
    assert payload["temperature"] == temperature
    assert payload["min_p"] == min_p


@pytest.mark.parametrize("language", ["sk", "en"])
@pytest.mark.parametrize("matrix", [False, True])
def test_settings_preserve_equivalent_payloads_reports_and_sources(
    tmp_path: Path,
    cli_args: list[str],
    english_cli_args: list[str],
    vault: Path,
    mock_api: list[httpx.Request],
    language: str,
    matrix: bool,
) -> None:
    args = [*(english_cli_args if language == "en" else cli_args), "--candidates", "1", "--strict"]
    if matrix:
        args += ["--models", f"{MAGNUM},{EURYALE}", "--temp", "0.4", "--min-p", "0.2"]
    source = Path(args[0])
    before = source.read_bytes(), source.stat().st_mtime_ns
    assert cli.main(args) == 0
    original_requests = sorted(request.content for request in mock_api)
    original_outputs = {path.name: path.read_bytes() for path in (vault / "output").iterdir()}
    second_vault = tmp_path / "second-synthetic-vault"
    second_vault.mkdir()
    for name in (".env", "TIER4_ADDON.txt"):
        (second_vault / name).write_bytes((vault / name).read_bytes())
    if matrix:
        content = (
            f"language = '{language}'\ncandidates = 1\nmodels = [' {MAGNUM} ', '{EURYALE}']\n"
            "temp = 0.4\nmin_p = 0.2\nvault_dir = 'second-synthetic-vault'\n"
            f"style_sheet = '{args[args.index('--style-sheet') + 1]}'\n"
        )
        if language == "sk":
            content += f"lexicon = '{args[args.index('--lexicon') + 1]}'\n"
        config = _settings(tmp_path, content)
        configured_args = [str(source), "--config", str(config), "--strict"]
    else:
        config = _settings(tmp_path, "")
        args[args.index("--vault-dir") + 1] = str(second_vault)
        configured_args = [*args, "--config", str(config)]
    assert cli.main(configured_args) == 0
    assert (
        sorted(request.content for request in mock_api[len(original_requests) :])
        == original_requests
    )
    assert {
        path.name: path.read_bytes() for path in (second_vault / "output").iterdir()
    } == original_outputs
    assert (source.read_bytes(), source.stat().st_mtime_ns) == before


@pytest.mark.parametrize(
    "content",
    [
        "SYNTHETIC_UNKNOWN = 'SYNTHETIC_VALUE'",
        "[defaults]\nlanguage = 'en'",
        "OPENROUTER_API_KEY = 'SYNTHETIC_VALUE'",
        "addon = 'SYNTHETIC_VALUE'",
        "prompt = 'SYNTHETIC_VALUE'",
        "source = 'SYNTHETIC_VALUE'",
        "draft = 'SYNTHETIC_VALUE'",
        "post_path = 'SYNTHETIC_VALUE'",
        "output_dir = 'SYNTHETIC_VALUE'",
        "dry_run = true",
        "lint_only = 'SYNTHETIC_VALUE'",
        "strict = true",
        "print_output = true",
        "generate = true",
        "language = 'de'",
        "language = 2026-11-11",
        "candidates = true",
        "candidates = 0",
        "candidates = 1.5",
        "model = ''",
        "model = 12",
        f"models = ['{MAGNUM}']",
        f"models = ['{MAGNUM}', '{MAGNUM}']",
        f"models = ['{MAGNUM}', 'SYNTHETIC_UNKNOWN_MODEL']",
        f"models = ['{MAGNUM},{EURYALE}']",
        f"models = ['{MAGNUM}', 12]",
        f"models = '{MAGNUM},{EURYALE}'",
        f"model = '{MAGNUM}'\nmodels = ['{MAGNUM}', '{EURYALE}']",
        "temp = true",
        "temp = -0.1",
        "temp = 2.1",
        "temp = nan",
        "temp = inf",
        "min_p = -0.1",
        "min_p = 1.1",
        "min_p = 'SYNTHETIC_VALUE'",
        "track = 'SYNTHETIC_UNKNOWN_TRACK'",
        "tracks_root = 12",
        "style_sheet = ''",
        "lexicon = false",
        "vault_dir = []",
        r"style_sheet = 'C:relative.md'",
        r"style_sheet = '\relative.md'",
        'style_sheet = "\\u0000"',
    ],
)
def test_invalid_settings_reject_before_sources_even_with_cli_overrides(
    tmp_path: Path,
    content: str,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    config = _settings(tmp_path, "# SYNTHETIC_SETTINGS_SENTINEL\n" + content)
    monkeypatch.setattr(Path, "read_bytes", _blocked)
    monkeypatch.setattr(Path, "read_text", _blocked)
    monkeypatch.setattr(cli.VaultConfig, "load", _blocked)
    monkeypatch.setattr(cli, "OpenRouterClient", _blocked)
    assert (
        cli.main(
            [
                "missing-synthetic-frame.md",
                "--config",
                str(config),
                "--language",
                "sk",
                "--candidates",
                "3",
                "--model",
                MAGNUM,
                "--temp",
                "0.68",
                "--min-p",
                "0.06",
                "--dry-run",
            ]
        )
        == 2
    )
    output = capsys.readouterr()
    assert "[FAIL] TOML" in output.err
    assert "SYNTHETIC" not in output.out + output.err
    assert "Traceback" not in output.err


def test_recursive_settings_reject_before_consumption_even_with_cli_selector_override(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    depth = max(2000, sys.getrecursionlimit() * 2)
    config = _settings(
        tmp_path, "models = " + "[" * depth + "'SYNTHETIC_RECURSION_SENTINEL'" + "]" * depth
    )
    vault = tmp_path / "unconsumed-synthetic-vault"
    monkeypatch.setattr(Path, "read_bytes", _blocked)
    monkeypatch.setattr(Path, "read_text", _blocked)
    monkeypatch.setattr(cli, "_resource_paths", _blocked)
    monkeypatch.setattr(cli.VaultConfig, "load", _blocked)
    monkeypatch.setattr(cli, "OpenRouterClient", _blocked)
    monkeypatch.setattr(cli, "render_outputs", _blocked)
    monkeypatch.setattr(cli, "render_arena", _blocked)
    assert (
        cli.main(
            [
                str(tmp_path / "missing-synthetic-frame.md"),
                "--config",
                str(config),
                "--model",
                MAGNUM,
                "--vault-dir",
                str(vault),
                "--dry-run",
            ]
        )
        == 2
    )
    output = capsys.readouterr()
    assert not output.out
    assert output.err.startswith("[FAIL] TOML")
    assert "SYNTHETIC_RECURSION_SENTINEL" not in output.err
    assert "Traceback" not in output.err
    assert not vault.exists()


@pytest.mark.parametrize(
    "failure", ["missing", "directory", "extension", "syntax", "utf8", "numeric", "denied"]
)
def test_settings_file_failures_are_redacted(
    tmp_path: Path,
    failure: str,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    path = tmp_path / "SYNTHETIC_SETTINGS_SENTINEL.toml"
    if failure == "directory":
        path.mkdir()
    elif failure == "extension":
        path = path.with_suffix(".env")
        path.write_text("SYNTHETIC_SETTINGS_SENTINEL", encoding="utf-8")
    elif failure == "syntax":
        path.write_text(
            "language = 'en'\nlanguage = 'SYNTHETIC_SETTINGS_SENTINEL'", encoding="utf-8"
        )
    elif failure == "utf8":
        path.write_bytes(b"\xffSYNTHETIC_SETTINGS_SENTINEL")
    elif failure == "numeric":
        path.write_text("# SYNTHETIC_SETTINGS_SENTINEL\ntemp = " + "9" * 5000, encoding="utf-8")
    elif failure == "denied":

        def denied(*args: object, **kwargs: object) -> None:
            raise PermissionError("SYNTHETIC_SETTINGS_SENTINEL")

        monkeypatch.setattr(Path, "open", denied)
    assert cli.main(["missing-frame.md", "--config", str(path), "--dry-run"]) == 2
    output = capsys.readouterr()
    assert "[FAIL] TOML" in output.err
    assert "SYNTHETIC_SETTINGS_SENTINEL" not in output.out + output.err


@pytest.mark.parametrize(
    ("content", "flags", "message"),
    [
        ("language = 'en'\nlexicon = 'missing.md'", [], "--lexicon is Slovak-only"),
        (f"models = ['{MAGNUM}', '{EURYALE}']", ["--lint-only", "missing.txt"], "--models cannot"),
        (f"models = ['{MAGNUM}', '{EURYALE}']\ncandidates = 5", [], "nine initial"),
        (f"models = ['{MAGNUM}', '{DEEPSEEK}']\nmin_p = 0.06", [], "--min-p requires"),
        ("track = 'blog'", [], "--track and --tracks-root"),
        ("tracks_root = 'missing-root'", [], "--track and --tracks-root"),
    ],
)
def test_invalid_effective_combinations_reject_before_sources(
    tmp_path: Path,
    content: str,
    flags: list[str],
    message: str,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    config = _settings(tmp_path, content)
    monkeypatch.setattr(Path, "read_bytes", _blocked)
    monkeypatch.setattr(cli.VaultConfig, "load", _blocked)
    assert cli.main(["missing-frame.md", "--config", str(config), *flags]) == 2
    assert message in capsys.readouterr().err


@pytest.mark.parametrize("matrix", [False, True])
def test_cli_replaces_the_entire_configured_model_selector(
    tmp_path: Path,
    cli_args: list[str],
    vault: Path,
    mock_api: list[httpx.Request],
    matrix: bool,
) -> None:
    content = f"model = '{EURYALE}'" if matrix else f"models = ['{MAGNUM}', '{EURYALE}']"
    config = _settings(tmp_path, content + "\ncandidates = 1\n")
    flags = ["--models", f"{MAGNUM},{EURYALE}"] if matrix else ["--model", MAGNUM]
    assert cli.main([*cli_args, "--config", str(config), *flags]) == 0
    assert sorted(json.loads(request.content)["model"] for request in mock_api) == (
        sorted([MAGNUM, EURYALE]) if matrix else [MAGNUM]
    )
    assert sorted(path.name for path in (vault / "output").iterdir()) == (
        ["frame.arena.json", "frame.arena.md"]
        if matrix
        else ["frame.candidates.md", "frame.merged.md"]
    )


@pytest.mark.parametrize("order", [False, True])
def test_explicit_model_conflicts_and_help_do_not_open_settings(
    order: bool, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(Path, "open", _blocked)
    monkeypatch.setattr(Path, "read_bytes", _blocked)
    single = ["--model", ModelParams().model]
    matrix = ["--models", f"{MAGNUM},{EURYALE}"]
    with pytest.raises(SystemExit) as conflict:
        cli.main(
            [
                "missing.md",
                "--config",
                "missing.toml",
                *(single + matrix if order else matrix + single),
            ]
        )
    assert conflict.value.code == 2
    with pytest.raises(SystemExit) as help_exit:
        cli.main(
            ["--config", "missing.env", "--help"]
            if order
            else ["--help", "--config", "missing.env"]
        )
    assert help_exit.value.code == 0


@pytest.mark.parametrize(
    "selection", ["cli", "environment", "config", "legacy", "empty-environment"]
)
def test_vault_and_credential_precedence(
    tmp_path: Path,
    cli_args: list[str],
    mock_api: list[httpx.Request],
    selection: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    home = tmp_path / "synthetic-home"
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: home))
    vaults = {
        "cli": tmp_path / "cli-vault",
        "environment": tmp_path / "environment-vault",
        "config": tmp_path / "config-vault",
        "legacy": home / "zafo-local",
        "empty-environment": tmp_path / "empty-environment-vault",
    }
    for path in vaults.values():
        path.mkdir(parents=True)
        (path / ".env").write_text("OPENROUTER_API_KEY=synthetic-file-key\n", encoding="utf-8")
        (path / "TIER4_ADDON.txt").write_text("Benign synthetic addon.", encoding="utf-8")
    content = "candidates = 1\n"
    if selection != "legacy":
        content += "vault_dir = '..\\config-vault'\n"
    config = _settings(tmp_path / "settings", content)
    args = _without(cli_args, "--vault-dir")
    if selection == "cli":
        args += ["--vault-dir", str(vaults["cli"])]
    if selection in ("cli", "environment"):
        monkeypatch.setenv("ZAFO_VAULT_DIR", str(vaults["environment"]))
        monkeypatch.setenv("OPENROUTER_API_KEY", "synthetic-process-key")
    else:
        monkeypatch.setenv("OPENROUTER_API_KEY", "")
    if selection == "empty-environment":
        monkeypatch.setenv("ZAFO_VAULT_DIR", "")
        monkeypatch.chdir(vaults["empty-environment"])
    assert cli.main([*args, "--config", str(config)]) == 0
    for name, path in vaults.items():
        assert (path / "output").exists() is (name == selection)
    expected_key = (
        "synthetic-process-key" if selection in ("cli", "environment") else "synthetic-file-key"
    )
    assert mock_api[0].headers["Authorization"] == "Bearer " + expected_key


@pytest.mark.parametrize("origin", ["config-root", "config-track", "override-track"])
def test_track_pairing_uses_effective_values_and_config_relative_paths(
    tmp_path: Path,
    tracks_root: Path,
    vault: Path,
    origin: str,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    content = "language = 'en'\n"
    flags = ["--vault-dir", str(vault)]
    if origin != "config-track":
        content += "tracks_root = '..\\synthetic-tracks'\n"
        flags += ["--track", "serial"]
    else:
        flags += ["--tracks-root", str(tracks_root)]
    if origin != "config-root":
        content += f"track = '{'blog' if origin == 'override-track' else 'serial'}'\n"
    config = _settings(tmp_path / "settings", content)
    elsewhere = tmp_path / "other-working-directory"
    elsewhere.mkdir()
    monkeypatch.chdir(elsewhere)
    source = tracks_root / "serial" / "episodes" / "nested" / "frame_en.md"
    assert (
        cli.main([str(source), "--config", "..\\settings\\settings.toml", *flags, "--dry-run"]) == 0
    )
    output = capsys.readouterr().out
    assert "track=serial; style=track-default; lexicon=none" in output
    assert "SYNTHETIC_STYLE" not in output
    assert not (vault / "output").exists()
    assert config.read_text(encoding="utf-8") == content


@pytest.mark.parametrize("path_kind", ["relative", "home", "literal-variable"])
def test_config_resource_paths_do_not_use_cwd_or_expand_environment_variables(
    tmp_path: Path,
    english_cli_args: list[str],
    fixtures: Path,
    path_kind: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    directory = tmp_path / "settings"
    directory.mkdir()
    if path_kind == "home":
        monkeypatch.setenv("USERPROFILE", str(tmp_path))
        monkeypatch.setenv("HOME", str(tmp_path))
        style = tmp_path / "style.md"
        setting = "~/style.md"
    else:
        setting = (
            "%SYNTHETIC_STYLE%$SYNTHETIC_STYLE" if path_kind == "literal-variable" else "style.md"
        )
        style = directory / setting
        monkeypatch.setenv("SYNTHETIC_STYLE", str(tmp_path / "missing-style.md"))
    style.write_bytes((fixtures / "STYLE_SHEET_EN.md").read_bytes())
    config = _settings(directory, f"style_sheet = '{setting}'")
    args = _without(english_cli_args, "--style-sheet")
    monkeypatch.chdir(tmp_path)
    assert cli.main([*args, "--config", str(config), "--dry-run"]) == 0
    override = tmp_path / "override.md"
    override.write_bytes((fixtures / "STYLE_SHEET_EN.md").read_bytes())
    style.unlink()
    assert (
        cli.main([*args, "--config", str(config), "--style-sheet", "override.md", "--dry-run"]) == 0
    )


@pytest.mark.skipif(os.name != "nt", reason="Windows junction settings pathname origin")
def test_linked_settings_consume_resources_from_selected_pathname_directory(
    tmp_path: Path,
    english_cli_args: list[str],
    fixtures: Path,
    mock_api: list[httpx.Request],
) -> None:
    assert tmp_path.drive.casefold() == "c:"
    selected = tmp_path / "selected"
    selected.mkdir()
    target = tmp_path / "target" / "config"
    _settings(target, "style_sheet = '..\\style.md'\ncandidates = 1\n")
    style = (fixtures / "STYLE_SHEET_EN.md").read_text(encoding="utf-8")
    for directory, marker in ((selected, "SELECTED_PATHNAME"), (target.parent, "LINK_TARGET")):
        (directory / "style.md").write_text(
            style.replace(
                "## 1. Pinned Golden Voice Sample\n",
                f"## 1. Pinned Golden Voice Sample\n\nSYNTHETIC_{marker}_STYLE\n",
                1,
            ),
            encoding="utf-8",
        )
    link = selected / "config"
    subprocess.run(
        [
            "pwsh",
            "-NoProfile",
            "-Command",
            f"New-Item -ItemType Junction -Path '{link}' -Target '{target}' "
            "-ErrorAction Stop | Out-Null",
        ],
        check=True,
        capture_output=True,
        timeout=30,
    )
    try:
        config = link / "settings.toml"
        assert link.is_junction()
        assert config.parent != config.resolve(strict=True).parent
        args = _without(english_cli_args, "--style-sheet")
        assert cli.main([*args, "--config", str(config)]) == 0
        assert len(mock_api) == 1
        messages = json.loads(mock_api[0].content)["messages"]
        consumed = "\n".join(message["content"] for message in messages)
        assert "SYNTHETIC_SELECTED_PATHNAME_STYLE" in consumed
        assert "SYNTHETIC_LINK_TARGET_STYLE" not in consumed
    finally:
        link.rmdir()


def test_config_lint_only_never_inspects_vault_or_styles(
    tmp_path: Path,
    english_cli_args: list[str],
    fixtures: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    unused = Path(r"D:\synthetic-forbidden-but-unused")
    config = _settings(
        tmp_path, f"vault_dir = '{unused}'\nstyle_sheet = 'missing-unused-style.md'\n"
    )
    args = _without(_without(english_cli_args, "--vault-dir"), "--style-sheet")
    original_resolve = Path.resolve
    original_stat = Path.stat

    def resolve(path: Path, strict: bool = False) -> Path:
        if path == unused or unused in path.parents:
            raise AssertionError("Lint-only must not resolve the configured vault.")
        return original_resolve(path, strict=strict)

    def stat(path: Path, *, follow_symlinks: bool = True) -> os.stat_result:
        if path == unused or unused in path.parents:
            raise AssertionError("Lint-only must not stat the configured vault.")
        return original_stat(path, follow_symlinks=follow_symlinks)

    monkeypatch.setattr(Path, "resolve", resolve)
    monkeypatch.setattr(Path, "stat", stat)
    monkeypatch.setattr(cli.VaultConfig, "load", _blocked)
    monkeypatch.setattr(cli, "OpenRouterClient", _blocked)
    assert (
        cli.main(
            [
                *args,
                "--config",
                str(config),
                "--lint-only",
                str(fixtures / "candidate_en.txt"),
                "--strict",
            ]
        )
        == 0
    )


def test_config_dry_run_never_reads_private_files_calls_http_or_writes(
    tmp_path: Path,
    cli_args: list[str],
    vault: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    config = _settings(tmp_path, f"models = [' {MAGNUM} ', ' {EURYALE} ']\ncandidates = 1")
    for name in (".env", "TIER4_ADDON.txt"):
        (vault / name).write_bytes(b"\xff")
    sources = [Path(cli_args[0]), Path(cli_args[2]), Path(cli_args[4]), config]
    before = {path: hashlib.sha256(path.read_bytes()).digest() for path in sources}
    private_files = {vault / ".env", vault / "TIER4_ADDON.txt"}

    def guard_private_open(file: object, *args: object, **kwargs: object) -> object:
        if isinstance(file, (str, bytes, os.PathLike)):
            if Path(os.fsdecode(file)).absolute() in private_files:
                raise AssertionError("Dry-run must not open credentials or addons.")
        return DEFAULT

    for module in (builtins, io, os):
        monkeypatch.setattr(module, "open", Mock(wraps=module.open, side_effect=guard_private_open))
    monkeypatch.setattr(cli, "OpenRouterClient", _blocked)
    monkeypatch.setattr(cli, "render_outputs", _blocked)
    monkeypatch.setattr(cli, "render_arena", _blocked)
    assert cli.main([*cli_args, "--config", str(config), "--dry-run", "--print-output"]) == 0
    output = capsys.readouterr()
    assert "addon and credentials not read; no API or writes" in output.out
    assert "Benign synthetic addon" not in output.out + output.err
    assert not (vault / "output").exists()
    assert {path: hashlib.sha256(path.read_bytes()).digest() for path in sources} == before
