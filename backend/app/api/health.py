"""Health and corpus introspection."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict

from fastapi import APIRouter, Depends
from pymongo.database import Database

from app.core.config import settings
from app.core.constants import DISCLAIMER
from app.db.mongo import active_backend, active_url_safe
from app.db.repositories import amendments as amendments_repo
from app.db.repositories import clauses as clauses_repo
from app.db.repositories import qcos as qcos_repo
from app.db.repositories import relationships as relationships_repo
from app.db.repositories import requirements as requirements_repo
from app.db.repositories import standards as standards_repo
from app.llm.service import get_llm
from app.api.deps import db_session
from app.models import (
    QCO,
    Amendment,
    ComplianceRequirement,
    Standard,
    StandardClause,
    StandardRelationship,
)
from app.schemas.models import CorpusStats, HealthResponse
from app.search.bm25 import backend_name as bm25_backend
from app.search.reranker import backend_name as reranker_backend
from app.services import corpus
from app.services.regulatory import regulatory_overview
from app.search.embeddings import get_embedding_backend
from app.search.vector_store import (
    CLAUSES_COLLECTION,
    STANDARDS_COLLECTION,
    get_vector_store,
)

router = APIRouter(tags=["meta"])


def _corpus_stats(db: Database) -> CorpusStats:
    store = get_vector_store()
    standards_repo_ = standards_repo(db)
    clauses_repo_ = clauses_repo(db)
    standards = standards_repo_.count()
    verified = standards_repo_.count({"is_verified": True})
    mode_state = corpus.status(db)
    mode_dict = mode_state.as_dict()
    return CorpusStats(
        corpus_mode=mode_state.mode.value,
        corpus_mode_label=mode_dict["label"],
        corpus_mode_message=mode_state.message,
        corpus_content_mode=mode_dict["content_mode"],
        corpus_content_label=mode_dict["content_label"],
        usable_standards=mode_state.usable_standards,
        starved=mode_state.starved,
        tables=clauses_repo_.count({"is_table": True}),
        standards=standards,
        clauses=clauses_repo_.count(),
        requirements=requirements_repo(db).count(),
        regulatory_records=qcos_repo(db).count(),
        amendments=amendments_repo(db).count(),
        relationships=relationships_repo(db).count(),
        vectors_standards=store.count(STANDARDS_COLLECTION),
        vectors_clauses=store.count(CLAUSES_COLLECTION),
        dataset_status="verified" if verified and verified == standards else "demo",
        verified_standards=verified,
        demo_standards=standards - verified,
    )


@router.get("/health", response_model=HealthResponse)
def health(db: Database = Depends(db_session)) -> HealthResponse:
    embedding = get_embedding_backend()
    store = get_vector_store()
    return HealthResponse(
        status="ok",
        app=settings.app_name,
        environment=settings.app_env,
        database={"backend": active_backend(), "url": active_url_safe()},
        llm=get_llm().status(),
        retrieval={
            "embedding_backend": embedding.name,
            "embedding_dimension": embedding.dimension,
            "vector_backend": store.name,
            "vector_search": store.active_backend(CLAUSES_COLLECTION),
            "keyword_backend": bm25_backend(),
            "reranker": reranker_backend(),
            "weights": {
                "semantic": settings.weight_semantic,
                "bm25": settings.weight_bm25,
                "metadata": settings.weight_metadata,
            },
        },
        corpus=_corpus_stats(db),
        regulatory=regulatory_overview(db),
        disclaimer=DISCLAIMER,
    )


@router.get("/corpus/manifest")
def corpus_manifest() -> Dict[str, Any]:
    """The provenance manifest for everything in the corpus."""
    path: Path = settings.data_dir / "source_manifest.json"
    if not path.exists():
        return {"available": False, "message": "No source manifest has been generated yet."}
    return {"available": True, **json.loads(path.read_text(encoding="utf-8"))}


@router.get("/evaluation")
def evaluation_results() -> Dict[str, Any]:
    """The last recorded run of scripts/evaluate.py, read straight off disk.

    These are real measurements against ground truth assigned by reading the
    source documents (data/evaluation/evaluation_queries.json), not numbers
    computed for display. This endpoint never runs the evaluation itself -
    that takes tens of seconds and loads the embedding model - it only
    reports whatever the last run wrote, and says plainly when none exists.
    """
    path: Path = settings.data_dir / "evaluation" / "results.json"
    if not path.exists():
        return {
            "available": False,
            "message": (
                "No evaluation has been run yet. Run `python scripts/evaluate.py` "
                "from the repository root to generate one."
            ),
        }
    return {"available": True, **json.loads(path.read_text(encoding="utf-8"))}
