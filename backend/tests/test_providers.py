"""Real providers against mocked HTTP (httpx.MockTransport) and a fake Gemini client.

No network: every external call is intercepted, so these tests check request
shape, response parsing and error mapping.
"""

import json
from collections.abc import Callable
from types import SimpleNamespace
from typing import Any

import httpx
import pytest
from google.genai import errors as genai_errors
from pydantic import BaseModel, SecretStr

from app.config import Settings
from app.providers import build_providers
from app.providers.books import FallbackBooksProvider, GoogleBooksProvider, OpenLibraryProvider
from app.providers.errors import ErrorKind, ProviderError, RetryPolicy
from app.providers.llm import GeminiProvider, LLMProvider, map_gemini_error
from app.providers.web import TavilyProvider
from app.providers.youtube import (
    UnconfiguredYouTube,
    VideoCandidate,
    YouTubeDataProvider,
    parse_iso_duration,
    transcript_text,
)

FAST = RetryPolicy(max_attempts=3, min_wait=0, max_wait=0)


def mock_client(handler: Callable[[httpx.Request], httpx.Response]) -> httpx.Client:
    return httpx.Client(transport=httpx.MockTransport(handler))


# ---------------------------------------------------------------------------
# Tavily
# ---------------------------------------------------------------------------


def test_tavily_search_request_and_parsing() -> None:
    seen: list[httpx.Request] = []

    def handler(req: httpx.Request) -> httpx.Response:
        seen.append(req)
        return httpx.Response(200, json={"query": "q", "results": [
            {"title": "HTTP methods", "url": "https://developer.mozilla.org/x", "content": "GET retrieves", "score": 0.9},
            {"title": "no url"},
        ]})

    tavily = TavilyProvider("tvly-key", exclude_domains=["youtube.com"], client=mock_client(handler), retry=FAST)
    results = tavily.search("http methods", max_results=3)

    body = json.loads(seen[0].content)
    assert seen[0].headers["Authorization"] == "Bearer tvly-key"
    assert body["search_depth"] == "basic" and body["max_results"] == 3 and body["include_answer"] is False
    assert body["exclude_domains"] == ["youtube.com"]
    assert [(r.url, r.snippet, r.query) for r in results] == [("https://developer.mozilla.org/x", "GET retrieves", "http methods")]


def test_tavily_quota_error_is_not_retried() -> None:
    calls = {"n": 0}

    def handler(req: httpx.Request) -> httpx.Response:
        calls["n"] += 1
        return httpx.Response(432, json={"detail": {"error": "limit"}})

    tavily = TavilyProvider("k", client=mock_client(handler), retry=FAST)
    with pytest.raises(ProviderError) as info:
        tavily.search("q")
    assert info.value.kind == ErrorKind.quota_exhausted and calls["n"] == 1
    assert "credit" in info.value.message


def test_tavily_rate_limit_is_retried_then_succeeds() -> None:
    responses = [httpx.Response(429), httpx.Response(503), httpx.Response(200, json={"results": []})]

    tavily = TavilyProvider("k", client=mock_client(lambda req: responses.pop(0)), retry=FAST)
    assert tavily.search("q") == []
    assert responses == []


def test_tavily_timeout_becomes_readable_error() -> None:
    def handler(req: httpx.Request) -> httpx.Response:
        raise httpx.ReadTimeout("slow", request=req)

    tavily = TavilyProvider("k", client=mock_client(handler), retry=FAST)
    with pytest.raises(ProviderError) as info:
        tavily.search("q")
    assert info.value.kind == ErrorKind.timeout


def test_tavily_extract_batches_and_skips_failures() -> None:
    batches: list[list[str]] = []

    def handler(req: httpx.Request) -> httpx.Response:
        urls = json.loads(req.content)["urls"]
        batches.append(urls)
        return httpx.Response(200, json={
            "results": [{"url": u, "raw_content": f"text of {u}"} for u in urls if not u.endswith("/bad")],
            "failed_results": [{"url": u, "error": "blocked"} for u in urls if u.endswith("/bad")],
        })

    urls = [f"https://site.org/{i}" for i in range(24)] + ["https://site.org/bad"]
    pages = TavilyProvider("k", client=mock_client(handler), retry=FAST).extract(urls)
    assert [len(b) for b in batches] == [20, 5]
    assert len(pages) == 24 and all(p.content.startswith("text of") for p in pages)


def test_tavily_requires_key() -> None:
    with pytest.raises(ProviderError) as info:
        TavilyProvider("")
    assert info.value.kind == ErrorKind.not_configured


