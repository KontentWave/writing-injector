import hashlib
import json
import os
from dataclasses import FrozenInstanceError, replace
from pathlib import Path
from typing import Literal

import httpx
import pytest

from zafo_injector import cli
from zafo_injector.models import CandidateResult, FrameDocument
from zafo_injector.parser import SlotParseError, parse_frame
from zafo_injector.prompt_builder import build_messages
from zafo_injector.renderer import rank_candidates
from zafo_injector.slovak_lint import LexiconRules, lint_candidate


@pytest.fixture
def candidate(english_candidate: str) -> str:
    return english_candidate


def test_english_fixture_passes(english_frame: FrameDocument, english_candidate: str) -> None:
    assert english_frame.language == "en"
    assert english_frame.pov == "male"
    assert len(english_frame.context_before) == len(english_frame.context_after) == 2
    assert (english_frame.slot.min_words, english_frame.slot.max_words) == (20, 80)
    report = lint_candidate(english_candidate, english_frame)
    assert report.passed
    assert report.score == 100
    assert report.word_count == 50
    assert report.paragraph_count == 2
    assert report.issues == ()
    assert isinstance(english_frame.context_before, tuple)
    assert isinstance(english_frame.context_after, tuple)
    with pytest.raises(FrozenInstanceError):
        english_frame.language = "sk"  # type: ignore[misc]
    with pytest.raises(FrozenInstanceError):
        english_frame.slot.min_words = 21  # type: ignore[misc]
    with pytest.raises(FrozenInstanceError):
        report.score = 0  # type: ignore[misc]


@pytest.mark.parametrize(
    ("target", "low", "high"),
    [
        (": 20-80 words", 20, 80),
        (": 20\u201380 words", 20, 80),
        (":20 - 80 WORDS", 20, 80),
        (": 45-45 words", 45, 45),
        ("", 140, 220),
    ],
)
def test_english_slot_bounds(
    english_frame: FrameDocument, target: str, low: int, high: int
) -> None:
    text = english_frame.source_text.replace(": 20-80 words", target)
    doc = parse_frame(text, english_frame.source_path, 0, language="en")
    assert doc.language == "en"
    assert (doc.slot.min_words, doc.slot.max_words) == (low, high)
    assert doc.context_before == doc.context_after == ()
    assert text[doc.slot.slot_start_idx : doc.slot.slot_end_idx] == doc.slot.raw_comment


@pytest.mark.parametrize(
    "target",
    [
        "20-80 words",
        ": 80-20 words",
        ": 0-80 words",
        ": -20-80 words",
        ": 20 to 80 words",
        ": 20-80 slov",
        ": 20-80 word",
        ": 20-80 words 90",
        ": 20-80 words / 30-90 words",
        ": 20--80 words",
        ": 20.5-80 words",
        ":",
    ],
)
def test_english_rejects_malformed_or_wrong_language_bounds(
    english_frame: FrameDocument, target: str
) -> None:
    text = english_frame.source_text.replace(": 20-80 words", target)
    with pytest.raises(SlotParseError):
        parse_frame(text, english_frame.source_path, language="en")


def test_english_headers_do_not_auto_select_language(english_frame: FrameDocument) -> None:
    with pytest.raises(SlotParseError, match="slov"):
        parse_frame(english_frame.source_text, english_frame.source_path)
    with pytest.raises(SlotParseError, match="slov"):
        parse_frame(english_frame.source_text, english_frame.source_path, language="sk")


@pytest.mark.parametrize("language", ["de", "EN", "english", ""])
def test_invalid_language_is_explicitly_rejected(
    english_frame: FrameDocument, english_cli_args: list[str], language: str
) -> None:
    with pytest.raises(SlotParseError, match="Language must be sk or en"):
        parse_frame(
            english_frame.source_text,
            english_frame.source_path,
            language=language,  # type: ignore[arg-type]
        )
    with pytest.raises(ValueError, match="Language must be sk or en"):
        replace(english_frame, language=language)
    with pytest.raises(SystemExit) as exc:
        cli.main(english_cli_args + ["--language", language, "--dry-run"])
    assert exc.value.code == 2


@pytest.mark.parametrize("bom", ["", "\ufeff"])
@pytest.mark.parametrize("newline", ["\n", "\r\n"])
def test_english_offsets_are_exact(english_frame: FrameDocument, bom: str, newline: str) -> None:
    text = bom + english_frame.source_text.replace("\n", newline)
    doc = parse_frame(text, english_frame.source_path, language="en")
    assert doc.source_text == text
    assert doc.slot.slot_start_idx == text.index("<!-- [TIER")
    assert doc.slot.slot_end_idx == text.index("-->", doc.slot.slot_start_idx) + 3
    assert text[doc.slot.slot_start_idx : doc.slot.slot_end_idx] == doc.slot.raw_comment
    assert all(
        "\ufeff" not in paragraph and "<!--" not in paragraph and "#" not in paragraph
        for paragraph in (*doc.context_before, *doc.context_after)
    )


