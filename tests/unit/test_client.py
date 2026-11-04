import json
import threading

import httpx
import pytest

from zafo_injector.models import ModelParams
from zafo_injector.openrouter_client import ENDPOINT, OpenRouterClient, OpenRouterError

MESSAGES = [{"role": "user", "content": "Make coffee."}]


def test_payload_and_parallel_candidate_count() -> None:
    requests: list[httpx.Request] = []
    barrier = threading.Barrier(3)

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        barrier.wait(timeout=5)
        return httpx.Response(200, json={"choices": [{"message": {"content": "Coffee."}}]})

    with httpx.Client(transport=httpx.MockTransport(handler)) as transport:
        result = OpenRouterClient("synthetic-key", client=transport).generate_candidates(
            MESSAGES, ModelParams(), 3
        )
    assert result == ["Coffee."] * 3
    assert len(requests) == 3
    for request in requests:
        assert str(request.url) == ENDPOINT
        assert request.headers["Authorization"] == "Bearer synthetic-key"
        assert json.loads(request.content) == {
            "model": "anthracite-org/magnum-v4-72b",
            "messages": MESSAGES,
            "n": 1,
            "temperature": 0.68,
            "min_p": 0.06,
            "top_p": 0.90,
            "repetition_penalty": 1.05,
            "provider": {"quantizations": ["bf16", "fp16", "fp8"], "allow_fallbacks": True},
        }


@pytest.mark.parametrize("status", [429, 500, 503])
def test_bounded_exponential_retries(status: int) -> None:
    calls: list[int] = []
    sleeps: list[float] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(status)
        return httpx.Response(status, text="synthetic-key must never be shown")

    with httpx.Client(transport=httpx.MockTransport(handler)) as transport:
        with pytest.raises(OpenRouterError) as error:
            OpenRouterClient(
                "synthetic-key", client=transport, sleep=sleeps.append
            ).generate_candidates(MESSAGES, ModelParams(), 1)
    assert calls == [status] * 3
    assert sleeps == [0.5, 1.0]
    assert "synthetic-key" not in str(error.value)


def test_retry_can_recover() -> None:
    statuses = iter([429, 200])

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            next(statuses), json={"choices": [{"message": {"content": "Coffee."}}]}
        )

    with httpx.Client(transport=httpx.MockTransport(handler)) as transport:
        assert OpenRouterClient("test", client=transport, sleep=lambda _: None).generate_candidates(
            MESSAGES, ModelParams(), 1
        ) == ["Coffee."]


@pytest.mark.parametrize("status", [301, 400, 401, 403])
def test_nonretryable_status_is_redacted(status: int) -> None:
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(
            status, headers={"Location": "https://example.invalid"}, text="SECRET"
        )

    with httpx.Client(transport=httpx.MockTransport(handler), follow_redirects=True) as transport:
        with pytest.raises(OpenRouterError) as error:
            OpenRouterClient("SECRET", client=transport).generate_candidates(
                MESSAGES, ModelParams(), 1
            )
    assert len(requests) == 1
    assert "SECRET" not in str(error.value)


@pytest.mark.parametrize(
    "payload",
    [
        None,
        [],
        {},
        {"choices": []},
        {"choices": [None]},
        {"choices": [{"message": {"content": None}}]},
        {"choices": [{"message": {"content": " "}}]},
    ],
)
def test_invalid_response_shapes(payload: object) -> None:
    with httpx.Client(
        transport=httpx.MockTransport(
            lambda request: httpx.Response(200, content=json.dumps(payload))
        )
    ) as transport:
        with pytest.raises(OpenRouterError):
            OpenRouterClient("test", client=transport).generate_candidates(
                MESSAGES, ModelParams(), 1
            )


def test_transport_exception_is_redacted() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("SECRET", request=request)

    with httpx.Client(transport=httpx.MockTransport(handler)) as transport:
        with pytest.raises(OpenRouterError) as error:
            OpenRouterClient("SECRET", client=transport).generate_candidates(
                MESSAGES, ModelParams(), 1
            )
    assert "SECRET" not in str(error.value)


def test_markdown_and_echo_cleanup() -> None:
    content = "```markdown\n<!-- [TIER 1 INSERT SLOT: 20-80 slov] -->\nCoffee.\n```"
    with httpx.Client(
        transport=httpx.MockTransport(
            lambda request: httpx.Response(
                200, json={"choices": [{"message": {"content": content}}]}
            )
        )
    ) as transport:
        assert OpenRouterClient("test", client=transport).generate_candidates(
            MESSAGES, ModelParams(), 1
        ) == ["Coffee."]


@pytest.mark.parametrize("key", ["", "synthetic-secret-ľ", "synthetic\tkey"])
def test_invalid_header_keys_raise_only_redacted_errors(key: str) -> None:
    with pytest.raises(OpenRouterError) as error:
        OpenRouterClient(key).generate_candidates(MESSAGES, ModelParams(), 1)
    assert "synthetic" not in str(error.value)


def test_invalid_json_is_reported() -> None:
    with httpx.Client(
        transport=httpx.MockTransport(lambda request: httpx.Response(200, content=b"not JSON"))
    ) as transport:
        with pytest.raises(OpenRouterError, match="invalid JSON"):
            OpenRouterClient("test", client=transport).generate_candidates(
                MESSAGES, ModelParams(), 1
            )
