"""Research steps with fake providers: caching, extraction choice, cleaning, tiering, book vetting."""

from fastapi.testclient import TestClient
from sqlmodel import Session, select

from app.models import ProviderCache, Source
from app.pipeline.passages import select_passages, strip_chrome, topic_keywords
from app.pipeline.research import (
    DUPLICATE_THRESHOLD,
    clean_page_text,
    keyword_filter,
    select_for_extraction,
    similarity,
)
from app.pipeline.sources import self_declared_outdated
from app.providers import Providers
from app.providers.books import BookResult
from app.providers.errors import ErrorKind, ProviderError
from app.providers.web import WebSearchResult
from tests.conftest import create_lesson, step_map


def test_retry_reuses_cached_searches(client: TestClient, providers: Providers, session: Session) -> None:
    web = providers.web
    real_extract = web.extract
    web.extract = lambda urls: (_ for _ in ()).throw(  # type: ignore[method-assign]
        ProviderError("tavily", ErrorKind.auth, "bad key"))
    lesson_id = create_lesson(client)
    client.post(f"/lessons/{lesson_id}/run")
    assert step_map(client, lesson_id)["research_web"]["status"] == "failed"
    searches_before = [c for c in web.calls if c[0] == "search"]  # type: ignore[attr-defined]
    assert len(searches_before) == 4

    web.extract = real_extract  # type: ignore[method-assign]
    client.post(f"/lessons/{lesson_id}/steps/research_web/retry")
    assert step_map(client, lesson_id)["research_web"]["status"] == "done"
    assert [c for c in web.calls if c[0] == "search"] == searches_before  # no new paid searches  # type: ignore[attr-defined]
    namespaces = {row.namespace for row in session.exec(select(ProviderCache)).all()}
    assert {"fake-web.search", "fake-web.extract", "fake-youtube.search", "fake-youtube.relevance"} <= namespaces


def test_second_lesson_on_same_topic_hits_cache(client: TestClient, providers: Providers) -> None:
    client.post(f"/lessons/{create_lesson(client)}/run")
    calls_after_first = len(providers.web.calls)  # type: ignore[attr-defined]
    youtube_after_first = len(providers.youtube.calls)  # type: ignore[attr-defined]
    client.post(f"/lessons/{create_lesson(client)}/run")
    assert len(providers.web.calls) == calls_after_first  # type: ignore[attr-defined]
    assert len(providers.youtube.calls) == youtube_after_first  # type: ignore[attr-defined]


def test_select_for_extraction_prefers_reliable_and_caps_per_host() -> None:
    def r(url: str) -> WebSearchResult:
        return WebSearchResult(query="q", url=url, title=url)

    results = [r("https://blog.example/a"), r("https://blog.example/b"), r("https://blog.example/c"),
               r("https://developer.mozilla.org/x"), r("https://en.wikipedia.org/wiki/HTTP")]
    picked = [p.url for p in select_for_extraction(results, limit=4, max_per_host=2)]
    assert picked == ["https://developer.mozilla.org/x", "https://en.wikipedia.org/wiki/HTTP",
                      "https://blog.example/a", "https://blog.example/b"]


def test_clean_page_text_drops_navigation_and_images() -> None:
    page = (
        "[Home](/) | [Docs](/docs) | [Blog](/blog)\n"
        "![logo](/logo.png)\n"
        "# HTTP methods\n\n\n\n"
        "The [GET](https://x.org/get) method requests a representation.\n"
        "- [Related article](/r)\n"
    )
    assert clean_page_text(page) == "# HTTP methods\n\nThe GET method requests a representation."


def test_clean_page_text_keeps_definition_terms() -> None:
    page = "[`200 OK`](/docs/200)\n:   The request succeeded.\n* [Menu item](/m)"
    assert clean_page_text(page) == "`200 OK`\n:   The request succeeded."


