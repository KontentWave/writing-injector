import json
from pathlib import Path

import httpx
import pytest
from pytest_bdd import given, scenarios, then, when

from zafo_injector import cli
from zafo_injector.cli import main
from zafo_injector.config import AirGapViolationError, validate_storage_path
from zafo_injector.models import FrameDocument
from zafo_injector.openrouter_client import OpenRouterClient
from zafo_injector.slovak_lint import LexiconRules, lint_candidate

scenarios(str(Path(__file__).resolve().parents[2] / "specs" / "features"))


@given("a vault path on drive D", target_fixture="forbidden")
def forbidden_path() -> Path:
    return Path(r"D:\private-vault")


@when("the vault boundary is checked", target_fixture="rejected")
def check_boundary(forbidden: Path) -> bool:
    with pytest.raises(AirGapViolationError):
        validate_storage_path(forbidden, Path(__file__).resolve().parents[2])
    return True


@then("storage is rejected")
def storage_rejected(rejected: bool) -> None:
    assert rejected


@given("a synthetic coffee frame")
def coffee_frame(frame: FrameDocument) -> None:
    assert frame.source_path.name == "frame.md"


@when("the frame is parsed")
def parsed(frame: FrameDocument) -> None:
    assert frame.pov == "male"


@then("its word bounds and two surrounding paragraphs are extracted")
def extracted(frame: FrameDocument) -> None:
    assert (frame.slot.min_words, frame.slot.max_words) == (20, 80)
    assert len(frame.context_before) == len(frame.context_after) == 2


@given("a clean synthetic candidate and a Czechism variant")
def candidates(candidate: str) -> None:
    assert candidate


@when("both candidates are linted", target_fixture="scores")
def scores(candidate: str, frame: FrameDocument, rules: LexiconRules) -> tuple[int, int]:
    return (
        lint_candidate(candidate, frame, rules).score,
        lint_candidate(candidate + " zrovna", frame, rules).score,
    )


@then("the clean candidate has the higher score")
def higher(scores: tuple[int, int]) -> None:
    assert scores[0] > scores[1]


@given("a synthetic CLI run with mocked OpenRouter responses", target_fixture="original")
def mocked_cli(fixtures: Path, mock_api: list[httpx.Request]) -> bytes:
    return (fixtures / "frame.md").read_bytes()


@when("injection is executed")
def inject(cli_args: list[str]) -> None:
    assert main(cli_args) == 0


@then("both drafts exist only in the synthetic vault output")
def drafts(vault: Path, fixtures: Path, original: bytes) -> None:
    assert (vault / "output" / "frame.candidates.md").is_file()
    assert (vault / "output" / "frame.merged.md").is_file()
    assert (fixtures / "frame.md").read_bytes() == original
    assert not (fixtures / "frame.merged.md").exists()


ARENA_MODELS = (
    "anthracite-org/magnum-v4-72b",
    "deepseek/deepseek-chat-v3-0324",
    "sao10k/l3.1-euryale-70b",
)


@when("model comparison is executed")
def compare_models(cli_args: list[str]) -> None:
    assert main(cli_args + ["--models", ",".join(ARENA_MODELS), "--strict"]) == 0


@then("only arena review and scorecards exist in the synthetic vault output")
def arena_reports(vault: Path, fixtures: Path, original: bytes) -> None:
    assert sorted(path.name for path in (vault / "output").iterdir()) == [
        "frame.arena.json",
        "frame.arena.md",
    ]
    assert (fixtures / "frame.md").read_bytes() == original


@then("every model has its planned stable candidate identities")
def planned_identities(vault: Path) -> None:
    metadata = json.loads((vault / "output" / "frame.arena.json").read_text(encoding="utf-8"))
    assert metadata["status"] == "completed" and metadata["execution"]["http_attempts"] == 9
    for model, model_id in zip(metadata["models"], ARENA_MODELS, strict=True):
        assert model["model_id"] == model_id
        assert model["scorecard"]["hard_pass_count"] == 3
        assert [candidate["candidate_id"] for candidate in model["candidates"]] == [
            f"{model_id}::candidate-{index}" for index in range(1, 4)
        ]


@when("comparison with a failed model is executed")
def compare_failed_model(
    cli_args: list[str], candidate: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        model_id = json.loads(request.content)["model"]
        if model_id == ARENA_MODELS[1]:
            return httpx.Response(401, text="SYNTHETIC_REMOTE_SECRET")
        return httpx.Response(200, json={"choices": [{"message": {"content": candidate}}]})

    with httpx.Client(transport=httpx.MockTransport(handler)) as transport:
        monkeypatch.setattr(
            cli, "OpenRouterClient", lambda key: OpenRouterClient(key, client=transport)
        )
        assert main(cli_args + ["--models", ",".join(ARENA_MODELS), "--strict"]) == 4


@then("the scorecards explicitly record the failed model")
def failed_scorecard(vault: Path) -> None:
    raw = (vault / "output" / "frame.arena.json").read_text(encoding="utf-8")
    metadata = json.loads(raw)
    assert metadata["status"] == "api_failed" and metadata["exit_code"] == 4
    failed = metadata["models"][1]
    assert failed["model_id"] == ARENA_MODELS[1]
    assert failed["scorecard"]["api_failed"] == 3
    assert all(candidate["score"] is None for candidate in failed["candidates"])
    assert "SYNTHETIC_REMOTE_SECRET" not in raw
