"""Web search provider interface + Tavily implementation (search + extract).

Tavily credits: basic search = 1 credit; basic extract = 1 credit per 5 successful URLs.
"""

import logging
from abc import ABC, abstractmethod

import httpx
from pydantic import BaseModel

from app.providers.errors import ErrorKind, ProviderError, RetryPolicy, request_json

log = logging.getLogger(__name__)


class WebSearchResult(BaseModel):
    query: str
    url: str
    title: str
    snippet: str = ""
    score: float | None = None  # provider relevance score, if any
    published_date: str | None = None


class WebPage(BaseModel):
    url: str
    title: str = ""
    content: str  # extracted full text


class WebSearchProvider(ABC):
    name: str = "web"

    @abstractmethod
    def search(self, query: str, max_results: int = 5) -> list[WebSearchResult]: ...

    @abstractmethod
    def extract(self, urls: list[str]) -> list[WebPage]:
        """Fetch full text for URLs. URLs that fail to extract are simply omitted."""


# ---------------------------------------------------------------------------
# Tavily
# ---------------------------------------------------------------------------

TAVILY_URL = "https://api.tavily.com"
EXTRACT_BATCH = 20  # Tavily's per-request maximum


def classify_tavily_error(resp: httpx.Response) -> tuple[ErrorKind, str] | None:
    if resp.status_code == 401:
        return ErrorKind.auth, "Tavily rejected the API key (HTTP 401). Check TAVILY_API_KEY."
    if resp.status_code in (432, 433):
        return ErrorKind.quota_exhausted, f"Tavily credit/plan limit reached (HTTP {resp.status_code}). Add credits or wait for the monthly reset."
    if resp.status_code == 429:
        return ErrorKind.rate_limited, "Tavily rate limit hit (HTTP 429)."
    return None


class TavilyProvider(WebSearchProvider):
    name = "tavily"

    def __init__(
        self,
        api_key: str,
        *,
        exclude_domains: list[str] | None = None,
        timeout_s: float = 30.0,
        retry: RetryPolicy = RetryPolicy(),
        client: httpx.Client | None = None,
    ) -> None:
        if not api_key:
            raise ProviderError("tavily", ErrorKind.not_configured, "TAVILY_API_KEY is not set.")
        self._client = client or httpx.Client(timeout=timeout_s)
        self._headers = {"Authorization": f"Bearer {api_key}"}
        self._exclude = exclude_domains or []
        self._retry = retry

    def _post(self, path: str, body: dict) -> dict:
        return request_json(self._client, "POST", f"{TAVILY_URL}{path}", provider="tavily", retry=self._retry,
                            classify=classify_tavily_error, headers=self._headers, json=body)

    def search(self, query: str, max_results: int = 5) -> list[WebSearchResult]:
        body = {
            "query": query,
            "search_depth": "basic",  # 1 credit; set explicitly so auto_parameters can't upgrade it
            "topic": "general",
            "max_results": max_results,
            "include_answer": False,  # we never use Tavily's own LLM answer as evidence
            "include_raw_content": False,
        }
        if self._exclude:
            body["exclude_domains"] = self._exclude
        data = self._post("/search", body)
        results = []
        for item in data.get("results", []):
            if not item.get("url"):
                continue
            results.append(WebSearchResult(
                query=query,
                url=item["url"],
                title=item.get("title") or item["url"],
                snippet=item.get("content") or "",
                score=item.get("score"),
                published_date=item.get("published_date"),
            ))
        return results

    def extract(self, urls: list[str]) -> list[WebPage]:
        pages: list[WebPage] = []
        for start in range(0, len(urls), EXTRACT_BATCH):
            batch = urls[start:start + EXTRACT_BATCH]
            data = self._post("/extract", {"urls": batch, "extract_depth": "basic", "format": "markdown"})
            for failed in data.get("failed_results", []):
                log.warning("tavily extract failed for %s: %s", failed.get("url"), failed.get("error"))
            for item in data.get("results", []):
                content = (item.get("raw_content") or "").strip()
                if item.get("url") and content:
                    pages.append(WebPage(url=item["url"], content=content))
        return pages
