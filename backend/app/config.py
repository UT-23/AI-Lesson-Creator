"""Settings loaded from environment variables and `.env`.

Secrets are stored as `SecretStr` so they never show up in logs or reprs.
"""

from functools import lru_cache
from pathlib import Path

from pydantic import SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict

BACKEND_DIR = Path(__file__).resolve().parent.parent
REPO_ROOT = BACKEND_DIR.parent


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        # Repo-root .env first, backend/.env may override it.
        env_file=(REPO_ROOT / ".env", BACKEND_DIR / ".env"),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # --- API keys -------------------------------------------------------
    gemini_api_key: SecretStr | None = None
    tavily_api_key: SecretStr | None = None
    youtube_api_key: SecretStr | None = None
    google_books_api_key: SecretStr | None = None

    # --- Models (no hardcoded defaults: must come from the environment) --
    gen_model: str = ""
    qc_model: str = ""

    # --- Modes ----------------------------------------------------------
    # DEMO_OFFLINE=1 swaps every provider for the fakes in providers/fakes.py.
    demo_offline: bool = False

    # --- Storage --------------------------------------------------------
    database_url: str = f"sqlite:///{(BACKEND_DIR / 'data' / 'lessons.db').as_posix()}"
    reports_dir: str = str(BACKEND_DIR / "data" / "reports")  # QC .md/.json files per lesson

    # --- Lesson / time budget --------------------------------------------
    lesson_minutes_budget: int = 45
    reading_wpm: int = 200

    # --- Research limits -------------------------------------------------
    web_results_per_query: int = 3
    web_max_extract: int = 8
    web_max_per_host: int = 2  # diversity: at most this many extracted pages per site
    web_min_page_chars: int = 400  # extracted pages shorter than this are not evidence
    web_excerpt_chars: int = 12000  # longer pages are reduced to their most relevant passages
    web_exclude_domains: list[str] = [
        "youtube.com", "pinterest.com", "facebook.com", "instagram.com", "tiktok.com", "quora.com", "x.com",
    ]
    youtube_max_searches: int = 1  # each search.list costs 100 quota units
    youtube_max_candidates: int = 8
    youtube_keep_max: int = 4
    youtube_min_seconds: int = 120  # skip Shorts / trailers
    youtube_preferred_max_minutes: int = 15
    youtube_max_relevance_checks: int = 6  # bounds Gemini video tokens per lesson
    # Order of relevance-check methods. "video" = Gemini watches the YouTube URL.
    youtube_relevance_order: list[str] = ["video", "transcript", "metadata"]
    books_candidates: int = 10
    books_max: int = 5

    # --- Provider behaviour --------------------------------------------------
    http_timeout_s: float = 30.0
    gemini_timeout_s: float = 120.0
    # Comma-separated Gemini model ids tried in order after GEN_MODEL / QC_MODEL on 429/503/504/timeouts.
    llm_fallback_models: str = ""
    # Last resort after every Gemini model failed (OpenAI-compatible Groq API).
    groq_api_key: SecretStr | None = None
    groq_model: str = ""
    gemini_temperature: float = 0.2
    retry_max_attempts: int = 4
    retry_min_wait_s: float = 2.0
    retry_max_wait_s: float = 30.0
    cache_enabled: bool = True
    llm_domain_tiering: bool = True  # ask QC_MODEL to tier domains the rules don't know

    # --- Prompt budget ----------------------------------------------------
    excerpt_chars_for_prompt: int = 3000
    # Per-source characters in the generation prompt: more room for more trustworthy sources.
    prompt_chars_by_tier: dict[int, int] = {1: 6000, 2: 5000, 3: 3500, 4: 2000}
    excerpt_chars_stored: int = 20000

    # --- LLM output repair ------------------------------------------------
    llm_max_repairs: int = 2

    cors_origins: list[str] = ["http://localhost:5173", "http://127.0.0.1:5173"]

    def fallback_models(self) -> list[str]:
        return [m.strip() for m in self.llm_fallback_models.split(",") if m.strip()]

    def secret_values(self) -> list[str]:
        """All configured secret values, used to scrub error messages."""
        secrets = [self.gemini_api_key, self.tavily_api_key, self.youtube_api_key, self.google_books_api_key]
        return [s.get_secret_value() for s in secrets if s and s.get_secret_value()]


@lru_cache
def get_settings() -> Settings:
    return Settings()
