"""Application configuration.

All settings are environment driven so the same image can run locally,
in Docker, or on a PaaS without code changes.
"""
from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path
from typing import List

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

BACKEND_ROOT = Path(__file__).resolve().parents[2]
REPO_ROOT = BACKEND_ROOT.parent
DATA_DIR = REPO_ROOT / "data"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=(BACKEND_ROOT / ".env"),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    app_env: str = Field(default="development", alias="APP_ENV")

    # --- Corpus mode ----------------------------------------------------
    # DEMO     - answer only from the labelled synthetic corpus
    # VERIFIED - answer only from official documents (is_verified=true)
    # MIXED    - both; verified preferred in ranking, demo always labelled
    corpus_mode: str = Field(default="MIXED", alias="CORPUS_MODE")
    app_name: str = "SIH26107 BIS Standards Intelligence Platform"
    api_prefix: str = "/api"

    # --- Database -------------------------------------------------------
    # MySQL 8 is the target production database (see docker-compose.yml).
    # If it is unreachable and DB_FALLBACK_SQLITE is true the app degrades to
    # a local SQLite file so the prototype is always demonstrable.
    database_url: str = Field(
        default="mysql+pymysql://sih:sihpassword@localhost:3307/sih26107",
        alias="DATABASE_URL",
    )
    db_fallback_sqlite: bool = Field(default=True, alias="DB_FALLBACK_SQLITE")
    sqlite_path: str = Field(
        default=str(BACKEND_ROOT / "storage" / "sih26107.db"), alias="SQLITE_PATH"
    )
    sql_echo: bool = Field(default=False, alias="SQL_ECHO")

    # --- LLM ------------------------------------------------------------
    # Provider is pluggable; "auto" picks the first provider with a key,
    # otherwise falls back to the deterministic no-API engine.
    llm_provider: str = Field(default="auto", alias="LLM_PROVIDER")
    llm_api_key: str = Field(default="", alias="LLM_API_KEY")
    llm_model: str = Field(default="", alias="LLM_MODEL")
    llm_timeout_seconds: int = Field(default=60, alias="LLM_TIMEOUT_SECONDS")

    # --- Retrieval ------------------------------------------------------
    chroma_path: str = Field(
        default=str(BACKEND_ROOT / "storage" / "chroma"), alias="CHROMA_PATH"
    )
    embedding_model: str = Field(
        default="all-MiniLM-L6-v2", alias="EMBEDDING_MODEL"
    )
    embedding_backend: str = Field(default="auto", alias="EMBEDDING_BACKEND")
    vector_backend: str = Field(default="auto", alias="VECTOR_BACKEND")
    reranker_model: str = Field(default="", alias="RERANKER_MODEL")

    # Hybrid scoring weights (tunable, not scientific constants).
    weight_semantic: float = Field(default=0.60, alias="WEIGHT_SEMANTIC")
    weight_bm25: float = Field(default=0.30, alias="WEIGHT_BM25")
    weight_metadata: float = Field(default=0.10, alias="WEIGHT_METADATA")

    discovery_candidate_limit: int = Field(default=8, alias="DISCOVERY_CANDIDATE_LIMIT")
    clause_top_k: int = Field(default=8, alias="CLAUSE_TOP_K")

    # --- Web ------------------------------------------------------------
    frontend_url: str = Field(default="http://localhost:5173", alias="FRONTEND_URL")
    cors_origins: str = Field(
        default="http://localhost:5173,http://127.0.0.1:5173,http://localhost:4173",
        alias="CORS_ORIGINS",
    )

    max_upload_mb: int = Field(default=15, alias="MAX_UPLOAD_MB")
    upload_dir: str = Field(
        default=str(BACKEND_ROOT / "storage" / "uploads"), alias="UPLOAD_DIR"
    )

    # --- Optional reranker ----------------------------------------------
    enable_reranker: bool = Field(default=True, alias="ENABLE_RERANKER")

    # --- Ingestion ------------------------------------------------------
    #: Official BIS gazette documents are published bilingually, with the Hindi
    #: and English renderings of the same order emitted as separate chunks.
    #: When true, ingestion keeps only the English rendering. Set false to
    #: index both scripts.
    ingest_english_only: bool = Field(default=True, alias="INGEST_ENGLISH_ONLY")

    # --- OCR ------------------------------------------------------------
    ocr_backend: str = Field(default="auto", alias="OCR_BACKEND")
    #: Path to the tesseract executable. Empty means auto-detect common
    #: install locations (see app/services/ocr.py); set explicitly to skip
    #: that search, e.g. in a container with a known install path.
    tesseract_cmd: str = Field(default="", alias="TESSERACT_CMD")

    @property
    def cors_origin_list(self) -> List[str]:
        origins = {o.strip() for o in self.cors_origins.split(",") if o.strip()}
        origins.add(self.frontend_url.strip())
        return sorted(o for o in origins if o)

    @property
    def cors_origin_regex(self) -> str:
        """Accept any localhost / 127.0.0.1 port on top of the explicit list.

        The Vite dev server falls back to 5174, 5175, … when its default port
        is already taken, so pinning a single dev origin breaks the app the
        moment that happens. Credentials are disabled, and this only ever
        matches loopback origins, so it is safe to allow the whole local range.
        """
        return r"http://(localhost|127\.0\.0\.1)(:\d+)?"

    @property
    def sqlite_url(self) -> str:
        path = Path(self.sqlite_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        return f"sqlite:///{path.as_posix()}"

    @property
    def data_dir(self) -> Path:
        return DATA_DIR


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()

# Keep HuggingFace/tokenizers quiet and offline-friendly during ingestion.
os.environ.setdefault("TOKENIZERS_PARALLELISM", "false")