# ---------------------------------------------------------------------------
# YouTube
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(("iso", "seconds"), [
    ("PT12M34S", 754), ("PT1H2M", 3720), ("PT45S", 45), ("P1DT1S", 86401), ("P0D", 0), ("bogus", None), (None, None),
])
def test_parse_iso_duration(iso: str | None, seconds: int | None) -> None:
    assert parse_iso_duration(iso) == seconds


def _youtube_handler(req: httpx.Request) -> httpx.Response:
    assert req.url.params["key"] == "yt-key"
    if req.url.path.endswith("/search"):
        assert req.url.params["type"] == "video"
        return httpx.Response(200, json={"items": [
            {"id": {"videoId": "abc"}, "snippet": {"title": "HTTP &amp; REST", "channelTitle": "Ed&#39;s", "description": "d"}},
            {"id": {"channelId": "skip-me"}, "snippet": {}},
        ]})
    return httpx.Response(200, json={"items": [{
        "id": "abc",
        "snippet": {"title": "HTTP &amp; REST", "channelTitle": "Ed's", "description": "full description"},
        "contentDetails": {"duration": "PT8M5S"},
        "statistics": {"viewCount": "1234"},
    }]})


def test_youtube_search_and_details() -> None:
    yt = YouTubeDataProvider("yt-key", llm=None, client=mock_client(_youtube_handler), retry=FAST)
    found = yt.search("http")
    assert [(v.video_id, v.title, v.channel_title) for v in found] == [("abc", "HTTP & REST", "Ed's")]
    details = yt.get_details(["abc"])[0]
    assert details.duration_seconds == 485 and details.view_count == 1234
    assert details.url == "https://www.youtube.com/watch?v=abc" and details.description == "full description"


def test_youtube_quota_exceeded_maps_to_quota_error() -> None:
    def handler(req: httpx.Request) -> httpx.Response:
        return httpx.Response(403, json={"error": {"errors": [{"reason": "quotaExceeded"}]}})

    yt = YouTubeDataProvider("yt-key", llm=None, client=mock_client(handler), retry=FAST)
    with pytest.raises(ProviderError) as info:
        yt.search("q")
    assert info.value.kind == ErrorKind.quota_exhausted and "quota" in info.value.message


class StubLLM(LLMProvider):
    """Returns `answer` for text prompts; raises `video_error` when asked to watch a video."""

    supports_video = True
    name, model = "stub", "stub-model"

    def __init__(self, answer: dict[str, Any], video_error: Exception | None = None) -> None:
        self.answer, self.video_error = answer, video_error
        self.prompts: list[tuple[str, str | None]] = []

    def complete_json(self, prompt: str, schema: type[BaseModel], system: str | None = None,
                      video_url: str | None = None) -> str:
        self.prompts.append((prompt, video_url))
        if video_url and self.video_error:
            raise self.video_error
        return json.dumps(self.answer)


VIDEO = VideoCandidate(video_id="abc", url="https://www.youtube.com/watch?v=abc", title="HTTP basics",
                       channel_title="Ed", description="All about GET", duration_seconds=480)
JUDGEMENT = {"spoken_language": "en", "relevant": True, "reason": "teaches GET", "outcomes_matched": ["Explain GET"],
             "key_points": ["GET retrieves a resource"], "suggested_segment": "01:00-04:00"}


def test_relevance_uses_gemini_video_first() -> None:
    llm = StubLLM(JUDGEMENT)
    yt = YouTubeDataProvider("k", llm=llm, transcript_fetcher=lambda vid: pytest.fail("transcript not needed"))
    verdict = yt.check_relevance(VIDEO, "HTTP", ["Explain GET"])
    assert verdict.method == "gemini_video" and verdict.key_points == ["GET retrieves a resource"]
    assert llm.prompts[0][1] == VIDEO.url


def test_relevance_rejects_non_english_narration() -> None:
    llm = StubLLM({**JUDGEMENT, "spoken_language": "hi"})
    verdict = YouTubeDataProvider("k", llm=llm).check_relevance(VIDEO, "HTTP", ["Explain GET"])
    assert verdict.relevant is False and "'hi'" in verdict.reason


def test_details_read_declared_audio_language() -> None:
    def handler(req: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"items": [{"id": "x", "snippet": {"title": "t", "defaultAudioLanguage": "hi"},
                                                     "contentDetails": {"duration": "PT5M"}}]})

    yt = YouTubeDataProvider("k", llm=None, client=mock_client(handler), retry=FAST)
    assert yt.get_details(["x"])[0].audio_language == "hi"


