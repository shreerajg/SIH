"""SQLAlchemy engine / session factory.

Target database is MySQL 8 (see docker-compose.yml). When MySQL is not
reachable and ``DB_FALLBACK_SQLITE`` is enabled the engine transparently falls
back to a local SQLite file so the prototype remains demonstrable on any
machine. The active backend is reported by ``/api/health``.
"""
from __future__ import annotations

import logging
from typing import Iterator, Optional

from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from app.core.config import settings

logger = logging.getLogger(__name__)


class Base(DeclarativeBase):
    pass


_engine: Optional[Engine] = None
_SessionLocal: Optional[sessionmaker] = None
_active_url: str = ""
_active_backend: str = "uninitialised"


def _build_engine(url: str) -> Engine:
    kwargs = {"echo": settings.sql_echo, "future": True, "pool_pre_ping": True}
    if url.startswith("sqlite"):
        kwargs["connect_args"] = {"check_same_thread": False}
        kwargs.pop("pool_pre_ping")
    return create_engine(url, **kwargs)


def _probe(engine: Engine) -> None:
    with engine.connect() as conn:
        conn.execute(text("SELECT 1"))


def init_engine(force: bool = False) -> Engine:
    """Create (once) the process-wide engine, applying the SQLite fallback."""
    global _engine, _SessionLocal, _active_url, _active_backend
    if _engine is not None and not force:
        return _engine

    candidates = [settings.database_url]
    if settings.db_fallback_sqlite and not settings.database_url.startswith("sqlite"):
        candidates.append(settings.sqlite_url)

    last_error: Optional[Exception] = None
    for url in candidates:
        try:
            engine = _build_engine(url)
            _probe(engine)
        except Exception as exc:  # pragma: no cover - depends on local infra
            last_error = exc
            logger.warning("Database unavailable at %s (%s)", _safe(url), exc.__class__.__name__)
            continue
        _engine = engine
        _SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)
        _active_url = url
        _active_backend = engine.dialect.name
        if url != settings.database_url:
            logger.warning(
                "Falling back to SQLite at %s because the configured database was unreachable.",
                _safe(url),
            )
        return engine

    raise RuntimeError(f"No usable database backend. Last error: {last_error}")


def _safe(url: str) -> str:
    """Strip credentials before logging a connection URL."""
    if "@" in url and "//" in url:
        head, tail = url.split("//", 1)
        if "@" in tail:
            return f"{head}//***@{tail.split('@', 1)[1]}"
    return url


def get_session_factory() -> sessionmaker:
    if _SessionLocal is None:
        init_engine()
    assert _SessionLocal is not None
    return _SessionLocal


def get_db() -> Iterator[Session]:
    """FastAPI dependency yielding a request-scoped session."""
    session = get_session_factory()()
    try:
        yield session
    finally:
        session.close()


def session_scope() -> Session:
    """Standalone session for scripts and services."""
    return get_session_factory()()


def active_backend() -> str:
    if _engine is None:
        return "uninitialised"
    return _active_backend


def active_url_safe() -> str:
    return _safe(_active_url)


def create_all() -> None:
    from app import models  # noqa: F401  (registers mappers)

    engine = init_engine()
    Base.metadata.create_all(bind=engine)


def drop_all() -> None:
    from app import models  # noqa: F401

    engine = init_engine()
    Base.metadata.drop_all(bind=engine)
