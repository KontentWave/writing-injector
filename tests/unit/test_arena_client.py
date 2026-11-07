import json
import threading
from collections import Counter
from concurrent.futures import ThreadPoolExecutor

import httpx
import pytest

from zafo_injector import openrouter_client as client_module
from zafo_injector.config import ConfigurationError
from zafo_injector.model_profiles import select_model_profiles
from zafo_injector.openrouter_client import ENDPOINT, OpenRouterClient, OpenRouterError

MAGNUM = "anthracite-org/magnum-v4-72b"
DEEPSEEK = "deepseek/deepseek-chat-v3-0324"
EURYALE = "sao10k/l3.1-euryale-70b"
ROSTER = f"{MAGNUM},{DEEPSEEK},{EURYALE}"
MESSAGES = [
    {"role": "system", "content": "Benign synthetic instructions."},
    {"role": "user", "content": "Make coffee."},
]


def test_matrix_payloads_share_messages_and_record_effective_profiles() -> None:
    requests: list[httpx.Request] = []
    original = json.dumps(MESSAGES)

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(200, json={"choices": [{"message": {"content": "Coffee."}}]})

    profiles = select_model_profiles(ROSTER, temperature=0.4)
    with httpx.Client(transport=httpx.MockTransport(handler)) as transport:
        responses = OpenRouterClient("synthetic-key", client=transport).generate_matrix(
            MESSAGES, profiles, 2
        )
        assert not transport.is_closed
    assert [(response.model_id, response.index) for response in responses] == [
        (profile.model_id, index) for profile in profiles for index in (1, 2)
    ]
    assert all(response.text == "Coffee." and response.failure is None for response in responses)
    assert all(response.attempts == 1 for response in responses)
    assert json.dumps(MESSAGES) == original
    assert len(requests) == 6
    for request in requests:
        payload = json.loads(request.content)
        profile = next(profile for profile in profiles if profile.model_id == payload["model"])
        assert str(request.url) == ENDPOINT
        assert payload == {
            "model": profile.model_id,
            "messages": MESSAGES,
            "n": 1,
            **profile.sampling_parameters(),
            "provider": profile.provider_settings(),
        }
        assert request.extensions["timeout"] == {"connect": 45, "read": 45, "write": 45, "pool": 45}


def test_matrix_uses_one_global_three_worker_pool(monkeypatch: pytest.MonkeyPatch) -> None:
    workers: list[int] = []
    lock = threading.Lock()
    ready = threading.Event()
    active = maximum = 0
    models: Counter[str] = Counter()

    def executor(*, max_workers: int) -> ThreadPoolExecutor:
        workers.append(max_workers)
        return ThreadPoolExecutor(max_workers=max_workers)

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal active, maximum
        with lock:
            models[json.loads(request.content)["model"]] += 1
            active += 1
            maximum = max(maximum, active)
            if active == 3:
                ready.set()
        assert ready.wait(timeout=5)
        with lock:
            active -= 1
        return httpx.Response(200, json={"choices": [{"message": {"content": "Coffee."}}]})

    monkeypatch.setattr(client_module, "ThreadPoolExecutor", executor)
    with httpx.Client(transport=httpx.MockTransport(handler)) as transport:
        result = OpenRouterClient("synthetic-key", client=transport).generate_matrix(
            MESSAGES, select_model_profiles(ROSTER), 3
        )
    assert len(result) == 9
    assert workers == [3]
    assert maximum == 3
    assert models == Counter({MAGNUM: 3, DEEPSEEK: 3, EURYALE: 3})


def test_completion_order_does_not_change_model_candidate_mapping() -> None:
    events = {model_id: threading.Event() for model_id in (MAGNUM, DEEPSEEK, EURYALE)}
    completed: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        model = json.loads(request.content)["model"]
        if model == MAGNUM:
            assert events[DEEPSEEK].wait(timeout=5)
        elif model == DEEPSEEK:
            assert events[EURYALE].wait(timeout=5)
        completed.append(model)
        events[model].set()
        return httpx.Response(200, json={"choices": [{"message": {"content": model}}]})

    with httpx.Client(transport=httpx.MockTransport(handler)) as transport:
        result = OpenRouterClient("synthetic-key", client=transport).generate_matrix(
            MESSAGES, select_model_profiles(ROSTER), 1
        )
    assert completed == [EURYALE, DEEPSEEK, MAGNUM]
    assert [(response.model_id, response.text, response.index) for response in result] == [
        (model, model, 1) for model in (MAGNUM, DEEPSEEK, EURYALE)
    ]


@pytest.mark.parametrize("status", [429, 500, 503])
def test_matrix_retry_and_total_attempt_budget(status: int) -> None:
    calls: Counter[str] = Counter()
    sleeps: list[float] = []
    lock = threading.Lock()

    def handler(request: httpx.Request) -> httpx.Response:
        with lock:
            calls[json.loads(request.content)["model"]] += 1
        return httpx.Response(status, text="SYNTHETIC_REMOTE_SECRET")

    with httpx.Client(transport=httpx.MockTransport(handler)) as transport:
        result = OpenRouterClient(
            "synthetic-key", client=transport, sleep=sleeps.append
        ).generate_matrix(MESSAGES, select_model_profiles(ROSTER), 3)
    assert calls == Counter({MAGNUM: 9, DEEPSEEK: 9, EURYALE: 9})
    assert sum(response.attempts for response in result) == 27
    assert Counter(sleeps) == Counter({0.5: 9, 1.0: 9})
    assert all(
        response.text is None
        and response.attempts == 3
        and response.failure is not None
        and response.failure.code == "http_error"
        and response.failure.http_status == status
        for response in result
    )
    assert "SYNTHETIC_REMOTE_SECRET" not in repr(result)
    assert all(
        response.failure is not None and "no output was written" not in response.failure.message
        for response in result
    )


