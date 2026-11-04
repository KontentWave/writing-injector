from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal


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