def test_strip_chrome_removes_menu_before_title_only() -> None:
    assert strip_chrome("HTML\n\nCSS\n\nToggle sidebar\n\n# POST method\n\nPOST sends data.") == "# POST method\n\nPOST sends data."
    real = ("This page has a long real introduction before its title, with well over twenty words in it, "
            "so it is content rather than a menu.\n\n# T\n\nx")
    assert strip_chrome(real) == real


def test_select_passages_prefers_specific_sections_with_headings() -> None:
    filler = "The request and response messages carry many header fields that a server and client may use. " * 3
    doc = "\n\n".join([
        "# HTTP Semantics",
        "HTTP is a stateless application-level request and response protocol for distributed systems.",
        *[f"## 3.{i}. Caches\n\n{filler}" for i in range(30)],
        "### 9.3.1. GET",
        "The GET method requests transfer of a current selected representation for the target resource.",
        *[f"## 4.{i}. Fields\n\n{filler}" for i in range(30)],
        "### 15.6. Server Error 5xx",
        "The 5xx (Server Error) class of status code indicates that the server is aware that it has erred.",
    ])
    keywords = topic_keywords(["Explain the GET method", "Distinguish 2xx, 4xx and 5xx status categories",
                               "HTTP request response server client"])
    excerpt, method = select_passages(doc, keywords, budget=900)
    assert method == "passages" and len(excerpt) <= 900
    assert "HTTP is a stateless" in excerpt  # the page's own summary
    assert "### 9.3.1. GET\n\nThe GET method requests" in excerpt  # definition with its heading
    assert "The 5xx (Server Error) class" in excerpt
    assert "[…]" in excerpt  # skipped text is marked


def test_select_passages_handles_text_without_blank_lines() -> None:
    """PDF extractions are often one giant 'paragraph'; that must not produce an empty excerpt."""
    pdf = " ".join(["Compound interest is earned on the principal and on interest already added."] * 400)
    excerpt, method = select_passages(pdf, {"compound", "interest", "principal"}, budget=3000)
    assert method == "passages" and 1000 < len(excerpt) <= 3000


def test_select_passages_skips_off_topic_opening() -> None:
    page = "\n\n".join([
        "Our site uses cookies to improve your experience. By continuing, you agree to our privacy policy.",
        *["Unrelated marketing copy about our award-winning platform and mobile apps for everyone." for _ in range(80)],
        "Compound interest is calculated on the principal and on all interest added in earlier periods.",
    ])
    excerpt, _ = select_passages(page, {"compound", "interest", "principal"}, budget=500)
    assert "cookies" not in excerpt and excerpt.startswith("Compound interest is calculated")


def test_select_passages_truncates_when_nothing_matches() -> None:
    page = "\n\n".join(["Totally unrelated sentence about gardening and soil and weather today." for _ in range(50)])
    excerpt, method = select_passages(page, {"compound"}, budget=300)
    assert method == "truncated" and excerpt == page[:300]


def test_book_ratings_threshold_and_order(client: TestClient, providers: Providers) -> None:
    import json as _json

    providers.qc_llm.queue("BookSelection", _json.dumps({"ratings": [  # type: ignore[attr-defined]
        {"id": 0, "score": 6, "reason": "tangential"},
        {"id": 1, "score": 9, "reason": "dedicated textbook"},
    ]}))
    lesson_id = create_lesson(client)
    client.post(f"/lessons/{lesson_id}/run")
    books = step_map(client, lesson_id)["research_books"]["output_json"]
    assert [b["title"] for b in books["books"]] == ["[FAKE] Practical HTTP Requests and Responses"]
    assert books["reasons"]["[FAKE] HTTP Requests and Responses: A Textbook"].startswith("6/10")


def test_select_passages_keeps_short_pages_whole() -> None:
    assert select_passages("# T\n\nShort page.", {"page"}, budget=1000) == ("# T\n\nShort page.", "whole")


def test_similarity_flags_duplicates_only() -> None:
    text = "The GET method requests transfer of a current selected representation for the target resource. " * 3
    assert similarity(text, text + " Extra trailing sentence here.") >= DUPLICATE_THRESHOLD
    assert similarity(text, "Compound interest is interest calculated on the principal and accumulated interest.") == 0


