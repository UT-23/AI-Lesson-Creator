"""Smoke tests for the deadline reliability fixes: keep a valid draft when a repair call fails; model fallback."""

import json

from pydantic import BaseModel

from app.providers.errors import ErrorKind, ProviderError
from app.providers.fakes import FakeLLM
from app.providers.llm import FallbackLLM, generate_structured


class Small(BaseModel):
    n: int


class FlakyAfterFirst(FakeLLM):
    """Answers once, then every later call fails like Gemini's 503."""

    def complete_json(self, prompt, schema, system=None, video_url=None):  # type: ignore[no-untyped-def]
        if self.calls:
            self.calls.append((schema.__name__, prompt))
            raise ProviderError("gemini", ErrorKind.network, "Gemini service error (503 UNAVAILABLE)")
        return super().complete_json(prompt, schema, system)


def test_failed_soft_repair_keeps_valid_draft() -> None:
    llm = FlakyAfterFirst()
    llm.queue("Small", json.dumps({"n": 1}))
    result = generate_structured(llm, "p", Small, soft_check=lambda s: ["too short"])
    assert result.n == 1 and len(llm.calls) == 2  # first draft kept although the repair call failed


def test_fallback_moves_to_next_model_and_records_it() -> None:
    first, second = FakeLLM(model="m-first"), FakeLLM(model="m-second")
    first.fail_with = ProviderError("gemini", ErrorKind.network, "503 UNAVAILABLE")
    second.queue("Small", json.dumps({"n": 7}))
    chain = FallbackLLM([first, second])
    assert generate_structured(chain, "p", Small).n == 7
    assert chain.last_model == "m-second" and len(first.calls) == 1
    assert chain.preferring_not("m-second").models == ["m-first", "m-second"]
    assert chain.preferring_not("m-first").models == ["m-second", "m-first"]
