from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal

Language = Literal["sk", "en"]
MAX_CONCURRENT_REQUESTS = 3
REQUEST_TIMEOUT_SECONDS = 45
MAX_RETRIES = 2
MAX_MATRIX_MODELS = 3
MAX_MATRIX_REQUESTS = 9
FailureCode = Literal[
    "http_error",
    "transport_error",
    "invalid_json",
    "invalid_response",
    "no_choices",
    "no_text",
    "empty_candidate",
    "retry_exhausted",
    "generation_error",
]
ArenaStatus = Literal["completed", "api_failed", "strict_lint_failed"]


@dataclass(frozen=True)
class SlotSpec:
    raw_comment: str
    min_words: int
    max_words: int
    instructions: str
    slot_start_idx: int
    slot_end_idx: int


@dataclass(frozen=True)
class FrameDocument:
    source_path: Path
    source_text: str = field(repr=False)
    pov: Literal["male", "female"]
    context_before: tuple[str, ...]
    context_after: tuple[str, ...]
    slot: SlotSpec
    language: Language = "sk"

    def __post_init__(self) -> None:
        if self.language not in ("sk", "en"):
            raise ValueError("Language must be sk or en.")


@dataclass(frozen=True)
class ModelParams:
    model: str = "anthracite-org/magnum-v4-72b"
    temperature: float = 0.68
    min_p: float = 0.06
    top_p: float = 0.90
    repetition_penalty: float = 1.05
    quantizations: tuple[str, ...] = ("bf16", "fp16", "fp8")

    def __post_init__(self) -> None:
        if not self.model.strip():
            raise ValueError("Model must not be empty.")
        if not 0 <= self.temperature <= 2:
            raise ValueError("Temperature must be between 0 and 2.")
        if not 0 <= self.min_p <= 1 or not 0 < self.top_p <= 1:
            raise ValueError("Invalid sampling probability.")
        if not 0 < self.repetition_penalty <= 2 or not self.quantizations:
            raise ValueError("Invalid repetition penalty or quantizations.")

    def sampling_parameters(self) -> dict[str, float]:
        return {
            "temperature": self.temperature,
            "min_p": self.min_p,
            "top_p": self.top_p,
            "repetition_penalty": self.repetition_penalty,
        }

    def provider_settings(self) -> dict[str, object]:
        return {"quantizations": list(self.quantizations), "allow_fallbacks": True}


@dataclass(frozen=True)
class ModelProfile:
    params: ModelParams
    supported_parameters: tuple[str, ...]

    def __post_init__(self) -> None:
        supported = set(self.supported_parameters)
        if (
            not isinstance(self.supported_parameters, tuple)
            or len(supported) != len(self.supported_parameters)
            or not {"temperature", "top_p"} <= supported
            or not supported <= self.params.sampling_parameters().keys()
        ):
            raise ValueError("Invalid model profile sampling parameters.")

    @property
    def model_id(self) -> str:
        return self.params.model

    def sampling_parameters(self) -> dict[str, float]:
        return {
            name: value
            for name, value in self.params.sampling_parameters().items()
            if name in self.supported_parameters
        }

    def provider_settings(self) -> dict[str, object]:
        return {**self.params.provider_settings(), "require_parameters": True}

    @property
    def omitted_parameters(self) -> tuple[str, ...]:
        return tuple(
            name
            for name in self.params.sampling_parameters()
            if name not in self.supported_parameters
        )


@dataclass(frozen=True)
class LintIssue:
    rule_id: str
    severity: Literal["error", "warn"]
    match: str
    suggestion: str
    line: int


@dataclass(frozen=True)
class LintReport:
    word_count: int
    paragraph_count: int
    issues: tuple[LintIssue, ...]
    score: int
    passed: bool


@dataclass(frozen=True)
class CandidateResult:
    index: int
    text: str = field(repr=False)
    report: LintReport