def test_matrix_retry_recovery_keeps_per_request_attempt_counts() -> None:
    calls: Counter[str] = Counter()
    lock = threading.Lock()

    def handler(request: httpx.Request) -> httpx.Response:
        model = json.loads(request.content)["model"]
        with lock:
            calls[model] += 1
            status = 429 if calls[model] == 1 else 200
        return httpx.Response(status, json={"choices": [{"message": {"content": "Coffee."}}]})

    with httpx.Client(transport=httpx.MockTransport(handler)) as transport:
        result = OpenRouterClient(
            "synthetic-key", client=transport, sleep=lambda _: None
        ).generate_matrix(MESSAGES, select_model_profiles(ROSTER), 1)
    assert calls == Counter({MAGNUM: 2, DEEPSEEK: 2, EURYALE: 2})
    assert all(response.attempts == 2 and response.failure is None for response in result)


@pytest.mark.parametrize(
    ("content", "code"),
    [
        ("not JSON", "invalid_json"),
        ("null", "invalid_response"),
        ("[]", "invalid_response"),
        ('{"choices":[]}', "no_choices"),
        ('{"choices":[null]}', "no_choices"),
        ('{"choices":[{"message":{}}]}', "no_text"),
        ('{"choices":[{"message":{"content":null}}]}', "no_text"),
        ('{"choices":[{"message":{"content":" "}}]}', "empty_candidate"),
    ],
)
def test_matrix_response_failures_remain_explicit_after_retry(content: str, code: str) -> None:
    calls: Counter[str] = Counter()
    lock = threading.Lock()

    def handler(request: httpx.Request) -> httpx.Response:
        model = json.loads(request.content)["model"]
        with lock:
            calls[model] += 1
            first = calls[model] == 1
        return httpx.Response(500 if first else 200, content=content)

    with httpx.Client(transport=httpx.MockTransport(handler)) as transport:
        result = OpenRouterClient(
            "synthetic-key", client=transport, sleep=lambda _: None
        ).generate_matrix(MESSAGES, select_model_profiles(ROSTER), 1)
    assert all(
        response.failure is not None and response.failure.code == code and response.attempts == 2
        for response in result
    )


@pytest.mark.parametrize("status", [301, 400, 401, 403])
def test_matrix_nonretryable_failure_does_not_abort_other_models(status: int) -> None:
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        if json.loads(request.content)["model"] == DEEPSEEK:
            return httpx.Response(
                status,
                headers={"Location": "https://example.invalid"},
                text="SYNTHETIC_REMOTE_SECRET",
            )
        return httpx.Response(200, json={"choices": [{"message": {"content": "Coffee."}}]})

    with httpx.Client(transport=httpx.MockTransport(handler), follow_redirects=True) as transport:
        result = OpenRouterClient("synthetic-key", client=transport).generate_matrix(
            MESSAGES, select_model_profiles(ROSTER), 2
        )
    assert len(requests) == len(result) == 6
    assert all(str(request.url) == ENDPOINT for request in requests)
    failures = [response for response in result if response.failure is not None]
    assert [(response.model_id, response.index, response.attempts) for response in failures] == [
        (DEEPSEEK, 1, 1),
        (DEEPSEEK, 2, 1),
    ]
    assert "SYNTHETIC_REMOTE_SECRET" not in repr(result)


@pytest.mark.parametrize("exception", [httpx.ConnectError, httpx.ReadTimeout])
def test_matrix_transport_errors_are_redacted_and_not_retried(
    exception: type[httpx.RequestError],
) -> None:
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        raise exception("SYNTHETIC_REMOTE_SECRET", request=request)

    with httpx.Client(transport=httpx.MockTransport(handler)) as transport:
        result = OpenRouterClient("synthetic-key", client=transport).generate_matrix(
            MESSAGES, select_model_profiles(ROSTER), 1
        )
    assert len(requests) == 3
    assert all(
        response.attempts == 1
        and response.failure is not None
        and response.failure.code == "transport_error"
        for response in result
    )
    assert "SYNTHETIC_REMOTE_SECRET" not in repr(result)


def test_matrix_validation_and_invalid_key_fail_before_transport_creation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def blocked(**kwargs: object) -> httpx.Client:
        raise AssertionError("Invalid requests must not construct a transport.")

    monkeypatch.setattr(httpx, "Client", blocked)
    profiles = select_model_profiles(ROSTER)
    with pytest.raises(ConfigurationError):
        OpenRouterClient("synthetic-key").generate_matrix(MESSAGES, profiles, 4)
    with pytest.raises(OpenRouterError, match="valid API key"):
        OpenRouterClient("").generate_matrix(MESSAGES, profiles, 1)


def test_matrix_production_transport_configuration_is_unchanged(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    real_client = httpx.Client
    settings: list[dict[str, object]] = []

    def factory(**kwargs: object) -> httpx.Client:
        settings.append(kwargs)
        return real_client(
            transport=httpx.MockTransport(
                lambda request: httpx.Response(
                    200, json={"choices": [{"message": {"content": "Coffee."}}]}
                )
            )
        )

    monkeypatch.setattr(httpx, "Client", factory)
    result = OpenRouterClient("synthetic-key").generate_matrix(
        MESSAGES, select_model_profiles(ROSTER), 1
    )
    assert len(result) == 3
    assert settings == [{"timeout": 45, "follow_redirects": False, "trust_env": False}]
