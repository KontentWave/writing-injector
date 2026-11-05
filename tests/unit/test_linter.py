from dataclasses import replace

import pytest

from zafo_injector.models import FrameDocument
from zafo_injector.slovak_lint import LexiconRules, lint_candidate


def test_clean_candidate_passes(frame: FrameDocument, rules: LexiconRules, candidate: str) -> None:
    report = lint_candidate(candidate, frame, rules)
    assert report.passed
    assert report.score == 100
    assert report.word_count == 37
    assert report.paragraph_count == 2


@pytest.mark.parametrize(
    ("text", "rule_id"),
    [
        ("VŮBEC", "CZECHISM"),
        ("zrovna", "CZECHISM"),
        ("záda", "CZECHISM"),
        ("polštář", "CZECHISM"),
        ("udělal jsem", "CZECHISM"),
        ("vydýchol som dych, o ktorom som nevedel", "CALQUE"),
        ("lono", "CLINICAL_OR_HARLEQUIN"),
    ],
)
def test_banned_terms(
    frame: FrameDocument, rules: LexiconRules, candidate: str, text: str, rule_id: str
) -> None:
    report = lint_candidate(candidate + "\n\n" + text, frame, rules)
    assert any(issue.rule_id == rule_id and issue.line == 5 for issue in report.issues)
    assert not report.passed


@pytest.mark.parametrize(
    ("pov", "text", "drift"),
    [
        ("male", "Povedala som to potichu.", True),
        ("male", "„Povedala som mu,“ povedal sused.", False),
        ("female", "Povedal som to potichu.", True),
        ("female", "Bol som doma.", True),
        ("female", "Šiel som domov.", True),
        ("female", "„Povedal som mu,“ povedala suseda.", False),
        ("female", "Povedala som to potichu.", False),
    ],
)
def test_pov_lock(
    frame: FrameDocument, rules: LexiconRules, pov: str, text: str, drift: bool
) -> None:
    doc = replace(frame, pov="male" if pov == "male" else "female")
    report = lint_candidate(text, doc, rules)
    assert any(issue.rule_id == "POV_DRIFT" for issue in report.issues) == drift


@pytest.mark.parametrize("count", [139, 140, 220, 221])
def test_exact_word_thresholds(frame: FrameDocument, rules: LexiconRules, count: int) -> None:
    doc = replace(frame, slot=replace(frame.slot, min_words=140, max_words=220))
    text = " ".join(["káva"] * (count // 2)) + "\n\n" + " ".join(["káva"] * (count - count // 2))
    report = lint_candidate(text, doc, rules)
    assert report.word_count == count
    assert report.passed == (140 <= count <= 220)


@pytest.mark.parametrize("count", [1, 2, 4, 5])
def test_paragraph_thresholds(frame: FrameDocument, rules: LexiconRules, count: int) -> None:
    text = "\n\n".join(["káva ráno okno stôl hrnček lyžica pokoj"] * count)
    report = lint_candidate(text, frame, rules)
    bounds = [issue for issue in report.issues if issue.rule_id == "PARAGRAPH_BOUNDS"]
    assert bool(bounds) == (count not in (2, 4))


def test_sentence_warning_and_score(frame: FrameDocument, rules: LexiconRules) -> None:
    text = "Jedna veta. Druhá veta. Tretia veta. Štvrtá veta. Piata veta.\n\n" + "káva " * 12
    report = lint_candidate(text, frame, rules)
    assert report.passed
    assert report.score == 95
    assert len(report.issues) == 1
    assert report.issues[0].severity == "warn"


def test_boundary_echo(frame: FrameDocument, rules: LexiconRules, candidate: str) -> None:
    report = lint_candidate(
        candidate + " Pozrel som sa na hodiny. Vtom zazvonil telefón.", frame, rules
    )
    assert sum(issue.rule_id == "BOUNDARY_ECHO" for issue in report.issues) == 2
    assert report.score == 50


def test_phrase_boundaries(frame: FrameDocument, rules: LexiconRules, candidate: str) -> None:
    report = lint_candidate(candidate + " zrovnanie", frame, rules)
    assert not any(issue.rule_id == "CZECHISM" for issue in report.issues)


@pytest.mark.parametrize("sentences", [4, 5])
def test_exact_sentence_warning_threshold(
    frame: FrameDocument, rules: LexiconRules, sentences: int
) -> None:
    text = "Ranná káva vonia. " * sentences + "\n\n" + "pokoj " * 12
    report = lint_candidate(text, frame, rules)
    assert report.passed
    assert report.score == (100 if sentences == 4 else 95)


def test_phrase_whitespace_boundaries_and_negative_score(
    frame: FrameDocument, rules: LexiconRules, candidate: str
) -> None:
    text = candidate + "\n\n" + "UDĚLAL\tJSEM " * 5 + "xudělal jsem udělal jsemx"
    report = lint_candidate(text, frame, rules)
    matches = [issue for issue in report.issues if issue.rule_id == "CZECHISM"]
    assert len(matches) == 5
    assert all(issue.line == 5 for issue in matches)
    errors = sum(issue.severity == "error" for issue in report.issues)
    warnings = sum(issue.severity == "warn" for issue in report.issues)
    assert report.score == 100 - 25 * errors - 5 * warnings < 0


def test_multiline_dialogue_preserves_issue_line_numbers(
    frame: FrameDocument, rules: LexiconRules
) -> None:
    text = "„Povedala som\nráno,“ povedal sused.\n\nPovedala som to potichu."
    report = lint_candidate(text, frame, rules)
    drift = [issue for issue in report.issues if issue.rule_id == "POV_DRIFT"]
    assert len(drift) == 1
    assert drift[0].line == 4


@pytest.mark.parametrize("newline", ["\n", "\r\n"])
@pytest.mark.parametrize("count", [1, 2, 4, 5])
def test_trailing_whitespace_does_not_merge_paragraphs(
    frame: FrameDocument, rules: LexiconRules, newline: str, count: int
) -> None:
    text = (newline + " \t" + newline).join(["káva ráno okno stôl hrnček lyžica pokoj \t"] * count)
    report = lint_candidate(text, frame, rules)
    assert report.paragraph_count == count
    bounds = [issue for issue in report.issues if issue.rule_id == "PARAGRAPH_BOUNDS"]
    assert bool(bounds) == (not 2 <= count <= 4)
