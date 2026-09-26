"""MongoDB client and database handle.

The connection URI is read from the environment (``MONGO_URI``) and is never
hard-coded. Atlas connection strings normally carry no database name in their
path, so the database is named separately by ``MONGO_DB_NAME``.

There is deliberately **no local fallback**. The previous SQL layer degraded to
a local SQLite file when MySQL was unreachable, which meant a network problem
could silently change which corpus answered a question. A standards platform
must not do that: if MongoDB cannot be reached the API reports 503 and says so.
"""
from __future__ import annotations

import logging
import re
from typing import Optional

from pymongo import MongoClient
from pymongo.database import Database
from pymongo.errors import PyMongoError

from app.core.config import settings

logger = logging.getLogger(__name__)

_client: Optional[MongoClient] = None
_database: Optional[Database] = None
_active_backend: str = "uninitialised"


class DatabaseNotConfigured(RuntimeError):
    """MONGO_URI is missing - the application cannot run without it."""


def safe_uri(uri: str = "") -> str:
    """Strip credentials from a connection URI before logging or returning it.

    ``mongodb+srv://user:password@host/db`` -> ``mongodb+srv://***@host/db``
    """
    uri = uri or settings.mongo_uri
    if not uri:
        return ""
    return re.sub(r"//[^@/]+@", "//***@", uri)


def _build_client(uri: str) -> MongoClient:
    return MongoClient(
        uri,
        serverSelectionTimeoutMS=settings.mongo_timeout_ms,
        connectTimeoutMS=settings.mongo_timeout_ms,
        # Surface a dead connection as an error rather than an empty result.
        retryWrites=True,
        tz_aware=False,
    )


def init_client(force: bool = False) -> Database:
    """Create (once) the process-wide client and verify it is reachable."""
    global _client, _database, _active_backend
    if _database is not None and not force:
        return _database

    if not settings.mongo_uri:
        raise DatabaseNotConfigured(
            "MONGO_URI is not set. Add it to backend/.env (the file is git-ignored) "
            "before starting the API."
        )

    client = _build_client(settings.mongo_uri)
    # Fail here, at startup, rather than on the first query.
    client.admin.command("ping")

    _client = client
    _database = client[settings.mongo_db_name]
    _active_backend = "mongodb"
    logger.info(
        "Connected to MongoDB at %s (database: %s)", safe_uri(), settings.mongo_db_name
    )
    return _database


def get_database() -> Database:
    """The process-wide database handle."""
    if _database is None:
        return init_client()
    return _database


def get_db():
    """FastAPI dependency yielding the database handle.

    PyMongo's client is thread-safe and pools connections internally, so unlike
    a SQLAlchemy session there is nothing per-request to open or close.
    """
    yield get_database()


def session_scope() -> Database:
    """Standalone handle for scripts and services (name kept for callers)."""
    return get_database()


def active_backend() -> str:
    return _active_backend


def active_url_safe() -> str:
    return safe_uri()


def ping() -> bool:
    """True when the server answers. Used by /api/health."""
    try:
        get_database().client.admin.command("ping")
        return True
    except (PyMongoError, DatabaseNotConfigured):
        return False


def close_client() -> None:
    global _client, _database, _active_backend
    if _client is not None:
        _client.close()
    _client = None
    _database = None
    _active_backend = "uninitialised"
