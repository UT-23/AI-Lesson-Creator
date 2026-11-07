"""Groq (OpenAI-compatible chat completions) as the last-resort LLM behind the Gemini chain.

JSON mode via response_format={"type": "json_object"}; the target JSON schema is
put in the system message. No video input. On a 413 / token-limit error the
prompt is trimmed once (keeping its head, where the best evidence is ordered
first, and its closing instructions) and retried; no loops.
"""

import json
import logging

import httpx
from pydantic import BaseModel

from app.providers.errors import ErrorKind, ProviderError, RetryPolicy, request_json
from app.providers.llm import LLMProvider

log = logging.getLogger(__name__)
GROQ_URL = "https://api.groq.com/openai/v1/chat/completions"
TRIM_TO_CHARS = 24000  # ~6k tokens: fits small free-tier per-request limits


def classify_groq_error(resp: httpx.Response) -> tuple[ErrorKind, str] | None:
    text = resp.text[:300]
    if resp.status_code == 413 or "context_length" in text or "too large" in text.lower():
        return ErrorKind.too_large, f"Groq request too large ({resp.status_code}): {text}"
    if resp.status_code == 429:
        return ErrorKind.rate_limited, f"Groq rate limit hit (429): {text}"
    if resp.status_code == 401:
        return ErrorKind.auth, "Groq rejected the API key (401). Check GROQ_API_KEY."
    return None


def trim_prompt(prompt: str, limit: int = TRIM_TO_CHARS) -> str:
    if len(prompt) <= limit:
        return prompt
    head, tail = int(limit * 0.7), int(limit * 0.3)
    return prompt[:head] + "\n\n[… lower-ranked evidence trimmed to fit the model's limit …]\n\n" + prompt[-tail:]


class GroqProvider(LLMProvider):
    supports_video = False

    def __init__(self, api_key: str, model: str, *, timeout_s: float = 120.0, temperature: float = 0.2,
                 client: httpx.Client | None = None) -> None:
        if not api_key or not model:
            raise ProviderError("groq", ErrorKind.not_configured, "Set GROQ_API_KEY and GROQ_MODEL to use Groq.")
        self.name = "groq"
        self.model = model
        self.temperature = temperature
        self._headers = {"Authorization": f"Bearer {api_key}"}
        self._client = client or httpx.Client(timeout=timeout_s)

    def _call(self, prompt: str, schema: type[BaseModel], system: str | None) -> str:
        instructions = (f"{system or ''}\nReturn ONLY a JSON object matching this JSON schema:\n"
                        f"{json.dumps(schema.model_json_schema(), separators=(',', ':'))}").strip()
        data = request_json(self._client, "POST", GROQ_URL, provider="groq", retry=RetryPolicy(1, 0, 0),
                            classify=classify_groq_error, headers=self._headers, json={
                                "model": self.model, "temperature": self.temperature,
                                "response_format": {"type": "json_object"},
                                "messages": [{"role": "system", "content": instructions},
                                             {"role": "user", "content": prompt}]})
        try:
            return data["choices"][0]["message"]["content"] or ""
        except (KeyError, IndexError, TypeError) as exc:
            raise ProviderError("groq", ErrorKind.bad_response, "Unexpected Groq response shape.") from exc

    def complete_json(self, prompt: str, schema: type[BaseModel], system: str | None = None,
                      video_url: str | None = None) -> str:
        try:
            return self._call(prompt, schema, system)
        except ProviderError as err:
            if err.kind != ErrorKind.too_large:
                raise
            log.warning("Groq: prompt too large (%d chars) — trimming evidence and retrying once", len(prompt))
            return self._call(trim_prompt(prompt), schema, system)
