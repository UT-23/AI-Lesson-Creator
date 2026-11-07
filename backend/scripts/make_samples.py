"""Run both test lessons end to end THROUGH THE HTTP API and save the export bundles to /samples.

Usage (backend must be running on :8000):
    .venv/Scripts/python scripts/make_samples.py            # both lessons
    .venv/Scripts/python scripts/make_samples.py http       # just one
Prints every step status change while it waits.
"""

import io
import sys
import time
import zipfile
from pathlib import Path

import httpx

API = "http://localhost:8000"
REPO = Path(__file__).resolve().parents[2]
LESSONS = {
    "http": ("HTTP Requests and Responses",
             "Explain GET and POST methods and distinguish between 2xx, 4xx, and 5xx response status categories."),
    "interest": ("Simple vs Compound Interest",
                 "Calculate simple and compound interest for a given principal, rate, and time, and explain why "
                 "compound interest grows faster."),
}


def run_one(name: str) -> bool:
    title, objective = LESSONS[name]
    lesson = httpx.post(f"{API}/lessons", json={"title": title, "objective": objective}, timeout=30).json()
    lesson_id = lesson["id"]
    print(f"[{name}] lesson {lesson_id} created", flush=True)
    print(f"[{name}] run -> {httpx.post(f'{API}/lessons/{lesson_id}/run', timeout=30).json()['message']}", flush=True)
    seen: dict[str, tuple] = {}
    started = time.monotonic()
    while True:
        steps = httpx.get(f"{API}/lessons/{lesson_id}/steps", timeout=30).json()
        for s in steps:
            state = (s["status"], s["attempt"])
            if seen.get(s["name"]) != state:
                seen[s["name"]] = state
                err = f"  error: {s['error']}" if s["error"] else ""
                print(f"[{name}] {time.strftime('%H:%M:%S')} {s['name']:17} -> {s['status']}{err}", flush=True)
        status = httpx.get(f"{API}/lessons/{lesson_id}", timeout=30).json()["lesson"]["status"]
        if status != "running":
            break
        if time.monotonic() - started > 1800:
            print(f"[{name}] gave up waiting after 30 min", flush=True)
            return False
        time.sleep(2)
    print(f"[{name}] lesson status: {status}", flush=True)
    resp = httpx.get(f"{API}/lessons/{lesson_id}/export", timeout=60)
    if resp.status_code != 200:
        print(f"[{name}] export failed: {resp.status_code} {resp.text}", flush=True)
        return False
    out = REPO / "samples" / name
    out.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(io.BytesIO(resp.content)) as zf:
        zf.extractall(out)
        print(f"[{name}] saved to {out}: {', '.join(zf.namelist())}", flush=True)
    (out / "lesson_id.txt").write_text(f"{lesson_id}\n", encoding="utf-8")
    return status in ("completed", "completed_with_warnings")


if __name__ == "__main__":
    names = sys.argv[1:] or list(LESSONS)
    ok = [run_one(n) for n in names]
    raise SystemExit(0 if all(ok) else 1)
