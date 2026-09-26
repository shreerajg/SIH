"""Test fixtures.

Environment is configured BEFORE any app module is imported so the settings
singleton picks up the test database, a throwaway vector store and the
dependency-light embedding backend (tests must not download a model).
"""
from __future__ import annotations

import os
import shutil
import tempfile
from pathlib import Path

import pytest

_TMP = Path(tempfile.mkdtemp(prefix="sih26107-tests-"))

os.environ["APP_ENV"] = "test"
# Defaults to a throwaway SQLite file so `pytest` needs no infrastructure.
# Set TEST_DATABASE_URL to run the identical suite against the real target
# database, e.g.
#   TEST_DATABASE_URL=mysql+pymysql://sih:sihpassword@localhost:3307/sih26107_test pytest
os.environ["DATABASE_URL"] = os.environ.get(
    "TEST_DATABASE_URL", f"sqlite:///{(_TMP / 'test.db').as_posix()}"
)
os.environ["DB_FALLBACK_SQLITE"] = "false"  # never mask a broken test database
os.environ["CHROMA_PATH"] = str(_TMP / "chroma")
os.environ["EMBEDDING_BACKEND"] = "hashing"
os.environ["VECTOR_BACKEND"] = "numpy"
os.environ["LLM_PROVIDER"] = "none"
os.environ["LLM_API_KEY"] = ""
for _key in ("OPENAI_API_KEY", "ANTHROPIC_API_KEY", "GEMINI_API_KEY", "GOOGLE_API_KEY"):
    os.environ.pop(_key, None)

from app.core.config import REPO_ROOT  # noqa: E402
from app.db.base import create_all, session_scope  # noqa: E402
from app.ingestion.pipeline import ingest_documents  # noqa: E402
from app.ingestion.seed import seed_all  # noqa: E402
from app.llm.base import LLMProvider, LLMResult  # noqa: E402
from app.llm.service import LLMService  # noqa: E402
from app.search.vector_store import get_vector_store  # noqa: E402


@pytest.fixture(scope="session", autouse=True)
def _corpus():
    """Build a real (small) corpus once for the whole test session."""
    from app.db.base import drop_all

    if os.environ.get("TEST_DATABASE_URL"):
        # A shared test database may carry rows from a previous run.
        drop_all()
    create_all()
    db = session_scope()
    try:
        ingest_documents(db, REPO_ROOT / "data" / "raw" / "standards")
        seed_all(db)
    finally:
        db.close()
    yield
    shutil.rmtree(_TMP, ignore_errors=True)


@pytest.fixture()
def db():
    session = session_scope()
    try:
        yield session
    finally:
        session.rollback()
        session.close()


@pytest.fixture()
def client():
    from fastapi.testclient import TestClient

    from app.main import app

    with TestClient(app) as test_client:
        yield test_client


# ---------------------------------------------------------------------------
# Scripted LLM used to prove the guardrails, including hostile output.
# ---------------------------------------------------------------------------

class ScriptedProvider(LLMProvider):
    """A provider that returns whatever the test tells it to."""

    name = "scripted"

    def __init__(self, payload: str) -> None:
        super().__init__(api_key="test-key", model="scripted-1", timeout=1)
        self.payload = payload
        self.calls = 0

    @property
    def available(self) -> bool:
        return True

    def generate(self, system, messages, *, json_mode=False, temperature=0.1, max_tokens=1600):
        del system, messages, json_mode, temperature, max_tokens
        self.calls += 1
        return LLMResult(text=self.payload, provider=self.name, model=self.model)


@pytest.fixture()
def scripted_llm():
    def _make(payload: str) -> LLMService:
        return LLMService(provider=ScriptedProvider(payload))

    return _make


@pytest.fixture()
def vector_store():
    return get_vector_store()