def test_relevance_falls_back_to_transcript() -> None:
    llm = StubLLM(JUDGEMENT, video_error=ProviderError("gemini", ErrorKind.bad_request, "video not supported"))
    yt = YouTubeDataProvider("k", llm=llm, transcript_fetcher=lambda vid: [(0.0, "Today GET requests"), (35.0, "then POST")])
    verdict = yt.check_relevance(VIDEO, "HTTP", ["Explain GET"])
    assert verdict.method == "transcript"
    assert "[00:35]" in (verdict.transcript_excerpt or "")
    assert "TRANSCRIPT" in llm.prompts[-1][0]


def test_relevance_metadata_fallback_never_claims_key_points() -> None:
    def no_transcript(vid: str) -> list:
        raise ProviderError("youtube-transcript", ErrorKind.unavailable, "disabled")

    llm = StubLLM(JUDGEMENT, video_error=ProviderError("gemini", ErrorKind.bad_request, "nope"))
    verdict = YouTubeDataProvider("k", llm=llm, transcript_fetcher=no_transcript).check_relevance(VIDEO, "HTTP", ["Explain GET"])
    assert verdict.method == "metadata" and verdict.key_points == []


def test_relevance_unverifiable_raises_unavailable() -> None:
    def no_transcript(vid: str) -> list:
        raise ProviderError("youtube-transcript", ErrorKind.unavailable, "disabled")

    yt = YouTubeDataProvider("k", llm=StubLLM(JUDGEMENT), relevance_order=["transcript"], transcript_fetcher=no_transcript)
    with pytest.raises(ProviderError) as info:
        yt.check_relevance(VIDEO, "HTTP", ["Explain GET"])
    assert info.value.kind == ErrorKind.unavailable and "transcript" in info.value.message


def test_transcript_text_marks_time_every_30s() -> None:
    text = transcript_text([(0, "a"), (10, "b"), (31, "c"), (95, "d")])
    assert text.count("[") == 3 and "[01:35] d" in text


def test_unconfigured_youtube_explains_missing_key() -> None:
    with pytest.raises(ProviderError) as info:
        UnconfiguredYouTube().search("q")
    assert "YOUTUBE_API_KEY" in info.value.message


# ---------------------------------------------------------------------------
# Books
# ---------------------------------------------------------------------------


def _google_books(req: httpx.Request) -> httpx.Response:
    return httpx.Response(200, json={"items": [{"volumeInfo": {
        "title": "HTTP: The Definitive Guide", "authors": ["David Gourley"], "publisher": "O'Reilly",
        "publishedDate": "2002-09", "description": "<p>Covers <b>HTTP</b>.</p>",
        "canonicalVolumeLink": "https://books.google.com/books/about/x",
        "industryIdentifiers": [{"type": "ISBN_10", "identifier": "1"}, {"type": "ISBN_13", "identifier": "9781565925090"}],
    }}]})


def test_google_books_parsing() -> None:
    book = GoogleBooksProvider("gb", client=mock_client(_google_books), retry=FAST).search("http")[0]
    assert (book.title, book.year, book.isbn, book.source_api) == ("HTTP: The Definitive Guide", 2002, "9781565925090", "google_books")
    assert book.description == "Covers HTTP ."


def _open_library(req: httpx.Request) -> httpx.Response:
    if req.url.path == "/search.json":
        assert "AILessonCreationTool" in req.headers["User-Agent"]
        return httpx.Response(200, json={"docs": [{"key": "/works/OL1W", "title": "Compound Interest", "author_name": ["A"],
                                                   "first_publish_year": 1999, "isbn": ["123", "9780000000000"]}]})
    return httpx.Response(200, json={"description": {"type": "/type/text", "value": "A book about interest."}})


def test_books_fall_back_to_open_library_when_google_fails() -> None:
    google = GoogleBooksProvider(None, client=mock_client(lambda r: httpx.Response(
        403, json={"error": {"errors": [{"reason": "dailyLimitExceeded"}]}})), retry=FAST)
    books = FallbackBooksProvider([google, OpenLibraryProvider(client=mock_client(_open_library), retry=FAST)])
    result = books.search("compound interest")
    assert result[0].source_api == "open_library"
    assert result[0].description == "A book about interest." and result[0].isbn == "9780000000000"
    assert result[0].url == "https://openlibrary.org/works/OL1W"


def test_books_fall_back_when_google_finds_nothing() -> None:
    google = GoogleBooksProvider(None, client=mock_client(lambda r: httpx.Response(200, json={})), retry=FAST)
    books = FallbackBooksProvider([google, OpenLibraryProvider(client=mock_client(_open_library), retry=FAST)])
    assert books.search("x")[0].source_api == "open_library"


