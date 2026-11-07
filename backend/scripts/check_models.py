"""Make one tiny call ("say ok") per Gemini model id and report which ones work.

Usage (from backend/):  .venv/Scripts/python scripts/check_models.py gemini-3.8-flash gemini-3.6-flash ...
Each model gets exactly one request (no retries).
"""

import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from pydantic import BaseModel  # noqa: E402

from app.config import get_settings  # noqa: E402
from app.providers.errors import ProviderError, RetryPolicy  # noqa: E402
from app.providers.llm import GeminiProvider  # noqa: E402


class Ok(BaseModel):
    reply: str


def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[attr-defined]
    key = get_settings().gemini_api_key
    if not key:
        print("GEMINI_API_KEY is not set")
        return 2
    working = []
    for model in sys.argv[1:]:
        llm = GeminiProvider(key.get_secret_value(), model, timeout_s=60, retry=RetryPolicy(1, 0, 0))
        started = time.monotonic()
        try:
            raw = llm.complete_json('Say ok. Return {"reply": "ok"}.', Ok)
            print(f"OK     {model:28} {time.monotonic() - started:5.1f}s  response: {raw.strip()[:60]}")
            working.append(model)
        except ProviderError as err:
            print(f"FAILED {model:28} {time.monotonic() - started:5.1f}s  {err.kind.value}: {err.message}")
    print("working:", ",".join(working) or "none")
    return 0 if working else 1


if __name__ == "__main__":
    raise SystemExit(main())
