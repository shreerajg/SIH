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
# The suite runs against a SEPARATE MongoDB database, dropped and rebuilt for
# every session, so it can never touch the development data. By default that is
# "<MONGO_DB_NAME>_test" on the cluster MONGO_URI points at; override either
# piece with TEST_MONGO_URI / TEST_MONGO_DB_NAME.
#
# This needs a reachable cluster: MongoDB has no local-file mode, so unlike the
# old SQLite default the tests are not infrastructure-free.
_test_uri = os.environ.get("TEST_MONGO_URI") or os.environ.get("MONGO_URI", "")
if _test_uri:
    os.environ["MONGO_URI"] = _test_uri
_default_db = os.environ.get("MONGO_DB_NAME", "sih26107")
os.environ["MONGO_DB_NAME"] = os.environ.get("TEST_MONGO_DB_NAME", f"{_default_db}_test")
os.environ["EMBEDDING_BACKEND"] = "hashing"
os.environ["LLM_PROVIDER"] = "none"
os.environ["LLM_API_KEY"] = ""
for _key in ("OPENAI_API_KEY", "ANTHROPIC_API_KEY", "GEMINI_API_KEY", "GOOGLE_API_KEY"):
    os.environ.pop(_key, None)

from app.core.config import REPO_ROOT, settings  # noqa: E402
from app.db.indexes import drop_all, ensure_indexes  # noqa: E402
from app.db.mongo import init_client, session_scope  # noqa: E402
from app.ingestion.pipeline import ingest_documents  # noqa: E402
from app.ingestion.seed import seed_all  # noqa: E402
from app.llm.base import LLMProvider, LLMResult  # noqa: E402
from app.llm.service import LLMService  # noqa: E402
from app.search.vector_store import get_vector_store  # noqa: E402


@pytest.fixture(scope="session", autouse=True)
def _corpus():
    """Build a real (small) corpus once for the whole test session."""
    # Guard against ever pointing the suite at the development database: this
    # fixture drops every collection before it starts.
    if not settings.mongo_db_name.endswith("_test"):
        raise RuntimeError(
            f"Refusing to run tests against database '{settings.mongo_db_name}'. "
            "The test database name must end with '_test'."
        )

    db = init_client()
    # A shared test database may carry documents from a previous run. The
    # vectors live in their own collections, which drop_all() deliberately
    # leaves alone, so they are reset separately - exactly as
    # scripts/setup_demo.py --reset does.
    drop_all(db)
    get_vector_store().reset()
    ensure_indexes(db)
    # Deliberately the demo corpus only. Several suites depend on this being
    # demo-only - corpus-mode starvation, the "every demo record is flagged
    # mock" check - so ingesting verified documents here would weaken them.
    # Hallmarking tests therefore skip unless HALLMARKING_TEST_CORPUS=1 asks
    # for the fetched BIS hallmarking pack to be ingested as well.
    ingest_documents(db, REPO_ROOT / "data" / "raw" / "standards")
    if os.environ.get("HALLMARKING_TEST_CORPUS") == "1":
        hallmarking_dir = REPO_ROOT / "data" / "raw" / "hallmarking"
        if hallmarking_dir.exists() and any(hallmarking_dir.iterdir()):
            ingest_documents(db, hallmarking_dir)
    seed_all(db)
    yield
    drop_all(db)
    get_vector_store().reset()
    shutil.rmtree(_TMP, ignore_errors=True)


@pytest.fixture()
def db():
    # PyMongo pools connections on the client, so every test shares one handle;
    # there is no per-test session to open, roll back or close.
    yield session_scope()


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
