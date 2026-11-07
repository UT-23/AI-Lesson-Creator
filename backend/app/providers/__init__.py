"""Provider bundle: every external dependency the pipeline uses, in one object.

Pipeline steps receive a `Providers` instance instead of importing SDKs, so
tests (and DEMO_OFFLINE=1) can swap in fakes.
"""

from dataclasses import dataclass

from app.config import Settings
from app.providers.books import BooksProvider
from app.providers.errors import ErrorKind, ProviderError, RetryPolicy
from app.providers.llm import LLMProvider
from app.providers.web import WebSearchProvider
from app.providers.youtube import YouTubeProvider


@dataclass
class Providers:
    gen_llm: LLMProvider  # GEN_MODEL — writes plans and lessons
    qc_llm: LLMProvider  # QC_MODEL — judges (QC layers, video relevance, book/domain vetting)
    web: WebSearchProvider
    youtube: YouTubeProvider
    books: BooksProvider


def _secret(value) -> str:  # type: ignore[no-untyped-def]
    return value.get_secret_value() if value else ""


def build_providers(settings: Settings) -> Providers:
    if settings.demo_offline:
        from app.providers.fakes import make_fake_providers

        return make_fake_providers()

    required = {
        "GEMINI_API_KEY": _secret(settings.gemini_api_key),
        "TAVILY_API_KEY": _secret(settings.tavily_api_key),
        "GEN_MODEL": settings.gen_model,
        "QC_MODEL": settings.qc_model,
    }
    missing = [name for name, value in required.items() if not value]
    if missing:
        raise ProviderError(
            "config", ErrorKind.not_configured,
            f"Missing settings in .env: {', '.join(missing)}. See .env.example "
            "(or set DEMO_OFFLINE=1 to run with fake providers).",
        )

    from app.providers.books import FallbackBooksProvider, GoogleBooksProvider, OpenLibraryProvider
    from app.providers.llm import FallbackLLM, GeminiProvider
    from app.providers.web import TavilyProvider
    from app.providers.youtube import UnconfiguredYouTube, YouTubeDataProvider

    retry = RetryPolicy(settings.retry_max_attempts, settings.retry_min_wait_s, settings.retry_max_wait_s)
    gemini_key = _secret(settings.gemini_api_key)
    # With a fallback chain, a failing model hands over to the next one immediately (no backoff loop).
    llm_retry = RetryPolicy(max_attempts=1, min_wait=0, max_wait=0) if settings.fallback_models() else retry

    def gemini(model: str) -> GeminiProvider:
        return GeminiProvider(gemini_key, model, timeout_s=settings.gemini_timeout_s,
                              temperature=settings.gemini_temperature, retry=llm_retry)

    def chain(first: str) -> FallbackLLM:
        models = list(dict.fromkeys([first, *settings.fallback_models()]))  # preferred first, no duplicates
        return FallbackLLM([gemini(m) for m in models])

    qc_llm = chain(settings.qc_model)
    youtube_key = _secret(settings.youtube_api_key)
    youtube: YouTubeProvider = (
        YouTubeDataProvider(youtube_key, llm=qc_llm, relevance_order=settings.youtube_relevance_order,
                            timeout_s=settings.http_timeout_s, retry=retry)
        if youtube_key else UnconfiguredYouTube()
    )
    return Providers(
        gen_llm=chain(settings.gen_model),
        qc_llm=qc_llm,
        web=TavilyProvider(_secret(settings.tavily_api_key), exclude_domains=settings.web_exclude_domains,
                           timeout_s=settings.http_timeout_s, retry=retry),
        youtube=youtube,
        books=FallbackBooksProvider([
            GoogleBooksProvider(_secret(settings.google_books_api_key) or None,
                                timeout_s=settings.http_timeout_s, retry=retry),
            OpenLibraryProvider(timeout_s=settings.http_timeout_s, retry=retry),
        ]),
    )