# ---------------------------------------------------------------------------
# Gemini
# ---------------------------------------------------------------------------


def _api_error(code: int, status: str, message: str = "", details: list | None = None) -> genai_errors.APIError:
    return genai_errors.APIError(code, {"error": {"code": code, "status": status, "message": message, "details": details or []}})


@pytest.mark.parametrize(("error", "kind"), [
    (_api_error(429, "RESOURCE_EXHAUSTED", "Quota exceeded",
                [{"violations": [{"quotaId": "GenerateRequestsPerMinutePerProjectPerModel-FreeTier"}]}]), ErrorKind.rate_limited),
    (_api_error(429, "RESOURCE_EXHAUSTED", "Quota exceeded",
                [{"violations": [{"quotaId": "GenerateRequestsPerDayPerProjectPerModel-FreeTier"}]}]), ErrorKind.quota_exhausted),
    (_api_error(400, "INVALID_ARGUMENT", "API key not valid. Please pass a valid API key."), ErrorKind.auth),
    (_api_error(404, "NOT_FOUND", "models/x is not found"), ErrorKind.not_found),
    (_api_error(503, "UNAVAILABLE", "overloaded"), ErrorKind.network),
    (_api_error(400, "INVALID_ARGUMENT", "bad schema"), ErrorKind.bad_request),
])
def test_map_gemini_error(error: genai_errors.APIError, kind: ErrorKind) -> None:
    mapped = map_gemini_error(error, "gemini-x")
    assert mapped.kind == kind and mapped.provider == "gemini"


class FakeGenaiClient:
    def __init__(self, outcomes: list[Any]) -> None:
        self.outcomes = outcomes
        self.requests: list[dict[str, Any]] = []
        self.models = SimpleNamespace(generate_content=self._generate)

    def _generate(self, **kwargs: Any) -> Any:
        self.requests.append(kwargs)
        outcome = self.outcomes.pop(0)
        if isinstance(outcome, Exception):
            raise outcome
        return SimpleNamespace(text=outcome, candidates=[])


class Answer(BaseModel):
    value: int


def test_gemini_sends_schema_and_video_part() -> None:
    client = FakeGenaiClient(['{"value": 1}'])
    llm = GeminiProvider("key", "gemini-test", client=client, retry=FAST)
    assert llm.complete_json("q?", Answer, system="sys", video_url="https://www.youtube.com/watch?v=abc") == '{"value": 1}'

    req = client.requests[0]
    assert req["model"] == "gemini-test"
    assert req["config"].response_mime_type == "application/json"
    assert req["config"].response_json_schema == Answer.model_json_schema()
    assert req["config"].system_instruction == "sys"
    parts = req["contents"][0].parts
    assert parts[0].file_data.file_uri == "https://www.youtube.com/watch?v=abc" and parts[1].text == "q?"


def test_gemini_retries_429_then_gives_readable_error() -> None:
    errors = [_api_error(429, "RESOURCE_EXHAUSTED", "slow down") for _ in range(3)]
    client = FakeGenaiClient(errors)
    llm = GeminiProvider("key", "gemini-test", client=client, retry=FAST)
    with pytest.raises(ProviderError) as info:
        llm.complete_json("q", Answer)
    assert len(client.requests) == 3
    assert info.value.kind == ErrorKind.rate_limited and "429" in info.value.message and "gemini-test" in info.value.message


def test_gemini_requires_model() -> None:
    with pytest.raises(ProviderError) as info:
        GeminiProvider("key", "", client=object())
    assert "GEN_MODEL" in info.value.message


# ---------------------------------------------------------------------------
# Factory
# ---------------------------------------------------------------------------


def test_build_providers_lists_missing_settings() -> None:
    with pytest.raises(ProviderError) as info:
        build_providers(Settings(_env_file=None, demo_offline=False))  # type: ignore[call-arg]
    for name in ("GEMINI_API_KEY", "TAVILY_API_KEY", "GEN_MODEL", "QC_MODEL"):
        assert name in info.value.message


def test_build_providers_real_mode_without_youtube_key() -> None:
    settings = Settings(_env_file=None, demo_offline=False, gemini_api_key=SecretStr("g"),  # type: ignore[call-arg]
                        tavily_api_key=SecretStr("t"), gen_model="gen-m", qc_model="qc-m")
    providers = build_providers(settings)
    assert (providers.gen_llm.model, providers.qc_llm.model) == ("gen-m", "qc-m")
    assert isinstance(providers.web, TavilyProvider)
    assert isinstance(providers.youtube, UnconfiguredYouTube)
    assert isinstance(providers.books, FallbackBooksProvider)
