"""LLM provider interface, the Gemini implementation, and schema-validated output.

`generate_structured` is the only way pipeline code talks to an LLM:
it asks for JSON matching a Pydantic schema, validates it, and on failure
re-prompts with the validation error (at most `max_repairs` times) before
raising `LLMOutputError`.
"""

import json
import logging
import re
from abc import ABC, abstractmethod
from collections.abc import Callable
from typing import Any, TypeVar

import httpx
from pydantic import BaseModel, ValidationError

from app.providers.errors import ErrorKind, ProviderError, RetryPolicy

log = logging.getLogger(__name__)

T = TypeVar("T", bound=BaseModel)


class LLMOutputError(Exception):
    """The model kept returning output that did not match the schema."""


class LLMProvider(ABC):
    name: str = "llm"
    model: str = ""
    supports_video: bool = False  # can it watch a YouTube URL?

    @abstractmethod
    def complete_json(
        self, prompt: str, schema: type[BaseModel], system: str | None = None, video_url: str | None = None
    ) -> str:
        """Return raw text that should be JSON matching `schema`.

        Implementations should use the API's native JSON mode / response schema
        where available, and raise `ProviderError` for transport/quota failures.
        `video_url` is only passed when `supports_video` is True.
        """


# ---------------------------------------------------------------------------
# Gemini
# ---------------------------------------------------------------------------


def map_gemini_error(exc: Any, model: str) -> ProviderError:
    """google.genai.errors.APIError → ProviderError with a readable message."""
    code = getattr(exc, "code", 0) or 0
    status = getattr(exc, "status", "") or ""
    message = (getattr(exc, "message", "") or "").strip()
    details = str(getattr(exc, "details", ""))

    if code == 429 or status == "RESOURCE_EXHAUSTED":
        if "PerDay" in details or "per day" in message.lower():
            return ProviderError("gemini", ErrorKind.quota_exhausted,
                                 f"Daily Gemini quota for model '{model}' is used up (429 RESOURCE_EXHAUSTED). "
                                 "Wait for the quota to reset, or point GEN_MODEL / QC_MODEL at another model.")
        return ProviderError("gemini", ErrorKind.rate_limited,
                             f"Gemini rate limit hit for model '{model}' (429 RESOURCE_EXHAUSTED), still failing after "
                             "retries with backoff. Free-tier limits are per minute — retry this step shortly.")
    if code in (401, 403) or status in ("UNAUTHENTICATED", "PERMISSION_DENIED") or "API key not valid" in message:
        return ProviderError("gemini", ErrorKind.auth, f"Gemini rejected the API key ({code} {status}). Check GEMINI_API_KEY.")
    if code == 404:
        return ProviderError("gemini", ErrorKind.not_found,
                             f"Gemini model '{model}' was not found (404). Check GEN_MODEL / QC_MODEL against the current model list.")
    if code >= 500:
        return ProviderError("gemini", ErrorKind.network, f"Gemini service error ({code} {status}) — usually temporary.")
    return ProviderError("gemini", ErrorKind.bad_request, f"Gemini rejected the request ({code} {status}): {message[:300]}")


class GeminiProvider(LLMProvider):
    supports_video = True

    def __init__(
        self,
        api_key: str,
        model: str,
        *,
        timeout_s: float = 180.0,
        temperature: float = 0.2,
        retry: RetryPolicy = RetryPolicy(),
        client: Any = None,  # injectable for tests
    ) -> None:
        if not model:
            raise ProviderError("gemini", ErrorKind.not_configured, "No Gemini model configured (set GEN_MODEL / QC_MODEL).")
        self.name = "gemini"
        self.model = model
        self.temperature = temperature
        self._retry = retry
        if client is None:
            from google import genai
            from google.genai import types

            client = genai.Client(api_key=api_key, http_options=types.HttpOptions(timeout=int(timeout_s * 1000)))
        self._client = client

    def complete_json(
        self, prompt: str, schema: type[BaseModel], system: str | None = None, video_url: str | None = None
    ) -> str:
        from google.genai import errors, types

        parts = []
        if video_url:
            parts.append(types.Part(file_data=types.FileData(file_uri=video_url)))
        parts.append(types.Part(text=prompt))
        config = types.GenerateContentConfig(
            system_instruction=system,
            response_mime_type="application/json",
            response_json_schema=schema.model_json_schema(),
            temperature=self.temperature,
            # Low resolution keeps a 10-minute video to a manageable token count.
            media_resolution=types.MediaResolution.MEDIA_RESOLUTION_LOW if video_url else None,
        )

        def attempt() -> str:
            try:
                response = self._client.models.generate_content(
                    model=self.model, contents=[types.Content(role="user", parts=parts)], config=config
                )
            except errors.APIError as exc:
                raise map_gemini_error(exc, self.model) from exc
            except httpx.TimeoutException as exc:
                raise ProviderError("gemini", ErrorKind.timeout, f"Gemini request timed out (model '{self.model}').") from exc
            except httpx.TransportError as exc:
                raise ProviderError("gemini", ErrorKind.network, f"Network error talking to Gemini: {type(exc).__name__}") from exc
            text = response.text or ""
            if not text:
                reason = getattr((response.candidates or [None])[0], "finish_reason", None)
                log.warning("Gemini returned no text (finish_reason=%s)", reason)
            return text

        return self._retry.call(attempt)


REPAIR_TEMPLATE = """

---
YOUR PREVIOUS RESPONSE WAS REJECTED.
Problems found:
{errors}

Previous response (truncated):
{previous}

Return the complete corrected JSON object only, matching the schema exactly."""

_FENCE_RE = re.compile(r"^\s*```(?:json)?\s*(.*?)\s*```\s*$", re.DOTALL)