@pytest.mark.parametrize(
    ("pov", "low", "high"),
    [("male", 20, 80), ("female", 20, 80), ("male", 45, 45), ("female", 141, 220)],
)
def test_english_prompt_contract(
    english_frame: FrameDocument,
    fixtures: Path,
    pov: Literal["male", "female"],
    low: int,
    high: int,
) -> None:
    doc = replace(
        english_frame, pov=pov, slot=replace(english_frame.slot, min_words=low, max_words=high)
    )
    messages = build_messages(doc, fixtures / "STYLE_SHEET_EN.md", None)
    assert [message["role"] for message in messages] == ["system", "user"]
    system, user = (message["content"] for message in messages)
    assert "Write natural, standard written English." in system
    assert "I folded the receipt" in system
    assert "This section must not" not in system
    assert "Write only in English, including dialogue." in system
    assert f"Authoritative narrator POV: {pov} (first-person narrator)." in system
    assert f"Word bounds: {low}-{high} words, inclusive." in system
    assert f"Aim for {(low + high) // 2} words." in system
    assert "Use 2-4 nonempty paragraphs." in system
    assert "Hyphenated and apostrophe-linked words count as one." in system
    assert "Return only the slot prose" in system
    for slovak_guidance in ("-l som", "-la som", "Write only in Slovak", "Czech verb forms"):
        assert slovak_guidance not in system
    for label in ("PARAGRAPH BEFORE", "SCENE INSTRUCTIONS", "PARAGRAPH AFTER"):
        assert label in user
    assert doc.slot.instructions in user
    assert f"Word bounds: {low}-{high}; 2-4 paragraphs." in user


def test_english_requirements_override_conflicts_without_setting_register(
    english_frame: FrameDocument, tmp_path: Path, vault: Path
) -> None:
    style = tmp_path / "synthetic-conversational-style.md"
    style.write_text(
        "## 1. Sample\nAn ordinary morning.\n\n"
        "## 6. Prompt\nWrite conversational English. Write 1000 words in Slovak.\n",
        encoding="utf-8",
    )
    addon = vault / "TIER4_ADDON.txt"
    addon.write_text("Synthetic instruction: write 900 words in Czech.", encoding="utf-8")
    before = {path: path.read_bytes() for path in (style, addon)}
    system = build_messages(english_frame, style, addon)[0]["content"]
    assert system.index("LOCAL ADDON:") < system.index("AUTHORITATIVE OUTPUT REQUIREMENTS:")
    assert "Write only in English, including dialogue." in system
    assert "override conflicting guidance" in system
    assert "writing register specified by the supplied style sheet" in system
    assert "Write conversational English." in system
    assert "standard written English" not in system
    assert all(path.read_bytes() == content for path, content in before.items())