def test_self_declared_outdated() -> None:
    assert self_declared_outdated("1992 This is a historic document and is not accurate anymore.") == "historic document"
    assert self_declared_outdated("This document updates RFC 3864 and obsoletes RFCs 2818, 7231.") is None


def test_non_english_videos_are_dropped(client: TestClient, providers: Providers) -> None:
    original = providers.youtube.get_details

    def details_in_hindi(ids: list[str]):  # type: ignore[no-untyped-def]
        return [v.model_copy(update={"audio_language": "hi"}) if v.video_id == "fakevid001" else v for v in original(ids)]

    providers.youtube.get_details = details_in_hindi  # type: ignore[method-assign]
    lesson_id = create_lesson(client)
    client.post(f"/lessons/{lesson_id}/run")
    out = step_map(client, lesson_id)["research_youtube"]["output_json"]
    assert [v["video_id"] for v in out["kept"]] == ["fakevid002"]
    assert any(d["video_id"] == "fakevid001" and "not English" in d["reason"] for d in out["dropped"])


def test_topic_keywords_drop_filler_and_ids() -> None:
    kw = topic_keywords(["Explain GET and POST methods; RFC 9110 MDN examples; 2xx 4xx 5xx categories in 2026"])
    assert {"get", "post", "2xx", "4xx", "5xx", "methods", "categories"} <= kw
    assert not {"explain", "rfc", "mdn", "9110", "2026", "examples", "and"} & kw
    assert topic_keywords(["compound interest site:edu OR site:gov"]) == {"compound", "interest"}


def test_unknown_domains_get_llm_tier_with_reason(client: TestClient, session: Session) -> None:
    lesson_id = create_lesson(client)
    client.post(f"/lessons/{lesson_id}/run")
    web_sources = session.exec(select(Source).where(Source.lesson_id == lesson_id, Source.type == "web")).all()
    assert web_sources and all(s.reliability_reason.startswith("LLM-assessed by fake-qc-model") for s in web_sources)
    assessed = step_map(client, lesson_id)["score_sources"]["output_json"]["llm_assessed"]
    assert set(assessed) == {"example.com", "YouTube channel: [FAKE] Channel"}


def test_llm_tiering_failure_keeps_tier_4_and_does_not_fail(client: TestClient, providers: Providers, session: Session) -> None:
    providers.qc_llm.queue("DomainTiers", "{", "{", "{")  # type: ignore[attr-defined]
    lesson_id = create_lesson(client)
    client.post(f"/lessons/{lesson_id}/run")
    assert step_map(client, lesson_id)["score_sources"]["status"] == "done"
    web_sources = session.exec(select(Source).where(Source.type == "web")).all()
    assert all(s.reliability_tier == 4 and "Unknown site" in s.reliability_reason for s in web_sources)


def test_book_vetting_falls_back_to_keywords(client: TestClient, providers: Providers) -> None:
    providers.qc_llm.queue("BookSelection", "{", "{", "{")  # type: ignore[attr-defined]
    lesson_id = create_lesson(client)
    client.post(f"/lessons/{lesson_id}/run")
    books = step_map(client, lesson_id)["research_books"]["output_json"]
    assert books["selection_method"] == "keywords" and len(books["books"]) == 2


def test_keyword_filter() -> None:
    books = [BookResult(title="Compound Interest Explained", source_api="fake"),
             BookResult(title="Gardening for Beginners", description="plants", source_api="fake")]
    assert [b.title for b in keyword_filter(books, "Simple vs Compound Interest")] == ["Compound Interest Explained"]


def test_videos_outside_duration_window_are_dropped(client: TestClient) -> None:
    lesson_id = create_lesson(client)
    client.post(f"/lessons/{lesson_id}/run")
    out = step_map(client, lesson_id)["research_youtube"]["output_json"]
    assert [v["video_id"] for v in out["kept"]] == ["fakevid001", "fakevid002"]
    assert any(d["video_id"] == "fakevid003" and "longer than 15 min" in d["reason"] for d in out["dropped"])
