from dataclasses import FrozenInstanceError, replace

import pytest

from zafo_injector.config import ConfigurationError
from zafo_injector.model_profiles import (
    MODEL_PROFILES,
    select_model_profiles,
    validate_matrix_request,
)
from zafo_injector.models import (
    ArenaCandidate,
    ArenaRun,
    CandidateResponse,
    LintReport,
    ModelParams,
    ModelProfile,
    RequestFailure,
)

MAGNUM = "anthracite-org/magnum-v4-72b"
DEEPSEEK = "deepseek/deepseek-chat-v3-0324"
EURYALE = "sao10k/l3.1-euryale-70b"
ROSTER = f"{MAGNUM},{DEEPSEEK},{EURYALE}"


def test_registry_defaults_and_supported_sampling_are_immutable() -> None:
    profiles = select_model_profiles(ROSTER)
    assert tuple(profile.model_id for profile in profiles) == (MAGNUM, DEEPSEEK, EURYALE)
    assert profiles[0].params == ModelParams()
    assert (
        profiles[0].sampling_parameters()
        == profiles[2].sampling_parameters()
        == {
            "temperature": 0.68,
            "min_p": 0.06,
            "top_p": 0.9,
            "repetition_penalty": 1.05,
        }
    )
    assert profiles[1].sampling_parameters() == {"temperature": 0.68, "top_p": 0.9}
    assert profiles[1].omitted_parameters == ("min_p", "repetition_penalty")
    assert profiles[0].omitted_parameters == ()
    assert profiles[0].provider_settings() == {
        "quantizations": ["bf16", "fp16", "fp8"],
        "allow_fallbacks": True,
        "require_parameters": True,
    }
    with pytest.raises(FrozenInstanceError):
        profiles[0].supported_parameters = ()  # type: ignore[misc]
    with pytest.raises(FrozenInstanceError):
        profiles[0].params.temperature = 0.4  # type: ignore[misc]
    with pytest.raises(TypeError):
        MODEL_PROFILES[MAGNUM] = profiles[1]  # type: ignore[index]
    settings = profiles[0].sampling_parameters()
    settings["temperature"] = 1
    assert MODEL_PROFILES[MAGNUM].params.temperature == 0.68


@pytest.mark.parametrize(
    "model_list",
    [
        "",
        " ",
        f",{MAGNUM}",
        f"{MAGNUM},",
        f"{MAGNUM},,{EURYALE}",
        f"{MAGNUM}, {MAGNUM}",
        MAGNUM,
        f"{MAGNUM},MAGNUM",
        f"{MAGNUM},anthracite-org/Magnum-v4-72b",
        f"{MAGNUM},sao10k/l3.3-euryale-70b",
        f"{MAGNUM},SYNTHETIC_UNKNOWN_SENTINEL",
    ],
)
def test_model_list_rejections_do_not_echo_untrusted_ids(model_list: str) -> None:
    with pytest.raises(ConfigurationError) as exc:
        select_model_profiles(model_list)
    assert "SYNTHETIC_UNKNOWN_SENTINEL" not in str(exc.value)


def test_model_list_trims_whitespace_and_preserves_requested_order() -> None:
    profiles = select_model_profiles(f" {EURYALE} , {MAGNUM} ")
    assert tuple(profile.model_id for profile in profiles) == (EURYALE, MAGNUM)


def test_explicit_overrides_win_without_mutating_registry() -> None:
    profiles = select_model_profiles(f"{MAGNUM},{EURYALE}", temperature=0.4, min_p=0.2)
    assert all(
        profile.params.temperature == 0.4 and profile.params.min_p == 0.2 for profile in profiles
    )
    assert MODEL_PROFILES[MAGNUM].params == ModelParams()
    mixed = select_model_profiles(ROSTER, temperature=0.4)
    assert all(profile.sampling_parameters()["temperature"] == 0.4 for profile in mixed)
    assert "min_p" not in mixed[1].sampling_parameters()
    with pytest.raises(ConfigurationError, match="every selected"):
        select_model_profiles(ROSTER, min_p=0.06)


@pytest.mark.parametrize("temperature", [float("nan"), float("inf"), -0.1, 2.1])
def test_invalid_temperature_override_is_rejected(temperature: float) -> None:
    with pytest.raises(ValueError):
        select_model_profiles(f"{MAGNUM},{EURYALE}", temperature=temperature)


@pytest.mark.parametrize("min_p", [float("nan"), float("inf"), -0.1, 1.1])
def test_invalid_min_p_override_is_rejected(min_p: float) -> None:
    with pytest.raises(ValueError):
        select_model_profiles(f"{MAGNUM},{EURYALE}", min_p=min_p)


