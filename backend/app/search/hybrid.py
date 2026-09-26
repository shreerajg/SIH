"""Two-stage hybrid retrieval engine.

Stage 1 - standard discovery
    Search standard metadata (title / scope / keywords) with BM25 + dense
    vectors + a metadata affinity signal derived from the structured product
    profile. Produces a *closed candidate list*.

Stage 2 - clause retrieval
    Search clause chunks restricted to the standards chosen in stage 1. This
    is what stops semantically similar but irrelevant clauses from other
    product families flooding the context window.

Scores are fused with configurable weights - they are tuning knobs, not
scientific constants, and they never leak to the UI as a "confidence".
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Sequence

from pymongo.database import Database

from pymongo import ASCENDING

from app.core.config import settings
from app.core.text_utils import content_tokens
from app.db.repositories import clauses as clauses_repo
from app.db.repositories import standards as standards_repo
from app.models import Standard, StandardClause
from app.services import corpus
from app.search.bm25 import get_bm25_index
from app.search.vector_store import CLAUSES_COLLECTION, STANDARDS_COLLECTION, get_vector_store

logger = logging.getLogger(__name__)

#: Standards that legitimately apply across product families and must never be
#: penalised for a category mismatch.
HORIZONTAL_CATEGORIES = {"horizontal", "test-method", ""}

#: Multiplier applied to a product-specific standard from a different family.
CROSS_FAMILY_PENALTY = 0.35


def _normalise(scores: Dict[str, float]) -> Dict[str, float]:
    if not scores:
        return {}
    values = list(scores.values())
    lo, hi = min(values), max(values)
    if hi - lo < 1e-9:
        return {k: (1.0 if hi > 0 else 0.0) for k in scores}
    return {k: (v - lo) / (hi - lo) for k, v in scores.items()}


@dataclass
class StandardCandidate:
    standard: Standard
    score: float
    semantic_score: float = 0.0
    bm25_score: float = 0.0
    metadata_score: float = 0.0
    matched_keywords: List[str] = field(default_factory=list)
    signals: Dict[str, Any] = field(default_factory=dict)


@dataclass
class ClauseHit:
    clause: StandardClause
    score: float
    semantic_score: float = 0.0
    bm25_score: float = 0.0

    @property
    def chunk_id(self) -> str:
        return self.clause.chunk_id


class HybridRetriever:
    def __init__(self) -> None:
        self.w_semantic = settings.weight_semantic
        self.w_bm25 = settings.weight_bm25
        self.w_metadata = settings.weight_metadata

    # ------------------------------------------------------------------
    # Stage 1
    # ------------------------------------------------------------------
    def discover_standards(
        self,
        db: Database,
        query_text: str,
        *,
        profile_tokens: Optional[Sequence[str]] = None,
        category_hint: str = "",
        limit: Optional[int] = None,
    ) -> List[StandardCandidate]:
        limit = limit or settings.discovery_candidate_limit
        # The corpus mode decides which documents may be answered from at all.
        standards = {
            s.id: s for s in standards_repo(db).find(corpus.apply_mode())
        }
        if not standards:
            return []

        bm25_raw = {
            hit.id: hit.score
            for hit in get_bm25_index().search_standards(db, query_text, k=len(standards))
        }
        semantic_raw: Dict[str, float] = {}
        try:
            for hit in get_vector_store().query(
                STANDARDS_COLLECTION, query_text, k=min(len(standards), 25)
            ):
                sid = hit.metadata.get("standard_id") or hit.id
                semantic_raw[sid] = max(semantic_raw.get(sid, 0.0), hit.score)
        except Exception as exc:  # pragma: no cover - store may be empty
            logger.warning("Vector search failed during standard discovery: %s", exc)

        bm25 = _normalise(bm25_raw)
        semantic = _normalise(semantic_raw)

        tokens = set(profile_tokens or content_tokens(query_text))
        candidates: List[StandardCandidate] = []
        for sid, standard in standards.items():
            keywords = [k.lower() for k in (standard.keywords or [])]
            matched = sorted({k for k in keywords if k in tokens})
            # Multi-word keywords are matched against the raw query text.
            lowered = (query_text or "").lower()
            matched += sorted(
                {k for k in keywords if " " in k and k in lowered and k not in matched}
            )
            keyword_score = len(matched) / max(len(keywords), 1) if keywords else 0.0
            standard_category = (standard.product_category or "").lower()
            same_family = bool(category_hint) and category_hint.lower() == standard_category
            horizontal = standard_category in HORIZONTAL_CATEGORIES
            category_score = 1.0 if same_family else 0.0
            metadata_score = min(1.0, 0.75 * keyword_score + 0.25 * category_score)

            s_sem = semantic.get(sid, 0.0)
            s_bm = bm25.get(sid, 0.0)
            total = (
                self.w_semantic * s_sem
                + self.w_bm25 * s_bm
                + self.w_metadata * metadata_score
            )
            # A product-specific standard for a different product family is
            # near-duplicate noise (a cooker standard surfacing for a water
            # heater, because both say "domestic"). Horizontal standards -
            # general safety, test methods, marking - are never penalised
            # because they are meant to apply across families.
            cross_family = bool(category_hint) and not same_family and not horizontal
            if cross_family:
                total *= CROSS_FAMILY_PENALTY
            # In MIXED mode an official document outranks a synthetic one of
            # otherwise equal score.
            verified_bonus = corpus.ranking_bonus(standard)
            total += verified_bonus
            if total <= 0 and not matched:
                continue
            candidates.append(
                StandardCandidate(
                    standard=standard,
                    score=round(total, 6),
                    semantic_score=round(s_sem, 6),
                    bm25_score=round(s_bm, 6),
                    metadata_score=round(metadata_score, 6),
                    matched_keywords=matched,
                    signals={
                        "keyword_coverage": round(keyword_score, 4),
                        "category_match": bool(category_score),
                        "horizontal_standard": horizontal,
                        "cross_family_penalised": cross_family,
                        "verified_preference": round(verified_bonus, 4),
                    },
                )
            )

        candidates.sort(key=lambda c: -c.score)
        return candidates[:limit]

    # ------------------------------------------------------------------
    # Stage 2
    # ------------------------------------------------------------------
    def retrieve_clauses(
        self,
        db: Database,
        query_text: str,
        standard_ids: Sequence[str],
        *,
        k: Optional[int] = None,
    ) -> List[ClauseHit]:
        k = k or settings.clause_top_k
        standard_ids = corpus.filter_ids(db, list(standard_ids))
        if not standard_ids:
            return []

        bm25_raw = {
            hit.id: hit.score
            for hit in get_bm25_index().search_clauses(
                db, query_text, k=k * 4, allowed_standard_ids=standard_ids
            )
        }
        semantic_raw: Dict[str, float] = {}
        try:
            for hit in get_vector_store().query(
                CLAUSES_COLLECTION, query_text, k=k * 4, allowed_standard_ids=list(standard_ids)
            ):
                chunk_id = hit.metadata.get("chunk_id") or hit.id
                semantic_raw[chunk_id] = max(semantic_raw.get(chunk_id, 0.0), hit.score)
        except Exception as exc:  # pragma: no cover
            logger.warning("Vector search failed during clause retrieval: %s", exc)

        bm25 = _normalise(bm25_raw)
        semantic = _normalise(semantic_raw)
        chunk_ids = set(bm25) | set(semantic)
        if not chunk_ids:
            # Nothing matched lexically or semantically - fall back to the
            # scope/requirement clauses of the selected standards so the user
            # still sees genuine source material rather than an empty screen.
            fallback = clauses_repo(db).find(
                {"standard_id": {"$in": list(standard_ids)}},
                sort=[("clause_number", ASCENDING)],
                limit=k,
            )
            return [ClauseHit(clause=c, score=0.0) for c in fallback]

        clauses = {
            c.chunk_id: c
            for c in clauses_repo(db).find({"chunk_id": {"$in": list(chunk_ids)}})
        }
        denom = self.w_semantic + self.w_bm25
        hits: List[ClauseHit] = []
        for chunk_id, clause in clauses.items():
            s_sem = semantic.get(chunk_id, 0.0)
            s_bm = bm25.get(chunk_id, 0.0)
            total = (self.w_semantic * s_sem + self.w_bm25 * s_bm) / denom
            hits.append(
                ClauseHit(
                    clause=clause,
                    score=round(total, 6),
                    semantic_score=round(s_sem, 6),
                    bm25_score=round(s_bm, 6),
                )
            )
        hits.sort(key=lambda h: -h.score)
        return hits[:k]


_retriever: Optional[HybridRetriever] = None


def get_retriever() -> HybridRetriever:
    global _retriever
    if _retriever is None:
        _retriever = HybridRetriever()
    return _retriever
