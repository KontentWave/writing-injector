import re
import time
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor

import httpx

from .config import ConfigurationError, validate_api_key
from .models import ModelParams

ENDPOINT = "https://openrouter.ai/api/v1/chat/completions"


class OpenRouterError(RuntimeError):
    """A redacted remote-generation failure."""


def _clean_content(text: str) -> str:
    text = text.strip()
    fence = re.fullmatch(r"```[^\r\n]*\r?\n(.*?)\r?\n```", text, re.DOTALL)
    if fence:
        text = fence.group(1).strip()
    text = re.sub(r"<!--\s*\[TIER\b.*?-->", "", text, flags=re.DOTALL | re.IGNORECASE).strip()
    if not text:
        raise OpenRouterError("OpenRouter returned an empty candidate.")
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
        try:
            validate_api_key(self._api_key)
        except ConfigurationError:
            raise OpenRouterError("A valid API key is required.") from None
        if self._client is not None:
            return self._generate(self._client, messages, params, n)
        with httpx.Client(timeout=45, follow_redirects=False, trust_env=False) as client:
            return self._generate(client, messages, params, n)

    def _generate(
        self, client: httpx.Client, messages: list[dict[str, str]], params: ModelParams, n: int
    ) -> list[str]:
        payload: dict[str, object] = {
            "model": params.model,
            "messages": messages,
            "n": 1,
            "temperature": params.temperature,
            "min_p": params.min_p,
            "top_p": params.top_p,
            "repetition_penalty": params.repetition_penalty,
            "provider": {"quantizations": list(params.quantizations), "allow_fallbacks": True},
        }

        def request_candidate(_: int) -> str:
            for attempt in range(3):
                try:
                    response = client.post(
                        ENDPOINT,
                        json=payload,
                        headers={"Authorization": f"Bearer {self._api_key}"},
                        timeout=45,
                        follow_redirects=False,
                    )
                except httpx.HTTPError:
                    raise OpenRouterError(
                        "OpenRouter transport failed; no output was written."
                    ) from None
                if response.status_code == 429 or 500 <= response.status_code <= 599:
                    if attempt < 2:
                        self._sleep(0.5 * (2**attempt))
                        continue
                if response.status_code != 200:
                    raise OpenRouterError(
                        f"OpenRouter request failed (HTTP {response.status_code}); "
                        "no output was written."
                    )
                try:
                    data = response.json()
                except ValueError:
                    raise OpenRouterError("OpenRouter returned invalid JSON.") from None
                if not isinstance(data, dict):
                    raise OpenRouterError("OpenRouter returned an invalid response object.")
                choices = data.get("choices")
                if not isinstance(choices, list) or not choices or not isinstance(choices[0], dict):
                    raise OpenRouterError("OpenRouter returned no usable choices.")
                message = choices[0].get("message")
                if not isinstance(message, dict) or not isinstance(message.get("content"), str):
                    raise OpenRouterError("OpenRouter returned no text content.")
                return _clean_content(message["content"])
            raise OpenRouterError("OpenRouter retry budget exhausted.")

        with ThreadPoolExecutor(max_workers=min(n, 3)) as executor:
            # map preserves request order for deterministic tie-breaking.
            return list(executor.map(request_candidate, range(n)))
