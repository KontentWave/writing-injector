import json
import os
import shutil
import subprocess
import sys
from io import BytesIO
from pathlib import Path
from zipfile import ZipFile

import pytest

from zafo_injector.config import validate_storage_path

LAUNCHER = Path(__file__).resolve().parents[2] / "writing-injector.ps1"


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


def _prepare_launcher(
    tmp_path: Path, *, fake: bool = True, exit_code: int = 0
) -> tuple[Path, Path]:
    if os.name != "nt":
        pytest.skip("Launcher coverage requires a Windows console executable.")
    assert tmp_path.drive.casefold() == "c:"
    assert validate_storage_path(tmp_path, LAUNCHER.parent) == tmp_path
    launcher = tmp_path / "launcher" / LAUNCHER.name
    launcher.parent.mkdir()
    shutil.copyfile(LAUNCHER, launcher)
    executable = launcher.parent / ".venv" / "Scripts" / "zafo-inject.exe"
    executable.parent.mkdir(parents=True)
    installed = Path(sys.executable).with_name("zafo-inject.exe")
    if not fake:
        shutil.copyfile(installed, executable)
        return launcher, executable

    # Preserve the native stub/shebang and ZIP-relative offsets expected by its loader.
    with ZipFile(installed) as archive:
        assert "__main__.py" in archive.namelist()
        offset = min(entry.header_offset for entry in archive.infolist())
    payload = BytesIO()
    with ZipFile(payload, "w") as archive:
        archive.writestr(
            "__main__.py",
            "import json, os, sys\n"
            "from pathlib import Path\n"
            "Path(sys.argv[0]).with_suffix('.json').write_text("
            "json.dumps({'args': sys.argv[1:], 'cwd': os.getcwd()}), encoding='utf-8')\n"
            "print('SYNTHETIC_LAUNCHER_STDOUT')\n"
            "print('SYNTHETIC_LAUNCHER_STDERR', file=sys.stderr)\n"
            f"raise SystemExit({exit_code})\n",
        )
    executable.write_bytes(installed.read_bytes()[:offset] + payload.getvalue())
    return launcher, executable


def _run_launcher(
    launcher: Path,
    args: list[str] | None = None,
    *,
    generate: bool = False,
    process_dir: Path | None = None,
    location: Path | None = None,
) -> subprocess.CompletedProcess[str]:
    pwsh = shutil.which("pwsh")
    assert pwsh is not None, "PowerShell 7 is required; launcher coverage must not be skipped."
    process_dir = process_dir or launcher.parent
    location = location or process_dir
    invocation = launcher.parent / "invocation.json"
    invocation.write_text(
        json.dumps(
            {
                "launcher": str(launcher),
                "args": args,
                "include_args": args is not None,
                "generate": generate,
                "location": str(location),
            }
        ),
        encoding="utf-8",
    )
    quoted_invocation = str(invocation).replace("'", "''")
    command = (
        "$ErrorActionPreference = 'Stop'; "
        f"$invocation = Get-Content -Raw -LiteralPath '{quoted_invocation}' | ConvertFrom-Json; "
        "Set-Location -LiteralPath $invocation.location; "
        "$before = (Get-Location).ProviderPath; "
        "$parameters = @{}; "
        "if ($invocation.include_args) { $parameters.CliArgs = [string[]]$invocation.args }; "
        "if ($invocation.generate) { $parameters.Generate = $true }; "
        "& $invocation.launcher @parameters; $code = $LASTEXITCODE; "
        "if ((Get-Location).ProviderPath -cne $before) { "
        "throw 'Launcher changed the caller location.' }; exit $code"
    )
    env = os.environ.copy()
    for name in (
        "OPENROUTER_API_KEY",
        "ZAFO_VAULT_DIR",
        "GOOGLE_DRIVE_DIR",
        "PYTHONPATH",
        "PYTHONHOME",
        "PYTEST_PLUGINS",
    ):
        env.pop(name, None)
    env.update(
        PYTHONDONTWRITEBYTECODE="1",
        TEMP=str(launcher.parent),
        TMP=str(launcher.parent),
        TMPDIR=str(launcher.parent),
        PATH=str(Path(sys.executable).parent) + os.pathsep + env.get("PATH", ""),
    )
    return subprocess.run(
        [pwsh, "-NoProfile", "-NonInteractive", "-Command", command],
        cwd=process_dir,
        capture_output=True,
        encoding="utf-8",
        env=env,
        timeout=30,
    )


