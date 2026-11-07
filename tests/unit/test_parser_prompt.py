from dataclasses import FrozenInstanceError, replace
from pathlib import Path

import pytest

from zafo_injector.markdown import SourceFormatError, numbered_section
from zafo_injector.models import FrameDocument
from zafo_injector.parser import SlotParseError, parse_frame
from zafo_injector.prompt_builder import build_messages


def test_parser_extracts_bounds_pov_and_context(frame: FrameDocument) -> None:
    assert frame.pov == "male"
    assert (frame.slot.min_words, frame.slot.max_words) == (20, 80)
    assert len(frame.context_before) == len(frame.context_after) == 2
    assert all(
        "#" not in paragraph and "<!--" not in paragraph for paragraph in frame.context_before
    )
    assert "Opíš" in frame.slot.instructions
    assert (
        frame.source_text[frame.slot.slot_start_idx : frame.slot.slot_end_idx]
        == frame.slot.raw_comment
    )
    with pytest.raises(FrozenInstanceError):
        frame.pov = "female"  # type: ignore[misc]


@pytest.mark.parametrize("dash", ["-", "–"])
def test_parser_word_target_dashes(frame: FrameDocument, dash: str) -> None:
    text = frame.source_text.replace("20–80", f"140{dash}220")
    doc = parse_frame(text, frame.source_path)
    assert (doc.slot.min_words, doc.slot.max_words) == (140, 220)


def test_parser_defaults_and_female(frame: FrameDocument) -> None:
    text = frame.source_text.replace(": 20–80 slov", "").replace(
        "Male (-l som)", "Female (-la som)"
    )
    doc = parse_frame(text, frame.source_path, window_paragraphs=0)
    assert doc.pov == "female"
    assert (doc.slot.min_words, doc.slot.max_words) == (140, 220)
    assert doc.context_before == doc.context_after == ()


@pytest.mark.parametrize("kind", ["missing", "duplicate", "pov", "reverse", "malformed"])
def test_parser_errors(frame: FrameDocument, kind: str) -> None:
    text = {
        "missing": frame.source_text.replace(frame.slot.raw_comment, ""),
        "duplicate": frame.source_text + frame.slot.raw_comment,
        "pov": frame.source_text.replace("POV:", "Narrator:"),
        "reverse": frame.source_text.replace("20–80", "80–20"),
        "malformed": frame.source_text.replace("20–80", "20 to 80"),
    }[kind]
    with pytest.raises(SlotParseError):
        parse_frame(text, frame.source_path)


def test_comments_are_paragraph_boundaries(frame: FrameDocument) -> None:
    text = frame.source_text.replace(
        "# Ranná káva", "# Ranná káva\n\nEarlier prose.\n<!-- ignored -->\nLater prose."
    )
    doc = parse_frame(text, frame.source_path, window_paragraphs=4)
    assert doc.context_before[:2] == ("Earlier prose.", "Later prose.")


def test_prompt_sections_addon_and_female(
    frame: FrameDocument, fixtures: Path, tmp_path: Path
) -> None:
    addon = tmp_path / "synthetic-addon.txt"
    addon.write_text("Test-only addon.", encoding="utf-8")
    messages = build_messages(replace(frame, pov="female"), fixtures / "STYLE_SHEET.md", addon)
    assert [message["role"] for message in messages] == ["system", "user"]
    assert "Ráno som otvoril okno." in messages[0]["content"]
    assert "Test-only addon." in messages[0]["content"]
    assert "female (-la som)" in messages[0]["content"]
    assert "Male narrator" not in messages[0]["content"]
    assert "This section must not" not in messages[0]["content"]
    assert "ODSEK PRED" in messages[1]["content"]
    assert "POKYNY PRE SCÉNU" in messages[1]["content"]
    assert "ODSEK PO" in messages[1]["content"]


def test_numbered_section_missing() -> None:
    with pytest.raises(SourceFormatError):
        numbered_section("## 1. Empty\n\n## 2. Other\ntext", 1)


def test_numbered_section_preserves_headings_inside_fences() -> None:
    text = "## §6 Prompt\n```text\n## A prompt heading\nKeep this.\n```\n## 7. Other\nomit"
    section = numbered_section(text, 6)
    assert "Keep this." in section
    assert "omit" not in section


