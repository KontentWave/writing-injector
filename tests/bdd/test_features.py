from pathlib import Path

import httpx
import pytest
from pytest_bdd import given, scenarios, then, when

from zafo_injector.cli import main
from zafo_injector.config import AirGapViolationError, validate_storage_path
from zafo_injector.models import FrameDocument
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