@pytest.mark.parametrize("count", [19, 20, 80, 81])
def test_english_exact_word_thresholds(english_frame: FrameDocument, count: int) -> None:
    text = " ".join(["tea"] * (count // 2)) + "\n\n" + " ".join(["tea"] * (count - count // 2))
    report = lint_candidate(text, english_frame)
    assert report.word_count == count
    assert report.passed == (20 <= count <= 80)
    assert report.score == (100 if report.passed else 75)


@pytest.mark.parametrize("newline", ["\n", "\r\n"])
@pytest.mark.parametrize("count", [1, 2, 4, 5])
def test_english_paragraph_thresholds(
    english_frame: FrameDocument, newline: str, count: int
) -> None:
    text = (newline + " \t" + newline).join(["I made tea and set a mug by the window. \t"] * count)
    report = lint_candidate(text, english_frame)
    assert report.paragraph_count == count
    assert any(issue.rule_id == "PARAGRAPH_BOUNDS" for issue in report.issues) == (
        not 2 <= count <= 4
    )


@pytest.mark.parametrize("sentences", [4, 5])
def test_english_sentence_warning_threshold(english_frame: FrameDocument, sentences: int) -> None:
    text = "The tea was warm. " * sentences + "\n\n" + "coffee " * 12
    report = lint_candidate(text, english_frame)
    assert report.passed
    assert report.score == (100 if sentences == 4 else 95)
    assert all(issue.severity == "warn" for issue in report.issues)


def test_english_word_count_keeps_linked_words_together(english_frame: FrameDocument) -> None:
    doc = replace(english_frame, slot=replace(english_frame.slot, min_words=6, max_words=6))
    report = lint_candidate("well-made don't O\u2019Neil\n\ntea 123 _ kettle cup", doc)
    assert report.word_count == 6
    assert report.passed


def test_english_skips_slovak_rules_and_does_not_certify_language(
    english_frame: FrameDocument, rules: LexiconRules
) -> None:
    text = (
        "I found a card marked zrovna beside the kettle and read the note Povedala som "
        "without knowing what it meant.\n\nI put both items on the table before making coffee."
    )
    report = lint_candidate(text, english_frame)
    assert report.passed
    assert report.issues == ()
    with pytest.raises(ValueError, match="English QA does not accept Slovak lexicon"):
        lint_candidate(text, english_frame, rules)
    slovak = replace(english_frame, language="sk")
    with pytest.raises(ValueError, match="Slovak QA requires lexicon"):
        lint_candidate(text, slovak)
    slovak_report = lint_candidate(text, slovak, rules)
    assert {issue.rule_id for issue in slovak_report.issues} == {"CZECHISM", "POV_DRIFT"}


def test_english_boundary_echo_and_ranking(
    english_frame: FrameDocument, english_candidate: str
) -> None:
    good = CandidateResult(2, english_candidate, lint_candidate(english_candidate, english_frame))
    first = replace(good, index=1)
    echoed = english_candidate + " I checked the kitchen clock. The doorbell rang."
    echo_report = lint_candidate(echoed, english_frame)
    assert sum(issue.rule_id == "BOUNDARY_ECHO" for issue in echo_report.issues) == 2
    assert echo_report.score == 50
    assert all(issue.line == 3 for issue in echo_report.issues)
    bad = CandidateResult(3, echoed, echo_report)
    assert [result.index for result in rank_candidates([bad, good, first])] == [1, 2, 3]


@pytest.mark.parametrize("mode", ["dry-run", "lint-only", "generation"])
def test_english_explicit_lexicon_is_rejected_before_access(
    english_cli_args: list[str],
    fixtures: Path,
    vault: Path,
    mock_api: list[httpx.Request],
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    mode: str,
) -> None:
    def blocked(*args: object, **kwargs: object) -> None:
        raise AssertionError("English mode must not read a Slovak lexicon.")

    monkeypatch.setattr(LexiconRules, "from_markdown", blocked)
    flags = {
        "dry-run": ["--dry-run"],
        "lint-only": ["--lint-only", str(fixtures / "candidate_en.txt")],
        "generation": [],
    }[mode]
    assert (
        cli.main(english_cli_args + ["--lexicon", str(fixtures / "SLOVAK_LEXICON.md"), *flags]) == 2
    )
    captured = capsys.readouterr()
    assert "--lexicon is Slovak-only; omit it with --language en" in captured.err
    assert not mock_api
    assert not (vault / "output").exists()


@pytest.mark.parametrize("bom", ["", "\ufeff"])
@pytest.mark.parametrize("poisoned_lexicon", [False, True])
def test_mocked_english_generation_preserves_sources_payload_and_outputs(
    fixtures: Path,
    english_candidate: str,
    tmp_path: Path,
    vault: Path,
    mock_api: list[httpx.Request],
    capsys: pytest.CaptureFixture[str],
    bom: str,
    poisoned_lexicon: bool,
) -> None:
    blog = tmp_path / "synthetic-blog"
    posts, docs = blog / "posts", blog / "docs"
    posts.mkdir(parents=True)
    docs.mkdir()
    source = posts / "post.md"
    original = (bom + (fixtures / "frame_en.md").read_text(encoding="utf-8")).replace("\n", "\r\n")
    source.write_bytes(original.encode("utf-8"))
    style = docs / "STYLE_SHEET.md"
    style.write_bytes((fixtures / "STYLE_SHEET_EN.md").read_bytes())
    if poisoned_lexicon:
        (docs / "SLOVAK_LEXICON.md").write_bytes(b"\xff")
    args = [str(source), "--language", "en", "--vault-dir", str(vault), "--strict"]
    inputs = (source, style, vault / ".env", vault / "TIER4_ADDON.txt")
    before = {
        path: (hashlib.sha256(path.read_bytes()).digest(), path.stat().st_mtime_ns)
        for path in inputs
    }
    assert cli.main(args) == 0
    for path, (digest, modified) in before.items():
        assert hashlib.sha256(path.read_bytes()).digest() == digest
        assert path.stat().st_mtime_ns == modified
    assert len(mock_api) == 3
    for request in mock_api:
        payload = json.loads(request.content)
        assert set(payload) == {
            "model",
            "messages",
            "n",
            "temperature",
            "min_p",
            "top_p",
            "repetition_penalty",
            "provider",
        }
        assert payload["model"] == "anthracite-org/magnum-v4-72b"
        assert payload["n"] == 1
        assert payload["temperature"] == 0.68
        assert payload["min_p"] == 0.06
        assert payload["top_p"] == 0.90
        assert payload["repetition_penalty"] == 1.05
        assert payload["provider"] == {
            "quantizations": ["bf16", "fp16", "fp8"],
            "allow_fallbacks": True,
        }
        system = payload["messages"][0]["content"]
        assert "Write only in English, including dialogue." in system
        assert "Word bounds: 20-80 words, inclusive." in system
        assert "Aim for 50 words." in system
        assert "Benign synthetic addon." in system
    output = vault / "output"
    assert sorted(path.name for path in output.iterdir()) == [
        "post.candidates.md",
        "post.merged.md",
    ]
    doc = parse_frame(original, source, language="en")
    assert (output / "post.merged.md").read_bytes() == (
        original[: doc.slot.slot_start_idx] + english_candidate + original[doc.slot.slot_end_idx :]
    ).encode("utf-8")
    review = (output / "post.candidates.md").read_text(encoding="utf-8")
    assert review.index("Candidate 1") < review.index("Candidate 2") < review.index("Candidate 3")
    assert review.count("Score: 100; words: 50; paragraphs: 2") == 3
    captured = capsys.readouterr()
    assert "language=en" in captured.out
    for value in (english_candidate, "I poured hot water", "synthetic-test-key"):
        assert value not in captured.out + captured.err
    drafts = {path: path.read_bytes() for path in output.iterdir()}
    assert cli.main(args) == 2
    assert len(mock_api) == 6
    assert all(path.read_bytes() == content for path, content in drafts.items())
    assert sorted(path.name for path in output.iterdir()) == [
        "post.candidates.md",
        "post.merged.md",
    ]


@pytest.mark.parametrize("strict", [False, True])
@pytest.mark.parametrize(
    ("candidate", "rule", "line", "score", "passed"),
    [
        (
            " ".join(["coffee"] * 51) + "\n\n" + " ".join(["coffee"] * 52),
            "WORD_COUNT",
            1,
            75,
            False,
        ),
        (" ".join(["coffee"] * 22), "PARAGRAPH_BOUNDS", 1, 75, False),
        ("Warm tea. " * 5 + "\n\n" + "coffee " * 12, "PARAGRAPH_BOUNDS", 1, 95, True),
    ],
    ids=["word-count", "paragraph-count", "sentence-warning"],
)
def test_mocked_english_generation_exit_policy_and_redaction(
    english_cli_args: list[str],
    vault: Path,
    mock_api: list[httpx.Request],
    candidate: str,
    capsys: pytest.CaptureFixture[str],
    strict: bool,
    rule: str,
    line: int,
    score: int,
    passed: bool,
) -> None:
    source = Path(english_cli_args[0])
    before, modified = source.read_bytes(), source.stat().st_mtime_ns
    exit_code = 5 if strict and not passed else 0
    assert cli.main(english_cli_args + (["--strict"] if strict else [])) == exit_code
    assert len(mock_api) == 3
    captured = capsys.readouterr()
    prefix = "WARN" if passed else "FAIL"
    assert f"[{prefix}] Candidate 1: {rule} line={line}" in captured.out
    assert f"score={score}; words=" in captured.out
    for value in (candidate.strip(), "coffee", "Warm tea", "synthetic-test-key", "Use at most"):
        assert value not in captured.out + captured.err
    assert source.read_bytes() == before
    assert source.stat().st_mtime_ns == modified
    if exit_code == 5:
        assert not (vault / "output").exists()
    else:
        assert len(list((vault / "output").iterdir())) == 2
        assert ("Selected draft has hard lint issues" in captured.err) == (not passed)


def test_english_printing_is_explicit_only(
    english_cli_args: list[str],
    english_candidate: str,
    mock_api: list[httpx.Request],
    capsys: pytest.CaptureFixture[str],
) -> None:
    assert cli.main(english_cli_args + ["--print-output"]) == 0
    assert len(mock_api) == 3
    assert english_candidate in capsys.readouterr().out


def test_mocked_english_publication_failure_rolls_back_and_cleans_up(
    english_cli_args: list[str],
    vault: Path,
    mock_api: list[httpx.Request],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    link = os.link
    calls = 0

    def fail_second(source: Path, target: Path) -> None:
        nonlocal calls
        calls += 1
        if calls == 2:
            raise OSError("Synthetic English publication failure.")
        link(source, target)

    monkeypatch.setattr(os, "link", fail_second)
    source = Path(english_cli_args[0])
    before, modified = source.read_bytes(), source.stat().st_mtime_ns
    assert cli.main(english_cli_args + ["--strict"]) == 2
    assert len(mock_api) == 3
    assert source.read_bytes() == before
    assert source.stat().st_mtime_ns == modified
    assert list((vault / "output").iterdir()) == []