@pytest.mark.parametrize("bounds", ["-20–80 slov", "20–80 slov 90", "20–80 slov / 30–90 slov", ":"])
def test_parser_rejects_partially_valid_bounds(frame: FrameDocument, bounds: str) -> None:
    text = frame.source_text.replace("20–80 slov", bounds)
    with pytest.raises(SlotParseError):
        parse_frame(text, frame.source_path)


def test_parser_rejects_duplicate_pov_in_one_comment(frame: FrameDocument) -> None:
    text = frame.source_text.replace("POV: Male (-l som)", "POV: Male\nPOV: Female")
    with pytest.raises(SlotParseError):
        parse_frame(text, frame.source_path)


def test_bom_is_not_context(frame: FrameDocument) -> None:
    text = "\ufeff<!-- POV: Male (-l som) -->\n# Heading\n\nBefore.\n\n"
    text += frame.slot.raw_comment + "\n\nAfter."
    doc = parse_frame(text, frame.source_path)
    assert doc.context_before == ("Before.",)
    assert doc.context_after == ("After.",)
    assert doc.source_text == text
    assert text[doc.slot.slot_start_idx : doc.slot.slot_end_idx] == doc.slot.raw_comment


def test_fence_with_trailing_text_is_not_a_closing_fence() -> None:
    text = (
        "## 6. Prompt\n```text\nKeep.\n```not-a-close\n"
        "## 7. Still an example\nKeep too.\n```\n## 7. Real section\nOmit."
    )
    section = numbered_section(text, 6)
    assert "Keep too." in section
    assert "Omit." not in section


@pytest.mark.parametrize(
    ("pov", "low", "high"),
    [("male", 20, 80), ("female", 140, 220), ("male", 45, 45), ("female", 141, 220)],
)
def test_prompt_has_authoritative_language_and_length_requirements(
    frame: FrameDocument, fixtures: Path, pov: str, low: int, high: int
) -> None:
    doc = replace(frame, pov=pov, slot=replace(frame.slot, min_words=low, max_words=high))
    messages = build_messages(doc, fixtures / "STYLE_SHEET.md", None)
    system, user = (message["content"] for message in messages)
    gender = "-la som" if pov == "female" else "-l som"
    assert "Write only in Slovak, including dialogue." in system
    assert "Do not mix in Czech words or Czech verb forms." in system
    assert f"Authoritative narrator POV: {pov} ({gender})." in system
    assert f"Word bounds: {low}-{high} words, inclusive." in system
    assert f"Aim for {(low + high) // 2} words." in system
    assert "Use 2-4 nonempty paragraphs." in system
    assert "Hyphenated and apostrophe-linked words count as one." in system
    assert f"Word bounds: {low}-{high}; 2-4 paragraphs." in user


def test_prompt_requirements_follow_and_override_conflicting_synthetic_anchors(
    frame: FrameDocument, tmp_path: Path, vault: Path
) -> None:
    style = tmp_path / "synthetic-style.md"
    style.write_text(
        "## 1. Sample\nAn ordinary morning.\n\n## 6. Template\nWrite 1000 words in Czech.\n",
        encoding="utf-8",
    )
    addon = vault / "TIER4_ADDON.txt"
    addon.write_text("Synthetic example: write 900 words in Czech.", encoding="utf-8")
    style_before, addon_before = style.read_bytes(), addon.read_bytes()
    system = build_messages(frame, style, addon)[0]["content"]
    assert system.index("LOCAL ADDON:") < system.index("AUTHORITATIVE OUTPUT REQUIREMENTS:")
    assert "override conflicting guidance" in system
    assert "Word bounds: 20-80 words, inclusive." in system
    assert "Write only in Slovak, including dialogue." in system
    assert style.read_bytes() == style_before
    assert addon.read_bytes() == addon_before


def test_synthetic_acceptance_style_requires_standard_written_slovak(
    frame: FrameDocument, fixtures: Path
) -> None:
    system = build_messages(frame, fixtures / "STYLE_SHEET.md", None)[0]["content"]
    assert "Write natural, standard written Slovak, without colloquialisms." in system
    assert "Write colloquial Slovak." not in system


def test_prompt_register_remains_style_sheet_driven(frame: FrameDocument, tmp_path: Path) -> None:
    style = tmp_path / "synthetic-colloquial-style.md"
    style.write_text(
        "## 1. Sample\nRáno som otvoril okno.\n\n## 6. Prompt\nWrite colloquial Slovak.\n",
        encoding="utf-8",
    )
    system = build_messages(frame, style, None)[0]["content"]
    assert "Write colloquial Slovak." in system
    assert "standard written Slovak" not in system