@pytest.mark.parametrize(("model_count", "n"), [(2, 1), (2, 4), (3, 3)])
def test_exact_matrix_request_budget_accepts_valid_counts(model_count: int, n: int) -> None:
    validate_matrix_request(select_model_profiles(ROSTER)[:model_count], n)


@pytest.mark.parametrize(("model_count", "n"), [(2, 0), (2, -1), (2, 5), (3, 4), (3, 10)])
def test_matrix_request_budget_rejects_excess_counts(model_count: int, n: int) -> None:
    with pytest.raises(ConfigurationError, match="nine"):
        validate_matrix_request(select_model_profiles(ROSTER)[:model_count], n)


@pytest.mark.parametrize(
    "supported",
    [(), ("temperature",), ("temperature", "top_p", "top_p"), ("temperature", "top_p", "top_k")],
)
def test_invalid_profile_support_is_rejected(supported: tuple[str, ...]) -> None:
    with pytest.raises(ValueError, match="profile"):
        ModelProfile(ModelParams(), supported)


def test_library_matrix_rejects_unregistered_or_forged_support() -> None:
    profiles = select_model_profiles(ROSTER)
    unknown = replace(profiles[0], params=ModelParams(model="synthetic/unknown"))
    forged = replace(profiles[1], supported_parameters=profiles[0].supported_parameters)
    for invalid in ((profiles[0], unknown), (profiles[0], forged), (profiles[0], profiles[0])):
        with pytest.raises(ConfigurationError):
            validate_matrix_request(invalid, 1)


def test_arena_contracts_retain_complete_stable_identities_and_redact_text() -> None:
    profiles = select_model_profiles(f"{MAGNUM},{EURYALE}")
    report = LintReport(20, 2, (), 100, True)
    candidates = tuple(
        ArenaCandidate(CandidateResponse(profile.model_id, 1, 1, "SYNTHETIC_TEXT_SENTINEL"), report)
        for profile in profiles
    )
    run = ArenaRun(profiles, 1, candidates, strict=True)
    assert run.status == "completed" and run.exit_code == 0
    assert run.initial_requests == run.http_attempts == 2
    assert candidates[0].response.candidate_id == f"{MAGNUM}::candidate-1"
    assert run.hard_pass_count(MAGNUM) == 1
    assert "SYNTHETIC_TEXT_SENTINEL" not in repr(run)
    with pytest.raises(FrozenInstanceError):
        run.strict = False  # type: ignore[misc]
    with pytest.raises(FrozenInstanceError):
        candidates[0].response.index = 2  # type: ignore[misc]
    with pytest.raises(ValueError, match="every planned"):
        replace(run, candidates=candidates[:1])
    with pytest.raises(ValueError, match="every planned"):
        replace(run, candidates=(candidates[0], candidates[0]))
    with pytest.raises(ValueError, match="not part"):
        run.for_model(DEEPSEEK)


@pytest.mark.parametrize(
    ("index", "attempts", "text", "failure"),
    [
        (0, 1, "Coffee.", None),
        (1, 0, "Coffee.", None),
        (1, 4, "Coffee.", None),
        (1, 1, " ", None),
        (1, 1, None, None),
        (1, 1, "Coffee.", RequestFailure("transport_error")),
    ],
)
def test_invalid_candidate_response_contracts(
    index: int, attempts: int, text: str | None, failure: RequestFailure | None
) -> None:
    with pytest.raises(ValueError):
        CandidateResponse(MAGNUM, index, attempts, text, failure)


def test_failed_requests_cannot_have_qa_or_success_shaped_results() -> None:
    profiles = select_model_profiles(f"{MAGNUM},{EURYALE}")
    failure = RequestFailure("http_error", 401)
    response = CandidateResponse(MAGNUM, 1, 1, None, failure)
    with pytest.raises(ValueError, match="lint report"):
        ArenaCandidate(response, LintReport(20, 2, (), 100, True))
    with pytest.raises(ValueError):
        RequestFailure("http_error")
    with pytest.raises(ValueError):
        RequestFailure("transport_error", 401)
    run = ArenaRun(
        profiles,
        1,
        (
            ArenaCandidate(response, None),
            ArenaCandidate(
                CandidateResponse(EURYALE, 1, 1, "Coffee."),
                LintReport(1, 1, (), 50, False),
            ),
        ),
        strict=True,
    )
    assert run.status == "api_failed" and run.exit_code == 4
