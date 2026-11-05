import re
from pathlib import Path
from typing import Literal

from .models import FrameDocument, SlotSpec


class SlotParseError(ValueError):
    """A frame does not have one well-formed slot and explicit POV."""


_COMMENTS = re.compile(r"<!--.*?-->", re.DOTALL)
_SLOT = re.compile(r"^\s*\[TIER\b[^\]\r\n]*\bINSERT SLOT\b", re.IGNORECASE)


def _paragraphs(text: str) -> tuple[str, ...]:
    text = text.removeprefix("\ufeff")
    text = _COMMENTS.sub("\n\n", text)
    text = re.sub(r"^#{1,6}\s+.*$", "\n\n", text, flags=re.MULTILINE)
    return tuple(part.strip() for part in re.split(r"\n\s*\n", text) if part.strip())


def parse_frame(markdown_text: str, source_path: Path, window_paragraphs: int = 2) -> FrameDocument:
    if window_paragraphs < 0:
        raise SlotParseError("Context window must be nonnegative.")
    comments = list(_COMMENTS.finditer(markdown_text))
    slots = [comment for comment in comments if _SLOT.match(comment.group()[4:-3])]
    if len(slots) != 1:
        raise SlotParseError("Expected exactly one TIER INSERT SLOT comment.")
    match = slots[0]
    metadata = [
        comment.group()
        for comment in comments
        if comment.end() <= match.start() and re.search(r"\bPOV\s*:", comment.group(), re.I)
    ]
    if len(metadata) != 1:
        raise SlotParseError("Expected one explicit POV metadata comment before the slot.")
    if len(re.findall(r"\bPOV\s*:", metadata[0], re.I)) != 1:
        raise SlotParseError("Expected exactly one POV field in the metadata comment.")
    pov_match = re.search(r"\bPOV\s*:\s*(male|female)\b", metadata[0], re.I)
    if not pov_match:
        raise SlotParseError("POV must explicitly specify Male or Female.")
    pov: Literal["male", "female"] = "female" if pov_match.group(1).lower() == "female" else "male"
    body = match.group()[4:-3].strip()
    header, separator, instructions = body.partition("]")
    if not separator:
        raise SlotParseError("Slot header must end with ].")
    target = re.split(r"INSERT SLOT", header, flags=re.I)[1].strip()
    bounds = re.fullmatch(r":\s*(\d+)\s*[-–]\s*(\d+)\s+slov", target, re.I)
    if bounds:
        low, high = map(int, bounds.groups())
    elif target:
        raise SlotParseError("Malformed slot word bounds.")
    else:
        low, high = 140, 220
    if not 0 < low <= high:
        raise SlotParseError("Slot word bounds must be positive and ordered.")
    before = _paragraphs(markdown_text[: match.start()])
    after = _paragraphs(markdown_text[match.end() :])
    return FrameDocument(
        source_path=source_path,
        source_text=markdown_text,
        pov=pov,
        context_before=before[-window_paragraphs:] if window_paragraphs else (),
        context_after=after[:window_paragraphs],
        slot=SlotSpec(match.group(), low, high, instructions.strip(), match.start(), match.end()),
    )
