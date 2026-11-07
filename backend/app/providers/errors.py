"""Provider error type, the shared tenacity retry policy, and an HTTP helper.

Every real provider converts its SDK/HTTP failures into a `ProviderError`
with a `kind`, so the pipeline can show one readable message per failure
("Gemini rate limit hit (429)...") instead of raw stack traces.
"""

import logging
from collections.abc import Callable
from dataclasses import dataclass
from enum import Enum
from typing import Any, ParamSpec, TypeVar

import httpx
from tenacity import (
    Retrying,
    before_sleep_log,
    retry,
    retry_if_exception,
    stop_after_attempt,
    wait_exponential,
)

log = logging.getLogger(__name__)

P = ParamSpec("P")
R = TypeVar("R")


class ErrorKind(str, Enum):
    rate_limited = "rate_limited"  # HTTP 429 / RESOURCE_EXHAUSTED (per-minute limits)
    quota_exhausted = "quota_exhausted"  # daily/monthly quota gone: retrying now won't help
    timeout = "timeout"
    network = "network"  # connection problems and 5xx from the provider
    auth = "auth"  # bad / missing API key
    not_configured = "not_configured"
    bad_request = "bad_request"  # we sent something the API rejected
    bad_response = "bad_response"  # unexpected payload from the API
    not_found = "not_found"
    unavailable = "unavailable"  # e.g. no transcript for this video
    too_large = "too_large"  # request exceeds the model's token limit (e.g. Groq 413)


RETRYABLE_KINDS = {ErrorKind.rate_limited, ErrorKind.timeout, ErrorKind.network}


class ProviderError(Exception):
    def __init__(self, provider: str, kind: ErrorKind, message: str) -> None:
        self.provider = provider
        self.kind = kind
        self.message = message
        super().__init__(f"{provider}: {message}")

    @property
    def retryable(self) -> bool:
        return self.kind in RETRYABLE_KINDS


def _is_retryable(exc: BaseException) -> bool:
    return isinstance(exc, ProviderError) and exc.retryable


@dataclass(frozen=True)
class RetryPolicy:
    max_attempts: int = 4
    min_wait: float = 2.0
    max_wait: float = 30.0

    def call(self, fn: Callable[[], R]) -> R:
        """Run `fn`, retrying transient ProviderErrors with exponential backoff."""
        retrying = Retrying(
            retry=retry_if_exception(_is_retryable),
            stop=stop_after_attempt(self.max_attempts),
            wait=wait_exponential(multiplier=self.min_wait, min=self.min_wait, max=self.max_wait),
            before_sleep=before_sleep_log(log, logging.WARNING),
            reraise=True,
        )
        return retrying(fn)


NO_RETRY = RetryPolicy(max_attempts=1, min_wait=0, max_wait=0)


def with_retries(max_attempts: int = 4, min_wait: float = 2.0, max_wait: float = 30.0) -> Callable[[Callable[P, R]], Callable[P, R]]:
    """Decorator form of the same policy."""
    return retry(
        retry=retry_if_exception(_is_retryable),
        stop=stop_after_attempt(max_attempts),
        wait=wait_exponential(multiplier=min_wait, min=min_wait, max=max_wait),
        before_sleep=before_sleep_log(log, logging.WARNING),
        reraise=True,
    )


# ---------------------------------------------------------------------------
# HTTP
# ---------------------------------------------------------------------------

# Optional hook: inspect an error response and return (kind, message) to override the default mapping.
ErrorClassifier = Callable[[httpx.Response], tuple[ErrorKind, str] | None]


def default_http_error(provider: str, resp: httpx.Response) -> ProviderError:
    code = resp.status_code
    snippet = resp.text[:300].strip()
    if code == 429:
        return ProviderError(provider, ErrorKind.rate_limited, f"Rate limit hit (HTTP 429). {snippet}")
    if code in (401, 403):
        return ProviderError(provider, ErrorKind.auth, f"Request was not authorised (HTTP {code}) — check the API key. {snippet}")
    if code == 404:
        return ProviderError(provider, ErrorKind.not_found, f"Not found (HTTP 404). {snippet}")
    if code >= 500:
        return ProviderError(provider, ErrorKind.network, f"Service error (HTTP {code}). {snippet}")
    return ProviderError(provider, ErrorKind.bad_request, f"Request rejected (HTTP {code}). {snippet}")


def request_json(
    client: httpx.Client,
    method: str,
    url: str,
    *,
    provider: str,
    retry: RetryPolicy = RetryPolicy(),
    classify: ErrorClassifier | None = None,
    **kwargs: Any,
) -> Any:
    """One HTTP call → parsed JSON, with typed errors and retries for transient failures."""

    def attempt() -> Any:
        try:
            resp = client.request(method, url, **kwargs)
        except httpx.TimeoutException as exc:
            raise ProviderError(provider, ErrorKind.timeout, f"Request timed out ({type(exc).__name__}).") from exc
        except httpx.TransportError as exc:
            raise ProviderError(provider, ErrorKind.network, f"Network error: {type(exc).__name__}: {exc}") from exc
        if resp.status_code >= 400:
            override = classify(resp) if classify else None
            if override:
                raise ProviderError(provider, override[0], override[1])
            raise default_http_error(provider, resp)
        try:
            return resp.json()
        except ValueError as exc:
            raise ProviderError(provider, ErrorKind.bad_response, "Response was not valid JSON.") from exc

    return retry.call(attempt)
