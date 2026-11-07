"""SQLite engine + session helpers.

The engine is created lazily so tests can point it at a temporary database
with `init_engine(url)` before anything touches the DB.
"""

from collections.abc import Iterator
from pathlib import Path

from sqlalchemy import Engine, event
from sqlmodel import Session, SQLModel, create_engine

from app.config import get_settings

_engine: Engine | None = None


def init_engine(url: str | None = None) -> Engine:
    """(Re)create the global engine and make sure all tables exist."""
    global _engine
    url = url or get_settings().database_url
    if url.startswith("sqlite:///"):
        Path(url.removeprefix("sqlite:///")).parent.mkdir(parents=True, exist_ok=True)

    # check_same_thread=False: the pipeline runs in a background thread.
    # timeout: wait up to 30 s for another connection's write lock instead of failing.
    _engine = create_engine(url, connect_args={"check_same_thread": False, "timeout": 30})

    @event.listens_for(_engine, "connect")
    def _sqlite_pragmas(dbapi_conn, _record) -> None:  # type: ignore[no-untyped-def]
        cur = dbapi_conn.cursor()
        cur.execute("PRAGMA foreign_keys=ON")
        cur.execute("PRAGMA journal_mode=WAL")  # API reads while the pipeline writes
        cur.close()

    import app.models  # noqa: F401  (register tables on SQLModel.metadata)

    SQLModel.metadata.create_all(_engine)
    return _engine


def get_engine() -> Engine:
    return _engine if _engine is not None else init_engine()


def get_session() -> Iterator[Session]:
    """FastAPI dependency: one session per request."""
    with Session(get_engine()) as session:
        yield session