def _strip_fences(raw: str) -> str:
    match = _FENCE_RE.match(raw)
    return match.group(1) if match else raw.strip()


def _format_validation_error(err: ValidationError) -> str:
    lines = []
    for e in err.errors()[:15]:
        loc = ".".join(str(p) for p in e["loc"]) or "(root)"
        lines.append(f"- {loc}: {e['msg']}")
    return "\n".join(lines)


def generate_structured(
    llm: LLMProvider,
    prompt: str,
    schema: type[T],
    *,
    system: str | None = None,
    max_repairs: int = 2,
    check: Callable[[T], list[str]] | None = None,
    soft_check: Callable[[T], list[str]] | None = None,
    max_soft_repairs: int = 1,
    video_url: str | None = None,
) -> T:
    """Call the LLM and return a validated `schema` instance.

    `check` runs semantic checks Pydantic can't express (e.g. "every citation
    must be a known source id"); any problems it returns are fed back to the
    model exactly like schema errors, and the call fails if they persist.

    `soft_check` problems (e.g. "the lesson runs 52 minutes") are also fed back,
    but if they persist the best output that passed the hard checks is returned
    anyway — the caller re-runs `soft_check` to record them as warnings. Soft
    problems get at most `max_soft_repairs` extra calls (each is a full, paid
    generation; free-tier daily quotas are small).
    """
    current_prompt = prompt
    problems = ""
    acceptable: T | None = None  # latest output that passed schema + hard checks
    soft_rounds = 0
    for attempt in range(1, max_repairs + 2):
        try:
            if video_url:
                raw = llm.complete_json(current_prompt, schema, system, video_url=video_url)
            else:
                raw = llm.complete_json(current_prompt, schema, system)
        except ProviderError as err:
            if acceptable is not None:
                # A repair call failed, but we already hold a draft that passed every hard check:
                # keep it (the caller records the remaining soft problems as warnings).
                log.warning("%s repair call failed (%s); keeping the valid draft", schema.__name__, err)
                return acceptable
            raise
        try:
            parsed = schema.model_validate_json(_strip_fences(raw))
            issues = check(parsed) if check else []
            if not issues:
                acceptable = parsed
                issues = soft_check(parsed) if soft_check else []
                if not issues or soft_rounds >= max_soft_repairs:
                    return parsed
                soft_rounds += 1
            problems = "\n".join(f"- {i}" for i in issues)
        except ValidationError as err:
            problems = _format_validation_error(err)

        log.warning(
            "%s output invalid (attempt %d/%d):\n%s", schema.__name__, attempt, max_repairs + 1, problems
        )
        current_prompt = prompt + REPAIR_TEMPLATE.format(errors=problems, previous=raw[:3000])

    if acceptable is not None:
        return acceptable  # only soft problems remain
    first_problem = problems.splitlines()[0] if problems else "unknown problem"
    raise LLMOutputError(
        f"The model ({llm.model or llm.name}) returned invalid {schema.__name__} output "
        f"{max_repairs + 1} times in a row. First problem: {first_problem.lstrip('- ')}"
    )


# ---------------------------------------------------------------------------
# Model fallback chain
# ---------------------------------------------------------------------------

# Failures that are about this model/moment, not about our request: try the next model.
FALLBACK_KINDS = {ErrorKind.rate_limited, ErrorKind.quota_exhausted, ErrorKind.network,
                  ErrorKind.timeout, ErrorKind.not_found, ErrorKind.too_large}


class FallbackLLM(LLMProvider):
    """Try each model in order; on 429/503/504/timeout/quota move to the next one immediately.

    `last_model` records which model actually produced the latest output, so it
    can be stored with the lesson version / QC report.
    """

    def __init__(self, providers: list[LLMProvider]) -> None:
        if not providers:
            raise ProviderError("gemini", ErrorKind.not_configured, "No Gemini models configured.")
        self.providers = providers
        self.name = providers[0].name
        self.model = providers[0].model  # the preferred model (used in cache namespaces)
        self.supports_video = any(p.supports_video for p in providers)
        self.last_model: str | None = None

    @property
    def models(self) -> list[str]:
        return [p.model for p in self.providers]

    def preferring_not(self, model: str | None) -> "FallbackLLM":
        """Same chain, with `model` moved to the end (e.g. QC prefers a model other than the generator)."""
        if not model:
            return self
        same = {model, model.split(":", 1)[-1]}  # accepts "provider:model" or a bare model id
        ordered = [p for p in self.providers if p.model not in same] + [p for p in self.providers if p.model in same]
        return FallbackLLM(ordered)

    def complete_json(
        self, prompt: str, schema: type[BaseModel], system: str | None = None, video_url: str | None = None
    ) -> str:
        failures: list[str] = []
        last: ProviderError | None = None
        for provider in self.providers:
            if video_url and not provider.supports_video:
                continue
            try:
                if video_url:
                    text = provider.complete_json(prompt, schema, system, video_url=video_url)
                else:
                    text = provider.complete_json(prompt, schema, system)
            except ProviderError as err:
                if err.kind not in FALLBACK_KINDS:
                    raise
                log.warning("model %s failed (%s) — trying the next model", provider.model, err.message)
                failures.append(f"{provider.model}: {err.message}")
                last = err
                continue
            self.last_model = f"{provider.name}:{provider.model}"  # e.g. "gemini:gemini-3.5-flash-lite"
            return text
        raise ProviderError("gemini", last.kind if last else ErrorKind.not_configured,
                            "Every model in the fallback chain failed — " + " | ".join(failures))


def schema_json(schema: type[BaseModel]) -> str:
    """Compact JSON schema string, handy for embedding in prompts."""
    return json.dumps(schema.model_json_schema(), separators=(",", ":"))
