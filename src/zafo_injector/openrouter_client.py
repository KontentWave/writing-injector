import re
import time
from collections.abc import Callable, Iterator
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager

import httpx

from .config import ConfigurationError, validate_api_key
from .model_profiles import validate_matrix_request
from .models import (
    MAX_CONCURRENT_REQUESTS,
    MAX_RETRIES,
    REQUEST_TIMEOUT_SECONDS,
    CandidateResponse,
    FailureCode,
    ModelParams,
    ModelProfile,
    RequestFailure,
)

ENDPOINT = "https://openrouter.ai/api/v1/chat/completions"
RequestJob = tuple[ModelParams, ModelProfile | None, int]


class OpenRouterError(RuntimeError):
    """A redacted remote-generation failure."""

    def __init__(
        self,
        message: str,
        *,
        code: FailureCode = "generation_error",
        http_status: int | None = None,
        attempts: int = 1,
    ) -> None:
        super().__init__(message)
        self.failure = RequestFailure(code, http_status)
        self.attempts = attempts


def _clean_content(text: str) -> str:
    text = text.strip()
    fence = re.fullmatch(r"```[^\r\n]*\r?\n(.*?)\r?\n```", text, re.DOTALL)
    if fence:
        text = fence.group(1).strip()
    text = re.sub(r"<!--\s*\[TIER\b.*?-->", "", text, flags=re.DOTALL | re.IGNORECASE).strip()
    if not text:
        raise OpenRouterError("OpenRouter returned an empty candidate.", code="empty_candidate")
    return text


class OpenRouterClient:
    def __init__(
        self,
        api_key: str,
        *,
        client: httpx.Client | None = None,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        self._api_key = api_key
        self._client = client
        self._sleep = sleep

    def generate_candidates(
        self, messages: list[dict[str, str]], params: ModelParams, n: int
    ) -> list[str]:
        if n < 1:
            raise ValueError("Candidate count must be positive.")
        self._validate_key()
        jobs = tuple((params, None, index) for index in range(1, n + 1))
        with self._transport() as client:
            responses = self._generate_requests(client, messages, jobs, report_failures=False)
        return [response.text for response in responses if response.text is not None]

    def generate_matrix(
        self, messages: list[dict[str, str]], profiles: tuple[ModelProfile, ...], n: int
    ) -> tuple[CandidateResponse, ...]:
        validate_matrix_request(profiles, n)
        self._validate_key()
        jobs = tuple(
            (profile.params, profile, index) for profile in profiles for index in range(1, n + 1)
        )
        with self._transport() as client:
            return self._generate_requests(client, messages, jobs, report_failures=True)

    def _validate_key(self) -> None:
        try:
            validate_api_key(self._api_key)
        except ConfigurationError:
            raise OpenRouterError("A valid API key is required.") from None

    @contextmanager
    def _transport(self) -> Iterator[httpx.Client]:
        if self._client is not None:
            yield self._client
        else:
            with httpx.Client(
                timeout=REQUEST_TIMEOUT_SECONDS, follow_redirects=False, trust_env=False
            ) as client:
                yield client

    def _generate_requests(
        self,
        client: httpx.Client,
        messages: list[dict[str, str]],
        jobs: tuple[RequestJob, ...],
        *,
        report_failures: bool,
    ) -> tuple[CandidateResponse, ...]:
        def request_candidate(job: RequestJob) -> CandidateResponse:
            params, profile, index = job
            sampling = (
                params.sampling_parameters() if profile is None else profile.sampling_parameters()
            )
            provider = (
                params.provider_settings() if profile is None else profile.provider_settings()
            )
            payload: dict[str, object] = {
                "model": params.model,
                "messages": messages,
                "n": 1,
                **sampling,
                "provider": provider,
            }
            for attempt in range(MAX_RETRIES + 1):
                try:
                    response = client.post(
                        ENDPOINT,
                        json=payload,
                        headers={"Authorization": f"Bearer {self._api_key}"},
                        timeout=REQUEST_TIMEOUT_SECONDS,
                        follow_redirects=False,
                    )
                except httpx.HTTPError:
                    raise OpenRouterError(
                        "OpenRouter transport failed; no output was written.",
                        code="transport_error",
                        attempts=attempt + 1,
                    ) from None
                if response.status_code == 429 or 500 <= response.status_code <= 599:
                    if attempt < MAX_RETRIES:
                        self._sleep(0.5 * (2**attempt))
                        continue
                if response.status_code != 200:
                    raise OpenRouterError(
                        f"OpenRouter request failed (HTTP {response.status_code}); "
                        "no output was written.",
                        code="http_error",
                        http_status=response.status_code,
                        attempts=attempt + 1,
                    )
                try:
                    data = response.json()
                except ValueError:
                    raise OpenRouterError(
                        "OpenRouter returned invalid JSON.",
                        code="invalid_json",
                        attempts=attempt + 1,
                    ) from None
                if not isinstance(data, dict):
                    raise OpenRouterError(
                        "OpenRouter returned an invalid response object.",
                        code="invalid_response",
                        attempts=attempt + 1,
                    )
                choices = data.get("choices")
                if not isinstance(choices, list) or not choices or not isinstance(choices[0], dict):
                    raise OpenRouterError(
                        "OpenRouter returned no usable choices.",
                        code="no_choices",
                        attempts=attempt + 1,
                    )
                message = choices[0].get("message")
                if not isinstance(message, dict) or not isinstance(message.get("content"), str):
                    raise OpenRouterError(
                        "OpenRouter returned no text content.", code="no_text", attempts=attempt + 1
                    )
                try:
                    text = _clean_content(message["content"])
                except OpenRouterError as exc:
                    exc.attempts = attempt + 1
                    raise
                return CandidateResponse(params.model, index, attempt + 1, text)
            raise OpenRouterError(
                "OpenRouter retry budget exhausted.",
                code="retry_exhausted",
                attempts=MAX_RETRIES + 1,
            )

        def record_candidate(job: RequestJob) -> CandidateResponse:
            try:
                return request_candidate(job)
            except OpenRouterError as exc:
                if not report_failures:
                    raise
                params, _, index = job
                return CandidateResponse(params.model, index, exc.attempts, None, exc.failure)

        with ThreadPoolExecutor(max_workers=min(len(jobs), MAX_CONCURRENT_REQUESTS)) as executor:
            # map preserves request order for deterministic tie-breaking.
            return tuple(executor.map(record_candidate, jobs))
