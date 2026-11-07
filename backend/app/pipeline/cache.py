"""Response cache for external calls (Tavily, YouTube, Books, Gemini judgements).

Cache writes use their OWN session and commit immediately. That matters because
a failing step rolls back its session: if three Tavily searches succeed and the
fourth fails, the first three are still cached, so the retry costs one search.

Callers must not hold uncommitted writes in the step session while calling this
(SQLite allows one writer at a time).
"""

import hashlib
import json
import logging
from collections.abc import Callable
from typing import Any, TypeVar

from pydantic import TypeAdapter
from sqlalchemy.exc import IntegrityError
from sqlmodel import Session, select

from app.db import get_engine
from app.models import ProviderCache

log = logging.getLogger(__name__)

T = TypeVar("T")


def cache_key(params: dict[str, Any]) -> str:
    return hashlib.sha256(json.dumps(params, sort_keys=True, default=str).encode()).hexdigest()


def cached_call(
    namespace: str,
    params: dict[str, Any],
    call: Callable[[], T],
    response_type: Any,
    *,
    enabled: bool = True,
) -> T:
    """Return the cached response for (namespace, params), or run `call()` and cache it.

    `response_type` is the Python type of the result (e.g. `list[WebSearchResult]`),
    used to serialise to JSON and rebuild on a hit.
    """
    if not enabled:
        return call()

    adapter: TypeAdapter[T] = TypeAdapter(response_type)
    key = cache_key(params)
    with Session(get_engine()) as session:
        row = session.exec(
            select(ProviderCache).where(ProviderCache.namespace == namespace, ProviderCache.key == key)
        ).first()
        if row is not None:
            log.info("cache hit: %s %s", namespace, _short(params))
            return adapter.validate_python(row.response_json)

    result = call()  # raises on failure → nothing is cached

    with Session(get_engine()) as session:
        session.add(ProviderCache(namespace=namespace, key=key, params_json=params,
                                  response_json=adapter.dump_python(result, mode="json")))
        try:
            session.commit()
        except IntegrityError:  # another thread cached it first
            session.rollback()
    return result


def cached_batch(
    namespace: str,
    items: list[str],
    fetch: Callable[[list[str]], dict[str, T]],
    response_type: Any,
    *,
    enabled: bool = True,
) -> dict[str, T]:
    """Per-item caching for batch APIs (e.g. Tavily extract of many URLs in one call).

    Only cache misses are passed to `fetch`, in a single call. Items `fetch`
    doesn't return (failed extractions) are not cached and are simply absent.
    """
    if not enabled:
        return fetch(items)

    adapter: TypeAdapter[T] = TypeAdapter(response_type)
    found: dict[str, T] = {}
    with Session(get_engine()) as session:
        for item in items:
            row = session.exec(
                select(ProviderCache).where(ProviderCache.namespace == namespace,
                                            ProviderCache.key == cache_key({"item": item}))
            ).first()
            if row is not None:
                found[item] = adapter.validate_python(row.response_json)
    misses = [i for i in items if i not in found]
    if found:
        log.info("cache hit: %s for %d of %d items", namespace, len(found), len(items))
    if not misses:
        return found

    fetched = fetch(misses)
    with Session(get_engine()) as session:
        for item, value in fetched.items():
            session.add(ProviderCache(namespace=namespace, key=cache_key({"item": item}), params_json={"item": item},
                                      response_json=adapter.dump_python(value, mode="json")))
        try:
            session.commit()
        except IntegrityError:
            session.rollback()
    return {**found, **fetched}


def _short(params: dict[str, Any]) -> str:
    text = json.dumps(params, default=str)
    return text if len(text) <= 120 else text[:117] + "..."