@dataclass(frozen=True)
class RequestFailure:
    code: FailureCode
    http_status: int | None = None

    def __post_init__(self) -> None:
        if (self.code == "http_error") != (self.http_status is not None):
            raise ValueError("Only HTTP failures must include an HTTP status.")
        if self.code not in (
            "http_error",
            "transport_error",
            "invalid_json",
            "invalid_response",
            "no_choices",
            "no_text",
            "empty_candidate",
            "retry_exhausted",
            "generation_error",
        ):
            raise ValueError("Unknown request failure code.")

    @property
    def message(self) -> str:
        if self.code == "http_error":
            return f"OpenRouter request failed (HTTP {self.http_status})."
        messages = {
            "transport_error": "OpenRouter transport failed.",
            "invalid_json": "OpenRouter returned invalid JSON.",
            "invalid_response": "OpenRouter returned an invalid response object.",
            "no_choices": "OpenRouter returned no usable choices.",
            "no_text": "OpenRouter returned no text content.",
            "empty_candidate": "OpenRouter returned an empty candidate.",
            "retry_exhausted": "OpenRouter retry budget exhausted.",
            "generation_error": "OpenRouter generation failed.",
        }
        return messages[self.code]


@dataclass(frozen=True)
class CandidateResponse:
    model_id: str
    index: int
    attempts: int
    text: str | None = field(repr=False)
    failure: RequestFailure | None = None

    def __post_init__(self) -> None:
        if not self.model_id.strip() or self.index < 1:
            raise ValueError("Candidate identity must include a model and positive index.")
        if not 1 <= self.attempts <= MAX_RETRIES + 1:
            raise ValueError("Candidate attempts exceed the request budget.")
        if (self.text is not None) != (self.failure is None):
            raise ValueError("A candidate must contain either text or an explicit failure.")
        if self.text is not None and not self.text.strip():
            raise ValueError("Successful candidate text must not be empty.")

    @property
    def candidate_id(self) -> str:
        return f"{self.model_id}::candidate-{self.index}"


@dataclass(frozen=True)
class ArenaCandidate:
    response: CandidateResponse
    report: LintReport | None

    def __post_init__(self) -> None:
        if (self.response.failure is None) != (self.report is not None):
            raise ValueError("Only successful requests must have a lint report.")


@dataclass(frozen=True)
class ArenaRun:
    profiles: tuple[ModelProfile, ...]
    candidates_per_model: int
    candidates: tuple[ArenaCandidate, ...]
    strict: bool = False

    def __post_init__(self) -> None:
        if not isinstance(self.profiles, tuple) or not isinstance(self.candidates, tuple):
            raise ValueError("Arena profiles and candidates must be immutable tuples.")
        model_ids = {profile.model_id for profile in self.profiles}
        if not 2 <= len(self.profiles) <= MAX_MATRIX_MODELS or len(model_ids) != len(self.profiles):
            raise ValueError("An arena requires two or three distinct models.")
        if self.candidates_per_model < 1 or self.initial_requests > MAX_MATRIX_REQUESTS:
            raise ValueError("An arena permits at most nine initial candidate requests.")
        expected = {
            (model_id, index)
            for model_id in model_ids
            for index in range(1, self.candidates_per_model + 1)
        }
        actual = {
            (candidate.response.model_id, candidate.response.index) for candidate in self.candidates
        }
        if actual != expected or len(self.candidates) != len(expected):
            raise ValueError("Arena results must include exactly every planned model/candidate.")

    @property
    def initial_requests(self) -> int:
        return len(self.profiles) * self.candidates_per_model

    @property
    def http_attempts(self) -> int:
        return sum(candidate.response.attempts for candidate in self.candidates)

    def for_model(self, model_id: str) -> tuple[ArenaCandidate, ...]:
        if model_id not in {profile.model_id for profile in self.profiles}:
            raise ValueError("Model is not part of this arena.")
        return tuple(
            sorted(
                (
                    candidate
                    for candidate in self.candidates
                    if candidate.response.model_id == model_id
                ),
                key=lambda candidate: candidate.response.index,
            )
        )

    def hard_pass_count(self, model_id: str) -> int:
        return sum(
            candidate.report is not None and candidate.report.passed
            for candidate in self.for_model(model_id)
        )

    @property
    def status(self) -> ArenaStatus:
        if any(candidate.response.failure is not None for candidate in self.candidates):
            return "api_failed"
        if self.strict and any(
            self.hard_pass_count(profile.model_id) == 0 for profile in self.profiles
        ):
            return "strict_lint_failed"
        return "completed"

    @property
    def exit_code(self) -> int:
        return {"completed": 0, "api_failed": 4, "strict_lint_failed": 5}[self.status]