@pytest.mark.parametrize(
    ("args", "generate", "expected"),
    [
        (None, False, ["--help"]),
        ([], False, ["--help"]),
        ([""], False, ["--dry-run", ""]),
        (["--", "--lint-only"], False, ["--dry-run", "--", "--lint-only"]),
        (["frame.md"], False, ["--dry-run", "frame.md"]),
        (["frame.md"], True, ["frame.md"]),
        (["frame.md", "--dry-run"], False, ["frame.md", "--dry-run"]),
        (["frame.md", "--dry-run"], True, ["frame.md", "--dry-run"]),
        (
            ["frame.md", "--lint-only", "candidate.txt"],
            False,
            ["frame.md", "--lint-only", "candidate.txt"],
        ),
        (
            ["frame.md", "--lint-only=candidate.txt"],
            True,
            ["frame.md", "--lint-only=candidate.txt"],
        ),
        (["--help"], True, ["--help"]),
        (["-h"], False, ["-h"]),
        (
            ["frame.md", "--print-output"],
            False,
            ["--dry-run", "frame.md", "--print-output"],
        ),
        (["frame.md", "--print-output"], True, ["frame.md", "--print-output"]),
    ],
)
def test_powershell_launcher_dispatch(
    tmp_path: Path, args: list[str] | None, generate: bool, expected: list[str]
) -> None:
    launcher, executable = _prepare_launcher(tmp_path)
    result = _run_launcher(launcher, args, generate=generate)
    assert result.returncode == 0, result.stdout + result.stderr
    assert result.stdout == "SYNTHETIC_LAUNCHER_STDOUT\n"
    assert result.stderr == "SYNTHETIC_LAUNCHER_STDERR\n"
    assert (
        json.loads(executable.with_suffix(".json").read_text(encoding="utf-8"))["args"] == expected
    )


def test_powershell_launcher_exact_tokens_location_and_child_failure(tmp_path: Path) -> None:
    launcher, executable = _prepare_launcher(tmp_path, exit_code=37)
    process_dir = tmp_path / "original-process-directory"
    caller = tmp_path / "caller's location"
    process_dir.mkdir()
    caller.mkdir()
    args = [
        r".\relative frame.md",
        "--model=--dry-run",
        "--config=--help",
        "--style-sheet=--lint-only",
        "",
        "double \"quotes\" and 'single quotes'",
        "trailing slash\\",
        "; & | < > $() ` $(throw 'must not evaluate')",
        "-Generate",
        "--",
        "--help",
        "--dry-run",
        "--lint-only",
        "--print-output",
    ]
    result = _run_launcher(launcher, args, process_dir=process_dir, location=caller)
    assert result.returncode == 37, result.stdout + result.stderr
    assert result.stdout == "SYNTHETIC_LAUNCHER_STDOUT\n"
    assert result.stderr == "SYNTHETIC_LAUNCHER_STDERR\n"
    record = json.loads(executable.with_suffix(".json").read_text(encoding="utf-8"))
    assert record["args"] == ["--dry-run", *args]
    assert Path(record["cwd"]) == caller


@pytest.mark.parametrize("mode", ["bare", "help", "dry", "lint"])
def test_powershell_launcher_real_offline_modes(tmp_path: Path, fixtures: Path, mode: str) -> None:
    launcher, _ = _prepare_launcher(tmp_path, fake=False)
    caller = tmp_path / "caller"
    caller.mkdir()
    source = caller / "frame.md"
    original = b"\xef\xbb\xbf" + (fixtures / "frame_en.md").read_bytes().replace(b"\n", b"\r\n")
    source.write_bytes(original)
    before = source.stat().st_mtime_ns
    (caller / "style.md").write_bytes((fixtures / "STYLE_SHEET_EN.md").read_bytes())
    candidate = caller / "candidate.txt"
    candidate.write_bytes((fixtures / "candidate_en.txt").read_bytes())
    vault = tmp_path / "synthetic-vault"
    vault.mkdir()
    (vault / ".env").write_bytes(b"\xff")
    (vault / "TIER4_ADDON.txt").write_bytes(b"\xff")
    (caller / "defaults.toml").write_text(
        "language = 'en'\nstyle_sheet = 'style.md'\nvault_dir = '..\\synthetic-vault'\n",
        encoding="utf-8",
    )
    args = [r".\frame.md", "--config", r".\defaults.toml"]
    if mode == "bare":
        args = None
    elif mode == "help":
        args = ["--config", "missing-synthetic-settings.toml", "--help"]
    elif mode == "dry":
        args += ["--print-output"]
    else:
        args += ["--lint-only", r".\candidate.txt"]
    result = _run_launcher(launcher, args, location=caller)
    output = result.stdout + result.stderr
    assert result.returncode == 0, output
    assert "Traceback" not in output
    if mode in ("bare", "help"):
        assert "--config FILE" in output
    else:
        assert "[PASS]" in output
        assert "language=en" in output
    assert candidate.read_text(encoding="utf-8").strip() not in output
    assert source.read_bytes() == original
    assert source.stat().st_mtime_ns == before
    assert sorted(path.name for path in vault.iterdir()) == [".env", "TIER4_ADDON.txt"]


@pytest.mark.parametrize("failure", ["empty-generation", "missing-runtime", "launch-failure"])
def test_powershell_launcher_usage_and_runtime_failures(tmp_path: Path, failure: str) -> None:
    launcher, executable = _prepare_launcher(tmp_path)
    args = ["--help"]
    if failure == "missing-runtime":
        executable.unlink()
    elif failure == "launch-failure":
        executable.write_bytes(b"not an executable")
        args = ["SYNTHETIC_ARGUMENT_MUST_NOT_BE_ECHOED"]
    result = _run_launcher(
        launcher,
        [] if failure == "empty-generation" else args,
        generate=failure == "empty-generation",
    )
    assert result.returncode == 2, result.stdout + result.stderr
    assert result.stdout == ""
    assert "[FAIL]" in result.stderr
    assert "SYNTHETIC_ARGUMENT_MUST_NOT_BE_ECHOED" not in result.stderr
    assert not executable.with_suffix(".json").exists()
