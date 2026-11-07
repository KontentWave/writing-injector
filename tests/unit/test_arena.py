import hashlib
import json
import os
import threading
from collections.abc import Iterator
from dataclasses import replace
from pathlib import Path

import httpx
import pytest

from zafo_injector import cli
from zafo_injector import renderer as renderer_module
from zafo_injector.config import AirGapViolationError
from zafo_injector.model_profiles import select_model_profiles
from zafo_injector.models import (
    ArenaCandidate,
    ArenaRun,
    CandidateResponse,
    FrameDocument,
    Language,
    ModelParams,
    RequestFailure,
)
from zafo_injector.openrouter_client import OpenRouterClient
from zafo_injector.renderer import OutputError, render_arena
from zafo_injector.slovak_lint import LexiconRules, lint_candidate

WORKSPACE = Path(__file__).resolve().parents[2]
MAGNUM = "anthracite-org/magnum-v4-72b"
DEEPSEEK = "deepseek/deepseek-chat-v3-0324"
EURYALE = "sao10k/l3.1-euryale-70b"
ROSTER = f"{MAGNUM},{DEEPSEEK},{EURYALE}"


@pytest.fixture
def arena_api(
    monkeypatch: pytest.MonkeyPatch, candidate: str, english_candidate: str
) -> Iterator[list[httpx.Request]]:
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        system = json.loads(request.content)["messages"][0]["content"]
        text = english_candidate if "Write only in English" in system else candidate
        return httpx.Response(200, json={"choices": [{"message": {"content": text}}]})

    with httpx.Client(transport=httpx.MockTransport(handler)) as transport:
        monkeypatch.setattr(
            cli,
            "OpenRouterClient",
            lambda key: OpenRouterClient(key, client=transport, sleep=lambda _: None),
        )
        yield requests


