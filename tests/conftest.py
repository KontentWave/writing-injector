from collections.abc import Iterator
from pathlib import Path

import httpx
import pytest

from zafo_injector import cli
from zafo_injector.models import FrameDocument
from zafo_injector.openrouter_client import OpenRouterClient
from zafo_injector.parser import parse_frame
from zafo_injector.slovak_lint import LexiconRules


@pytest.fixture(autouse=True)
def isolate_private_data_and_network(monkeypatch: pytest.MonkeyPatch) -> None:
    for name in ("OPENROUTER_API_KEY", "ZAFO_VAULT_DIR", "GOOGLE_DRIVE_DIR"):
        monkeypatch.delenv(name, raising=False)

    def blocked(*args: object, **kwargs: object) -> None:
        raise AssertionError("Tests must never access the live network.")

    monkeypatch.setattr(httpx.HTTPTransport, "handle_request", blocked)


@pytest.fixture
def fixtures() -> Path:
    return Path(__file__).parent / "fixtures"


@pytest.fixture
def tracks_root(tmp_path: Path, fixtures: Path) -> Path:
    root = tmp_path / "synthetic-tracks"
    shared = root / "docs"
    shared.mkdir(parents=True)
    (shared / "SLOVAK_LEXICON.md").write_bytes((fixtures / "SLOVAK_LEXICON.md").read_bytes())
    for track in ("blog", "serial", "dark-romance"):
        docs = root / track / "docs"
        frames = root / track / ("posts" if track == "blog" else "episodes") / "nested"
        docs.mkdir(parents=True)
        frames.mkdir(parents=True)
        for language in ("sk", "en"):
            suffix = "_en" if language == "en" else ""
            original = (fixtures / f"frame{suffix}.md").read_bytes()
            (frames / f"frame{suffix}.md").write_bytes(
                b"\xef\xbb\xbf" + original.replace(b"\n", b"\r\n")
            )
            style_name = "STYLE_SHEET_EN.md" if language == "en" else "STYLE_SHEET.md"
            style = (
                (fixtures / style_name)
                .read_text(encoding="utf-8")
                .replace(
                    "## 1. Pinned Golden Voice Sample\n",
                    f"## 1. Pinned Golden Voice Sample\n\nSYNTHETIC_STYLE_{track}_{language}\n",
                    1,
                )
            )
            (docs / style_name).write_text(style, encoding="utf-8")
    return root


@pytest.fixture
def frame(fixtures: Path) -> FrameDocument:
    path = fixtures / "frame.md"
    return parse_frame(path.read_text(encoding="utf-8"), path)


@pytest.fixture
def rules(fixtures: Path) -> LexiconRules:
    return LexiconRules.from_markdown(fixtures / "SLOVAK_LEXICON.md")


@pytest.fixture
def candidate(fixtures: Path) -> str:
    return (fixtures / "candidate.txt").read_text(encoding="utf-8").strip()


@pytest.fixture
def english_frame(fixtures: Path) -> FrameDocument:
    path = fixtures / "frame_en.md"
    return parse_frame(path.read_text(encoding="utf-8"), path, language="en")


@pytest.fixture
def english_candidate(fixtures: Path) -> str:
    return (fixtures / "candidate_en.txt").read_text(encoding="utf-8").strip()


@pytest.fixture
def vault(tmp_path: Path) -> Path:
    path = tmp_path / "synthetic-vault"
    path.mkdir()
    (path / ".env").write_text("OPENROUTER_API_KEY=synthetic-test-key\n", encoding="utf-8")
    (path / "TIER4_ADDON.txt").write_text("Benign synthetic addon.", encoding="utf-8")
    return path


@pytest.fixture
def cli_args(fixtures: Path, vault: Path) -> list[str]:
    return [
        str(fixtures / "frame.md"),
        "--style-sheet",
        str(fixtures / "STYLE_SHEET.md"),
        "--lexicon",
        str(fixtures / "SLOVAK_LEXICON.md"),
        "--vault-dir",
        str(vault),
    ]


@pytest.fixture
def english_cli_args(fixtures: Path, vault: Path) -> list[str]:
    return [
        str(fixtures / "frame_en.md"),
        "--language",
        "en",
        "--style-sheet",
        str(fixtures / "STYLE_SHEET_EN.md"),
        "--vault-dir",
        str(vault),
    ]


@pytest.fixture
def mock_api(monkeypatch: pytest.MonkeyPatch, candidate: str) -> Iterator[list[httpx.Request]]:
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(200, json={"choices": [{"message": {"content": candidate}}]})

    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        monkeypatch.setattr(
            cli, "OpenRouterClient", lambda key: OpenRouterClient(key, client=client)
        )
        yield requests
