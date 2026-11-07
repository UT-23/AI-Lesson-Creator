"""Books provider interface + Google Books → Open Library fallback.

Books contribute metadata + publisher descriptions only. The tool never
claims to have read a book's full text.
"""

import logging
import re
from abc import ABC, abstractmethod
from typing import Literal

import httpx
from pydantic import BaseModel

from app.providers.errors import ErrorKind, ProviderError, RetryPolicy, request_json

log = logging.getLogger(__name__)


class BookResult(BaseModel):
    title: str
    authors: list[str] = []
    year: int | None = None
    publisher: str | None = None
    description: str | None = None
    url: str | None = None
    isbn: str | None = None
    source_api: Literal["google_books", "open_library", "fake"]


class BooksProvider(ABC):
    name: str = "books"

    @abstractmethod
    def search(self, query: str, max_results: int = 5) -> list[BookResult]: ...


_TAG_RE = re.compile(r"<[^>]+>")
_YEAR_RE = re.compile(r"\b(1[5-9]\d\d|20\d\d)\b")


def _clean(text: str | None) -> str | None:
    if not text:
        return None
    return re.sub(r"\s+", " ", _TAG_RE.sub(" ", text)).strip() or None


def _year(value: str | int | None) -> int | None:
    if isinstance(value, int):
        return value
    match = _YEAR_RE.search(value or "")
    return int(match.group(1)) if match else None


# ---------------------------------------------------------------------------
# Google Books
# ---------------------------------------------------------------------------


def classify_google_error(resp: httpx.Response) -> tuple[ErrorKind, str] | None:
    try:
        reason = resp.json()["error"]["errors"][0]["reason"]
    except (ValueError, KeyError, IndexError, TypeError):
        reason = ""
    if reason in ("dailyLimitExceeded", "quotaExceeded", "rateLimitExceeded", "userRateLimitExceeded"):
        return ErrorKind.quota_exhausted, f"Google Books quota exceeded ({reason})."
    if reason in ("keyInvalid", "keyExpired"):
        return ErrorKind.auth, "Google Books rejected the API key. Check GOOGLE_BOOKS_API_KEY."
    return None


class GoogleBooksProvider(BooksProvider):
    name = "google_books"
    URL = "https://www.googleapis.com/books/v1/volumes"

    def __init__(self, api_key: str | None, *, timeout_s: float = 30.0, retry: RetryPolicy = RetryPolicy(),
                 client: httpx.Client | None = None) -> None:
        self._key = api_key  # optional: Google Books works keyless with a lower quota
        self._client = client or httpx.Client(timeout=timeout_s)
        self._retry = retry

    def search(self, query: str, max_results: int = 5) -> list[BookResult]:
        params: dict[str, str | int] = {
            "q": query, "maxResults": min(max_results, 40), "printType": "books",
            "orderBy": "relevance", "langRestrict": "en",
        }
        if self._key:
            params["key"] = self._key
        data = request_json(self._client, "GET", self.URL, provider="google_books", retry=self._retry,
                            classify=classify_google_error, params=params)
        books = []
        for item in data.get("items", []):
            info = item.get("volumeInfo", {})
            if not info.get("title"):
                continue
            title = info["title"] + (f": {info['subtitle']}" if info.get("subtitle") else "")
            isbn = next((i["identifier"] for i in info.get("industryIdentifiers", []) if i.get("type") == "ISBN_13"), None)
            books.append(BookResult(
                title=title,
                authors=info.get("authors", []),
                year=_year(info.get("publishedDate")),
                publisher=info.get("publisher"),
                description=_clean(info.get("description")),
                url=info.get("canonicalVolumeLink") or info.get("infoLink"),
                isbn=isbn,
                source_api="google_books",
            ))
        return books


# ---------------------------------------------------------------------------
# Open Library
# ---------------------------------------------------------------------------


class OpenLibraryProvider(BooksProvider):
    name = "open_library"
    BASE = "https://openlibrary.org"
    # Open Library asks API clients to identify themselves.
    HEADERS = {"User-Agent": "AILessonCreationTool/0.1 (local educational research tool)"}

    def __init__(self, *, timeout_s: float = 30.0, retry: RetryPolicy = RetryPolicy(),
                 client: httpx.Client | None = None) -> None:
        self._client = client or httpx.Client(timeout=timeout_s)
        self._retry = retry

    def _get(self, path: str, params: dict | None = None) -> dict:
        return request_json(self._client, "GET", f"{self.BASE}{path}", provider="open_library", retry=self._retry,
                            headers=self.HEADERS, params=params or {})

    def _description(self, work_key: str) -> str | None:
        try:
            work = self._get(f"{work_key}.json")
        except ProviderError as exc:
            log.info("open library: no work record for %s (%s)", work_key, exc.message)
            return None
        desc = work.get("description")
        if isinstance(desc, dict):
            desc = desc.get("value")
        return _clean(desc) if isinstance(desc, str) else None

    def search(self, query: str, max_results: int = 5) -> list[BookResult]:
        data = self._get("/search.json", {
            "q": query, "limit": max_results, "lang": "en",
            "fields": "key,title,subtitle,author_name,first_publish_year,publisher,isbn",
        })
        books = []
        for doc in data.get("docs", [])[:max_results]:
            if not doc.get("title") or not doc.get("key"):
                continue
            title = doc["title"] + (f": {doc['subtitle']}" if doc.get("subtitle") else "")
            books.append(BookResult(
                title=title,
                authors=doc.get("author_name", [])[:5],
                year=doc.get("first_publish_year"),
                publisher=(doc.get("publisher") or [None])[0],
                description=self._description(doc["key"]),
                url=f"{self.BASE}{doc['key']}",
                isbn=next((i for i in doc.get("isbn", []) if len(i) == 13), None),
                source_api="open_library",
            ))
        return books


# ---------------------------------------------------------------------------
# Fallback chain
# ---------------------------------------------------------------------------


class FallbackBooksProvider(BooksProvider):
    """Try each provider in order; move on when one fails or finds nothing."""

    name = "books"

    def __init__(self, providers: list[BooksProvider]) -> None:
        self._providers = providers

    def search(self, query: str, max_results: int = 5) -> list[BookResult]:
        last_error: ProviderError | None = None
        for provider in self._providers:
            try:
                results = provider.search(query, max_results)
            except ProviderError as exc:
                log.warning("books: %s failed (%s), trying next provider", provider.name, exc.message)
                last_error = exc
                continue
            if results:
                return results
            log.info("books: %s found nothing for %r, trying next provider", provider.name, query)
        if last_error:
            raise last_error
        return []