@pytest.mark.parametrize("language", ["sk", "en"])
@pytest.mark.parametrize("bom", [False, True])
def test_matrix_complete_schema_sources_and_report_only_behavior(
    language: Language,
    bom: bool,
    fixtures: Path,
    tmp_path: Path,
    vault: Path,
    candidate: str,
    english_candidate: str,
    arena_api: list[httpx.Request],
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    blog = tmp_path / "synthetic-blog"
    posts, docs = blog / "posts", blog / "docs"
    posts.mkdir(parents=True)
    docs.mkdir()
    source = posts / "post.md"
    frame_name = "frame_en.md" if language == "en" else "frame.md"
    original = (
        (fixtures / frame_name).read_text(encoding="utf-8").replace("\n", "\r\n").encode("utf-8")
    )
    original = (b"\xef\xbb\xbf" if bom else b"") + original
    source.write_bytes(original)
    style = docs / "STYLE_SHEET.md"
    style_name = "STYLE_SHEET_EN.md" if language == "en" else "STYLE_SHEET.md"
    style.write_bytes((fixtures / style_name).read_bytes())
    lexicon = docs / "SLOVAK_LEXICON.md"
    lexicon.write_bytes(b"\xff" if language == "en" else (fixtures / lexicon.name).read_bytes())
    if language == "en":

        def blocked(*args: object, **kwargs: object) -> None:
            raise AssertionError("English matrix must not load a Slovak lexicon.")

        monkeypatch.setattr(LexiconRules, "from_markdown", blocked)
    inputs = (source, style, lexicon, vault / ".env", vault / "TIER4_ADDON.txt")
    before = {
        path: (hashlib.sha256(path.read_bytes()).digest(), path.stat().st_mtime_ns)
        for path in inputs
    }
    args = [
        str(source),
        "--vault-dir",
        str(vault),
        "--models",
        ROSTER,
        "--candidates",
        "2",
        "--strict",
    ]
    if language == "en":
        args += ["--language", "en"]
    assert cli.main(args) == 0
    assert len(arena_api) == 6
    payloads = [json.loads(request.content) for request in arena_api]
    assert all(payload["messages"] == payloads[0]["messages"] for payload in payloads)
    system = payloads[0]["messages"][0]["content"]
    assert f"Write only in {'English' if language == 'en' else 'Slovak'}" in system
    assert "Word bounds: 20-80 words, inclusive." in system
    assert "Aim for 50 words." in system
    assert "Benign synthetic addon." in system
    assert all(
        hashlib.sha256(path.read_bytes()).digest() == digest and path.stat().st_mtime_ns == modified
        for path, (digest, modified) in before.items()
    )
    output = vault / "output"
    assert sorted(path.name for path in output.iterdir()) == ["post.arena.json", "post.arena.md"]
    raw_metadata = (output / "post.arena.json").read_text(encoding="utf-8")
    metadata = json.loads(raw_metadata)
    assert set(metadata) == {
        "schema_version",
        "mode",
        "status",
        "exit_code",
        "strict",
        "language",
        "pov",
        "bounds",
        "qa",
        "execution",
        "models",
    }
    assert metadata["schema_version"] == 1 and metadata["mode"] == "arena"
    assert metadata["status"] == "completed" and metadata["exit_code"] == 0
    assert metadata["strict"] is True and metadata["language"] == language
    assert metadata["bounds"] == {
        "min_words": 20,
        "max_words": 80,
        "min_paragraphs": 2,
        "max_paragraphs": 4,
    }
    assert metadata["execution"] == {
        "candidates_per_model": 2,
        "initial_requests": 6,
        "initial_request_limit": 9,
        "http_attempts": 6,
        "http_attempt_budget": 18,
        "concurrency_cap": 3,
        "timeout_seconds": 45,
        "max_retries": 2,
        "retry_backoff_seconds": [0.5, 1.0],
    }
    assert metadata["qa"]["score_formula"] == "100 - 25 * errors - 5 * warnings"
    assert "not grammar, prose quality" in metadata["qa"]["limitations"]
    expected_words = 50 if language == "en" else 37
    for model, profile in zip(metadata["models"], select_model_profiles(ROSTER), strict=True):
        assert set(model) == {
            "model_id",
            "status",
            "sampling",
            "omitted_sampling_parameters",
            "provider",
            "scorecard",
            "candidates",
        }
        assert model["model_id"] == profile.model_id and model["status"] == "hard_pass"
        assert model["sampling"] == profile.sampling_parameters()
        assert model["provider"] == profile.provider_settings()
        assert model["omitted_sampling_parameters"] == list(profile.omitted_parameters)
        assert model["scorecard"] == {
            "requested": 2,
            "succeeded": 2,
            "api_failed": 0,
            "hard_pass_count": 2,
            "hard_pass_rate_requested": 1.0,
            "hard_error_count": 0,
            "warning_count": 0,
        }
        for index, result in enumerate(model["candidates"], 1):
            assert result == {
                "candidate_id": f"{profile.model_id}::candidate-{index}",
                "index": index,
                "status": "hard_pass",
                "attempts": 1,
                "score": 100,
                "word_count": expected_words,
                "paragraph_count": 2,
                "hard_pass": True,
                "hard_error_count": 0,
                "warning_count": 0,
                "issues": [],
                "failure": None,
            }
    review = (output / "post.arena.md").read_text(encoding="utf-8")
    text = english_candidate if language == "en" else candidate
    assert review.count(text) == 6
    assert "no winner selected and no merged draft" in review
    assert "Sampling differences are recorded" in review
    assert "## Model " + MAGNUM in review
    captured = capsys.readouterr()
    assert "no winner or merged draft" in captured.out
    for sentinel in (text, "synthetic-test-key", "Benign synthetic addon."):
        assert sentinel not in captured.out + captured.err
        assert sentinel not in raw_metadata
    assert "Benign synthetic addon." not in review
    assert "synthetic-test-key" not in review


@pytest.mark.parametrize("language", ["sk", "en"])
@pytest.mark.parametrize("strict", [False, True])
@pytest.mark.parametrize("kind", ["partial-api", "all-api", "one-model-lint", "all-lint", "mixed"])
def test_matrix_failure_policy_retains_every_candidate_and_redacts(
    language: Language,
    strict: bool,
    kind: str,
    cli_args: list[str],
    english_cli_args: list[str],
    vault: Path,
    candidate: str,
    english_candidate: str,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    calls: dict[str, int] = {}
    lock = threading.Lock()
    good = english_candidate if language == "en" else candidate

    def handler(request: httpx.Request) -> httpx.Response:
        model = json.loads(request.content)["model"]
        with lock:
            calls[model] = calls.get(model, 0) + 1
            index = calls[model]
        if kind == "all-api" or (kind == "partial-api" and model == DEEPSEEK):
            return httpx.Response(401, text="SYNTHETIC_REMOTE_SECRET")
        bad = (
            kind == "all-lint"
            or (kind == "one-model-lint" and model == DEEPSEEK)
            or (kind == "mixed" and index == 1)
        )
        text = "SYNTHETIC_MATCH_SENTINEL" if bad else good
        return httpx.Response(200, json={"choices": [{"message": {"content": text}}]})

    args = (english_cli_args if language == "en" else cli_args) + [
        "--models",
        ROSTER,
        "--candidates",
        "2",
    ]
    if strict:
        args += ["--strict"]
    has_api_failure = kind in ("partial-api", "all-api")
    strict_failure = strict and kind in ("one-model-lint", "all-lint")
    expected_exit = 4 if has_api_failure else 5 if strict_failure else 0
    expected_status = (
        "api_failed" if has_api_failure else "strict_lint_failed" if strict_failure else "completed"
    )
    with httpx.Client(transport=httpx.MockTransport(handler)) as transport:
        monkeypatch.setattr(
            cli, "OpenRouterClient", lambda key: OpenRouterClient(key, client=transport)
        )
        assert cli.main(args) == expected_exit
    assert calls == {MAGNUM: 2, DEEPSEEK: 2, EURYALE: 2}
    stem = "frame_en" if language == "en" else "frame"
    metadata = json.loads((vault / "output" / f"{stem}.arena.json").read_text(encoding="utf-8"))
    assert metadata["status"] == expected_status and metadata["exit_code"] == expected_exit
    assert metadata["execution"]["http_attempts"] == 6
    assert metadata["execution"]["http_attempt_budget"] == 18
    for model in metadata["models"]:
        assert len(model["candidates"]) == 2
        failed_api = kind == "all-api" or (kind == "partial-api" and model["model_id"] == DEEPSEEK)
        for index, result in enumerate(model["candidates"], 1):
            assert result["candidate_id"] == f"{model['model_id']}::candidate-{index}"
            if failed_api:
                assert result["status"] == "api_failed"
                for metric in (
                    "score",
                    "word_count",
                    "paragraph_count",
                    "hard_pass",
                    "hard_error_count",
                    "warning_count",
                    "issues",
                ):
                    assert result[metric] is None
                assert result["failure"] == {
                    "code": "http_error",
                    "http_status": 401,
                    "message": "OpenRouter request failed (HTTP 401).",
                }
            else:
                assert result["failure"] is None
                assert result["score"] in (50, 100)
                assert result["hard_pass"] == (result["score"] == 100)
        if kind == "mixed":
            assert model["scorecard"]["hard_pass_count"] == 1
            assert model["scorecard"]["hard_pass_rate_requested"] == 0.5
    captured = capsys.readouterr()
    assert "status=" + expected_status in captured.out
    for value in (
        "SYNTHETIC_MATCH_SENTINEL",
        "SYNTHETIC_REMOTE_SECRET",
        good,
        "synthetic-test-key",
        "Use 2-4 paragraphs",
    ):
        assert value not in captured.out + captured.err
    if expected_exit:
        assert "[FAIL] Arena report published:" in captured.out
    assert sorted(path.name for path in (vault / "output").iterdir()) == [
        f"{stem}.arena.json",
        f"{stem}.arena.md",
    ]


@pytest.mark.parametrize("count", [19, 20, 80, 81, 90, 99])
@pytest.mark.parametrize("strict", [False, True])
def test_matrix_exact_word_bounds_never_truncate_or_relax(
    count: int,
    strict: bool,
    english_cli_args: list[str],
    vault: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    text = " ".join(["tea"] * (count // 2)) + "\n\n" + " ".join(["tea"] * (count - count // 2))
    with httpx.Client(
        transport=httpx.MockTransport(
            lambda request: httpx.Response(200, json={"choices": [{"message": {"content": text}}]})
        )
    ) as transport:
        monkeypatch.setattr(
            cli, "OpenRouterClient", lambda key: OpenRouterClient(key, client=transport)
        )
        assert cli.main(
            english_cli_args
            + ["--models", f"{MAGNUM},{EURYALE}", "--candidates", "1"]
            + (["--strict"] if strict else [])
        ) == (5 if strict and not 20 <= count <= 80 else 0)
    metadata = json.loads((vault / "output" / "frame_en.arena.json").read_text(encoding="utf-8"))
    assert metadata["bounds"]["min_words"] == 20 and metadata["bounds"]["max_words"] == 80
    assert all(
        model["candidates"][0]["word_count"] == count
        and model["candidates"][0]["hard_pass"] == (20 <= count <= 80)
        for model in metadata["models"]
    )
    assert (vault / "output" / "frame_en.arena.md").read_text(encoding="utf-8").count(text) == 2


def test_matrix_sentence_warnings_do_not_fail_strict_and_are_redacted(
    english_cli_args: list[str],
    vault: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    text = ("Warm tea. " * 5).strip() + "\n\n" + ("coffee " * 12).strip()
    with httpx.Client(
        transport=httpx.MockTransport(
            lambda request: httpx.Response(200, json={"choices": [{"message": {"content": text}}]})
        )
    ) as transport:
        monkeypatch.setattr(
            cli, "OpenRouterClient", lambda key: OpenRouterClient(key, client=transport)
        )
        assert (
            cli.main(english_cli_args + ["--models", ROSTER, "--candidates", "1", "--strict"]) == 0
        )
    metadata = json.loads((vault / "output" / "frame_en.arena.json").read_text(encoding="utf-8"))
    assert all(model["scorecard"]["warning_count"] == 1 for model in metadata["models"])
    assert all(model["candidates"][0]["score"] == 95 for model in metadata["models"])
    captured = capsys.readouterr()
    assert f"[WARN] Model {MAGNUM}, Candidate 1: PARAGRAPH_BOUNDS line=1" in captured.out
    for value in (text, "Warm tea", "Use at most 4 sentences"):
        assert value not in captured.out + captured.err


@pytest.mark.parametrize("print_output", [False, True])
def test_matrix_candidate_printing_is_explicit_and_includes_identities(
    cli_args: list[str],
    vault: Path,
    candidate: str,
    arena_api: list[httpx.Request],
    capsys: pytest.CaptureFixture[str],
    print_output: bool,
) -> None:
    args = (
        cli_args
        + ["--models", ROSTER, "--candidates", "2"]
        + (["--print-output"] if print_output else [])
    )
    assert cli.main(args) == 0
    output = capsys.readouterr().out
    assert output.count(candidate) == (6 if print_output else 0)
    if print_output:
        assert output.index("Arena report published:") < output.index(candidate)
        assert f"{DEEPSEEK}::candidate-2\n{candidate}" in output
    assert len(arena_api) == 6
    assert sorted(path.suffix for path in (vault / "output").iterdir()) == [".json", ".md"]


@pytest.mark.parametrize("language", ["sk", "en"])
def test_matrix_dry_run_is_offline_without_addon_credentials_or_output(
    cli_args: list[str],
    english_cli_args: list[str],
    vault: Path,
    language: Language,
    capsys: pytest.CaptureFixture[str],
) -> None:
    (vault / ".env").write_bytes(b"\xff")
    (vault / "TIER4_ADDON.txt").write_bytes(b"\xff")
    args = english_cli_args if language == "en" else cli_args
    assert cli.main(args + ["--models", ROSTER, "--dry-run", "--print-output"]) == 0
    captured = capsys.readouterr()
    assert "initial requests=9/9" in captured.out and "HTTP attempt budget=27" in captured.out
    assert "global concurrency cap=3" in captured.out
    assert (
        f"Model {DEEPSEEK}: temperature=0.68; top_p=0.9; omitted=min_p,repetition_penalty"
        in captured.out
    )
    assert "addon and credentials not read; no API or writes" in captured.out
    assert "language=" + language in captured.out
    assert not (vault / "output").exists()


@pytest.mark.parametrize(
    "flags",
    [
        ["--models", ROSTER, "--lint-only", "missing-synthetic-candidate.txt"],
        ["--models", MAGNUM],
        ["--models", f"{MAGNUM},sao10k/l3.3-euryale-70b"],
        ["--models", f"{MAGNUM}, {MAGNUM}"],
        ["--models", ROSTER, "--min-p", "0.06"],
        ["--models", ROSTER, "--candidates", "4"],
        ["--models", f"{MAGNUM},{EURYALE}", "--candidates", "5"],
        ["--models", ROSTER, "--temp", "nan"],
        ["--models", f"{MAGNUM},{EURYALE}", "--min-p", "nan"],
    ],
)
def test_matrix_argument_rejections_happen_before_file_or_vault_access(
    flags: list[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    def blocked(*args: object, **kwargs: object) -> None:
        raise AssertionError("Invalid matrix arguments must reject before file access.")

    monkeypatch.setattr(Path, "read_bytes", blocked)
    monkeypatch.setattr(Path, "read_text", blocked)
    mode = [] if "--lint-only" in flags else ["--dry-run"]
    assert cli.main(["missing-synthetic-frame.md", *flags, *mode]) == 2


@pytest.mark.parametrize("language", ["sk", "en"])
def test_cli_matrix_overrides_reach_every_supported_payload(
    language: Language,
    cli_args: list[str],
    english_cli_args: list[str],
    arena_api: list[httpx.Request],
    vault: Path,
) -> None:
    args = english_cli_args if language == "en" else cli_args
    assert (
        cli.main(
            args
            + [
                "--models",
                f"{EURYALE},{MAGNUM}",
                "--candidates",
                "1",
                "--temp",
                "0.4",
                "--min-p",
                "0.2",
            ]
        )
        == 0
    )
    assert len(arena_api) == 2
    for request in arena_api:
        payload = json.loads(request.content)
        assert payload["temperature"] == 0.4 and payload["min_p"] == 0.2
        assert payload["top_p"] == 0.9 and payload["repetition_penalty"] == 1.05
        assert payload["provider"]["require_parameters"] is True
    stem = "frame_en" if language == "en" else "frame"
    metadata = json.loads((vault / "output" / f"{stem}.arena.json").read_text(encoding="utf-8"))
    assert [model["model_id"] for model in metadata["models"]] == [EURYALE, MAGNUM]
    assert all(
        model["sampling"]["temperature"] == 0.4 and model["sampling"]["min_p"] == 0.2
        for model in metadata["models"]
    )


@pytest.mark.parametrize("language", ["sk", "en"])
def test_phase1_single_model_overrides_and_custom_ids_keep_legacy_payloads_and_outputs(
    language: Language,
    cli_args: list[str],
    english_cli_args: list[str],
    arena_api: list[httpx.Request],
    vault: Path,
) -> None:
    args = english_cli_args if language == "en" else cli_args
    assert (
        cli.main(
            args
            + [
                "--model",
                "synthetic/phase1-custom-model",
                "--candidates",
                "1",
                "--temp",
                "0.4",
                "--min-p",
                "0.2",
            ]
        )
        == 0
    )
    assert len(arena_api) == 1
    payload = json.loads(arena_api[0].content)
    assert payload["model"] == "synthetic/phase1-custom-model"
    assert payload["temperature"] == 0.4 and payload["min_p"] == 0.2
    assert payload["top_p"] == 0.9 and payload["repetition_penalty"] == 1.05
    assert payload["provider"] == {
        "quantizations": ["bf16", "fp16", "fp8"],
        "allow_fallbacks": True,
    }
    stem = "frame_en" if language == "en" else "frame"
    assert sorted(path.name for path in (vault / "output").iterdir()) == [
        f"{stem}.candidates.md",
        f"{stem}.merged.md",
    ]


@pytest.mark.parametrize("print_output", [False, True])
def test_api_failed_matrix_prints_only_successful_candidates_after_publication(
    print_output: bool,
    cli_args: list[str],
    candidate: str,
    vault: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if json.loads(request.content)["model"] == DEEPSEEK:
            return httpx.Response(401, text="SYNTHETIC_REMOTE_SECRET")
        return httpx.Response(200, json={"choices": [{"message": {"content": candidate}}]})

    with httpx.Client(transport=httpx.MockTransport(handler)) as transport:
        monkeypatch.setattr(
            cli, "OpenRouterClient", lambda key: OpenRouterClient(key, client=transport)
        )
        assert (
            cli.main(
                cli_args
                + ["--models", ROSTER, "--candidates", "1", "--strict"]
                + (["--print-output"] if print_output else [])
            )
            == 4
        )
    captured = capsys.readouterr()
    assert captured.out.count(candidate) == (2 if print_output else 0)
    assert "SYNTHETIC_REMOTE_SECRET" not in captured.out + captured.err
    if print_output:
        assert captured.out.index("Arena report published:") < captured.out.index(candidate)
        assert f"{MAGNUM}::candidate-1\n{candidate}" in captured.out
        assert f"{EURYALE}::candidate-1\n{candidate}" in captured.out
    assert (
        json.loads((vault / "output" / "frame.arena.json").read_text(encoding="utf-8"))["status"]
        == "api_failed"
    )


def test_repeated_matrix_generation_preserves_reports_and_suppresses_candidate_printing(
    cli_args: list[str],
    vault: Path,
    arena_api: list[httpx.Request],
    candidate: str,
    capsys: pytest.CaptureFixture[str],
) -> None:
    args = cli_args + ["--models", ROSTER]
    assert cli.main(args) == 0
    paths = tuple((vault / "output").iterdir())
    before = {path: (path.read_bytes(), path.stat().st_mtime_ns) for path in paths}
    capsys.readouterr()
    assert cli.main(args + ["--print-output"]) == 2
    assert len(arena_api) == 18
    assert all(
        path.read_bytes() == content and path.stat().st_mtime_ns == modified
        for path, (content, modified) in before.items()
    )
    captured = capsys.readouterr()
    assert candidate not in captured.out + captured.err
    assert not list((vault / "output").glob(".zafo-*"))


@pytest.mark.parametrize("order", [False, True])
def test_explicit_single_and_matrix_model_flags_are_mutually_exclusive(order: bool) -> None:
    single, matrix = ["--model", MAGNUM], ["--models", ROSTER]
    with pytest.raises(SystemExit) as exc:
        cli.main(
            [
                "missing-synthetic-frame.md",
                *(matrix + single if order else single + matrix),
                "--dry-run",
            ]
        )
    assert exc.value.code == 2


@pytest.mark.parametrize("order", [False, True])
def test_exact_default_model_object_is_still_an_explicit_mutually_exclusive_argument(
    order: bool, monkeypatch: pytest.MonkeyPatch
) -> None:
    def blocked(*args: object, **kwargs: object) -> None:
        raise AssertionError("Conflicting explicit model flags must reject before file access.")

    monkeypatch.setattr(Path, "read_bytes", blocked)
    single = ["--model", ModelParams().model]
    matrix = ["--models", ROSTER]
    with pytest.raises(SystemExit) as exc:
        cli.main(
            [
                "missing-synthetic-frame.md",
                *(matrix + single if order else single + matrix),
                "--dry-run",
            ]
        )
    assert exc.value.code == 2


@pytest.mark.parametrize("mode", ["dry-run", "lint-only", "generation"])
def test_english_matrix_explicit_lexicon_rejects_before_access(
    mode: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    def blocked(*args: object, **kwargs: object) -> None:
        raise AssertionError("English --lexicon must reject before all file access.")

    monkeypatch.setattr(Path, "read_bytes", blocked)
    monkeypatch.setattr(Path, "read_text", blocked)
    flags = (
        ["--dry-run"]
        if mode == "dry-run"
        else ["--lint-only", "missing-candidate.txt"]
        if mode == "lint-only"
        else []
    )
    assert (
        cli.main(
            [
                "missing-synthetic-frame.md",
                "--language",
                "en",
                "--lexicon",
                "missing-synthetic-lexicon.md",
                "--models",
                ROSTER,
                *flags,
            ]
        )
        == 2
    )


@pytest.fixture
def arena_run(frame: FrameDocument, rules: LexiconRules, candidate: str) -> ArenaRun:
    profiles = select_model_profiles(f"{MAGNUM},{EURYALE}")
    candidates = []
    for profile in profiles:
        for index in range(1, 5):
            text = "Tea." if index == 1 else candidate
            response = CandidateResponse(
                profile.model_id,
                index,
                1,
                None if index == 4 else text,
                RequestFailure("http_error", 401) if index == 4 else None,
            )
            candidates.append(
                ArenaCandidate(response, lint_candidate(text, frame, rules) if index != 4 else None)
            )
    return ArenaRun(profiles, 4, tuple(candidates))


def test_arena_reporting_is_deterministic_with_per_model_ranking_and_failed_rows(
    frame: FrameDocument, arena_run: ArenaRun, vault: Path, tmp_path: Path
) -> None:
    paths = render_arena(
        frame, arena_run, vault / "output", vault_dir=vault, workspace_root=WORKSPACE
    )
    second = tmp_path / "second-synthetic-vault"
    second.mkdir()
    second_paths = render_arena(
        frame,
        replace(arena_run, candidates=tuple(reversed(arena_run.candidates))),
        second / "output",
        vault_dir=second,
        workspace_root=WORKSPACE,
    )
    assert all(
        first.read_bytes() == other.read_bytes()
        for first, other in zip(paths, second_paths, strict=True)
    )
    review = paths[0].read_text(encoding="utf-8")
    for profile in arena_run.profiles:
        positions = [
            review.index(f"### {profile.model_id}::candidate-{index}") for index in (2, 3, 1, 4)
        ]
        assert positions == sorted(positions)
    metadata = json.loads(paths[1].read_text(encoding="utf-8"))
    assert metadata["status"] == "api_failed"
    assert all(
        model["scorecard"]["hard_pass_rate_requested"] == 0.5 for model in metadata["models"]
    )
    assert all(
        [candidate["index"] for candidate in model["candidates"]] == [1, 2, 3, 4]
        for model in metadata["models"]
    )
    assert not list((vault / "output").glob(".zafo-*"))


@pytest.mark.parametrize("filename", ["frame.arena.md", "frame.arena.json"])
def test_arena_never_overwrites_existing_reports(
    frame: FrameDocument, arena_run: ArenaRun, vault: Path, filename: str
) -> None:
    output = vault / "output"
    output.mkdir()
    existing = output / filename
    existing.write_bytes(b"Synthetic existing report.")
    before = existing.stat().st_mtime_ns
    with pytest.raises(OutputError, match="already exists"):
        render_arena(frame, arena_run, output, vault_dir=vault, workspace_root=WORKSPACE)
    assert list(output.iterdir()) == [existing]
    assert existing.read_bytes() == b"Synthetic existing report."
    assert existing.stat().st_mtime_ns == before


@pytest.mark.parametrize("publication", [1, 2])
def test_arena_publication_failure_rolls_back_and_cleans_staging(
    frame: FrameDocument,
    arena_run: ArenaRun,
    vault: Path,
    monkeypatch: pytest.MonkeyPatch,
    publication: int,
) -> None:
    original_link = os.link
    calls = 0

    def failed_link(source: Path, target: Path) -> None:
        nonlocal calls
        calls += 1
        if calls == publication:
            raise OSError("Synthetic arena publication failure.")
        original_link(source, target)

    monkeypatch.setattr(os, "link", failed_link)
    with pytest.raises(OSError, match="publication failure"):
        render_arena(frame, arena_run, vault / "output", vault_dir=vault, workspace_root=WORKSPACE)
    assert list((vault / "output").iterdir()) == []


def test_arena_staging_failure_cleans_staged_files(
    frame: FrameDocument, arena_run: ArenaRun, vault: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    create = renderer_module.tempfile.NamedTemporaryFile
    calls = 0

    def failed_stage(*args: object, **kwargs: object) -> object:
        nonlocal calls
        calls += 1
        if calls == 2:
            raise OSError("Synthetic arena staging failure.")
        return create(*args, **kwargs)

    monkeypatch.setattr(renderer_module.tempfile, "NamedTemporaryFile", failed_stage)
    with pytest.raises(OSError, match="staging failure"):
        render_arena(frame, arena_run, vault / "output", vault_dir=vault, workspace_root=WORKSPACE)
    assert list((vault / "output").iterdir()) == []


def test_arena_publication_conflict_preserves_competing_report(
    frame: FrameDocument, arena_run: ArenaRun, vault: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    original_link = os.link
    calls = 0

    def competing_link(source: Path, target: Path) -> None:
        nonlocal calls
        calls += 1
        if calls == 2:
            target.write_bytes(b'{"synthetic_competing_report": true}')
        original_link(source, target)

    monkeypatch.setattr(os, "link", competing_link)
    with pytest.raises(FileExistsError):
        render_arena(frame, arena_run, vault / "output", vault_dir=vault, workspace_root=WORKSPACE)
    remaining = list((vault / "output").iterdir())
    assert remaining == [vault / "output" / "frame.arena.json"]
    assert remaining[0].read_bytes() == b'{"synthetic_competing_report": true}'


@pytest.mark.parametrize("reject_on_call", [2, 3, 4, 5])
def test_arena_boundary_revalidation_cleans_or_rolls_back_publication(
    frame: FrameDocument,
    arena_run: ArenaRun,
    vault: Path,
    monkeypatch: pytest.MonkeyPatch,
    reject_on_call: int,
) -> None:
    validate = renderer_module.validate_output_dir
    calls = 0

    def changed_boundary(output: Path, vault_dir: Path, workspace_root: Path) -> Path:
        nonlocal calls
        calls += 1
        if calls == reject_on_call:
            raise AirGapViolationError("Synthetic changed arena boundary.")
        return validate(output, vault_dir, workspace_root)

    monkeypatch.setattr(renderer_module, "validate_output_dir", changed_boundary)
    with pytest.raises(AirGapViolationError):
        render_arena(frame, arena_run, vault / "output", vault_dir=vault, workspace_root=WORKSPACE)
    assert calls == reject_on_call
    assert list((vault / "output").iterdir()) == []


def test_arena_rejects_d_drive_non_output_paths_and_changed_slot_contract(
    frame: FrameDocument, arena_run: ArenaRun, vault: Path
) -> None:
    with pytest.raises(AirGapViolationError):
        render_arena(
            frame,
            arena_run,
            Path(r"D:\synthetic-forbidden\output"),
            vault_dir=Path(r"D:\synthetic-forbidden"),
            workspace_root=WORKSPACE,
        )
    with pytest.raises(AirGapViolationError):
        render_arena(
            frame, arena_run, vault / "elsewhere", vault_dir=vault, workspace_root=WORKSPACE
        )
    changed = replace(frame, slot=replace(frame.slot, raw_comment="SYNTHETIC_CHANGED_SLOT"))
    with pytest.raises(OutputError, match="offsets"):
        render_arena(
            changed, arena_run, vault / "output", vault_dir=vault, workspace_root=WORKSPACE
        )
    assert not (vault / "output").exists()


def test_arena_cli_publication_failure_never_prints_candidates_or_partial_reports(
    cli_args: list[str],
    vault: Path,
    arena_api: list[httpx.Request],
    monkeypatch: pytest.MonkeyPatch,
    candidate: str,
    capsys: pytest.CaptureFixture[str],
) -> None:
    original_link = os.link
    calls = 0

    def failed_link(source: Path, target: Path) -> None:
        nonlocal calls
        calls += 1
        if calls == 2:
            raise OSError("SYNTHETIC_PRIVATE_ERROR_SENTINEL")
        original_link(source, target)

    monkeypatch.setattr(os, "link", failed_link)
    assert cli.main(cli_args + ["--models", ROSTER, "--print-output"]) == 2
    captured = capsys.readouterr()
    assert candidate not in captured.out + captured.err
    assert "SYNTHETIC_PRIVATE_ERROR_SENTINEL" not in captured.out + captured.err
    assert len(arena_api) == 9
    assert list((vault / "output").iterdir()) == []
