import re
from dataclasses import dataclass
from pathlib import Path

from .markdown import numbered_section, rule_table
from .models import FrameDocument, LintIssue, LintReport

_WORDS = re.compile(r"[^\W\d_]+(?:[-'’][^\W\d_]+)*", re.UNICODE)
_CLINICAL = ("pohlavný úd", "súlož", "lono", "jeho mužstvo", "kvet lona", "vlny rozkoše")


@dataclass(frozen=True)
class LexiconRules:
    czechisms: tuple[tuple[str, str], ...]
    calques: tuple[tuple[str, str], ...]
    clinical: tuple[str, ...] = _CLINICAL

    @classmethod
    def from_markdown(cls, lexicon_path: Path) -> "LexiconRules":
        text = lexicon_path.read_text(encoding="utf-8-sig")
        return cls(rule_table(numbered_section(text, 3)), rule_table(numbered_section(text, 4)))


def _sentences(text: str) -> list[str]:
    return [part.strip() for part in re.split(r"(?<=[.!?…])\s+", text) if part.strip()]


def _phrase_pattern(phrase: str) -> re.Pattern[str]:
    return re.compile(r"(?<!\w)" + r"\s+".join(map(re.escape, phrase.split())) + r"(?!\w)", re.I)


def lint_candidate(text: str, doc: FrameDocument, rules: LexiconRules | None = None) -> LintReport:
    if doc.language == "sk" and rules is None:
        raise ValueError("Slovak QA requires lexicon rules.")
    if doc.language == "en" and rules is not None:
        raise ValueError("English QA does not accept Slovak lexicon rules.")
    issues: list[LintIssue] = []
    words = len(_WORDS.findall(text))
    paragraphs = list(re.finditer(r"\S.*?(?=\r?\n[^\S\r\n]*\r?\n|\s*\Z)", text, re.DOTALL))

    def add(rule: str, match: str, suggestion: str, offset: int = 0, *, warn: bool = False) -> None:
        issues.append(
            LintIssue(
                rule,
                "warn" if warn else "error",
                match,
                suggestion,
                text.count("\n", 0, offset) + 1,
            )
        )

    if not doc.slot.min_words <= words <= doc.slot.max_words:
        add("WORD_COUNT", str(words), f"Use {doc.slot.min_words}-{doc.slot.max_words} words.")
    if not 2 <= len(paragraphs) <= 4:
        add("PARAGRAPH_BOUNDS", str(len(paragraphs)), "Use 2-4 paragraphs.")
    for paragraph in paragraphs:
        if len(_sentences(paragraph.group())) > 4:
            add(
                "PARAGRAPH_BOUNDS",
                paragraph.group(),
                "Use at most 4 sentences per paragraph.",
                paragraph.start(),
                warn=True,
            )
    if rules is not None:
        for rule_id, entries in (("CZECHISM", rules.czechisms), ("CALQUE", rules.calques)):
            for phrase, replacement in entries:
                for match in _phrase_pattern(phrase).finditer(text):
                    add(rule_id, match.group(), replacement, match.start())
        for phrase in rules.clinical:
            for match in _phrase_pattern(phrase).finditer(text):
                add(
                    "CLINICAL_OR_HARLEQUIN",
                    match.group(),
                    "Use natural colloquial wording.",
                    match.start(),
                )
        # Spaces preserve offsets while removing quoted dialogue from gender checks.
        narration = re.sub(r"„[^“]*“", lambda m: " " * len(m.group()), text, flags=re.DOTALL)
        pattern = r"\b[^\W\d_]+la\s+som\b" if doc.pov == "male" else r"\b[^\W\d_]+l\s+som\b"
        for match in re.finditer(pattern, narration, re.I):
            add(
                "POV_DRIFT",
                match.group(),
                f"Keep {doc.pov} first-person past tense.",
                match.start(),
            )
    boundaries: list[str] = []
    if doc.context_before:
        boundaries.append(_sentences(doc.context_before[-1])[-1])
    if doc.context_after:
        boundaries.append(_sentences(doc.context_after[0])[0])
    for sentence in dict.fromkeys(boundaries):
        for match in _phrase_pattern(sentence).finditer(text):
            add("BOUNDARY_ECHO", match.group(), "Do not repeat the frame boundary.", match.start())
    errors = sum(issue.severity == "error" for issue in issues)
    warnings = len(issues) - errors
    return LintReport(
        words, len(paragraphs), tuple(issues), 100 - 25 * errors - 5 * warnings, not errors
    )
