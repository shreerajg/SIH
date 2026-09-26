"""BM25 keyword index built from the relational corpus.

The index is rebuilt lazily whenever the underlying row count changes, which is
cheap for a prototype corpus and avoids a stale index after re-ingestion.
"""
from __future__ import annotations

import logging
import threading
from dataclasses import dataclass
from typing import Dict, List, Optional, Sequence

from pymongo.database import Database

from app.core.text_utils import tokenize
from app.db.repositories import clauses as clauses_repo
from app.db.repositories import standards as standards_repo

logger = logging.getLogger(__name__)

try:  # pragma: no cover - trivial import guard
    from rank_bm25 import BM25Okapi

    HAS_RANK_BM25 = True
except Exception:  # pragma: no cover
    BM25Okapi = None  # type: ignore
    HAS_RANK_BM25 = False


@dataclass
class BM25Hit:
    id: str
    score: float
    standard_id: str


class _SimpleBM25:
    """Pure-python BM25 used when rank_bm25 is not installed."""

    def __init__(self, corpus: Sequence[Sequence[str]], k1: float = 1.5, b: float = 0.75):
        self.k1, self.b = k1, b
        self.corpus = [list(doc) for doc in corpus]
        self.doc_len = [len(doc) for doc in self.corpus]
        self.avgdl = (sum(self.doc_len) / len(self.doc_len)) if self.doc_len else 0.0
        self.df: Dict[str, int] = {}
        self.tf: List[Dict[str, int]] = []
        for doc in self.corpus:
            counts: Dict[str, int] = {}
            for term in doc:
                counts[term] = counts.get(term, 0) + 1
            self.tf.append(counts)
            for term in counts:
                self.df[term] = self.df.get(term, 0) + 1
        self.N = len(self.corpus)

    def get_scores(self, query: Sequence[str]) -> List[float]:
        import math

        scores = [0.0] * self.N
        for term in query:
            if term not in self.df:
                continue
            idf = math.log(1 + (self.N - self.df[term] + 0.5) / (self.df[term] + 0.5))
            for i, counts in enumerate(self.tf):
                freq = counts.get(term, 0)
                if not freq:
                    continue
                denom = freq + self.k1 * (
                    1 - self.b + self.b * (self.doc_len[i] / (self.avgdl or 1))
                )
                scores[i] += idf * (freq * (self.k1 + 1)) / denom
        return scores


def _build(corpus: Sequence[Sequence[str]]):
    if HAS_RANK_BM25 and corpus:
        return BM25Okapi(list(corpus))
    return _SimpleBM25(corpus)


class BM25Index:
    def __init__(self) -> None:
        self._clause_index = None
        self._clause_ids: List[str] = []
        self._clause_standards: List[str] = []
        self._clause_count = -1

        self._standard_index = None
        self._standard_ids: List[str] = []
        self._standard_count = -1
        self._lock = threading.Lock()

    # -- clauses ---------------------------------------------------------
    def ensure_clauses(self, db: Database) -> None:
        repo = clauses_repo(db)
        total = repo.count()
        if self._clause_index is not None and total == self._clause_count:
            return
        with self._lock:
            rows = repo.project(
                ["chunk_id", "standard_id", "heading", "text", "clause_number"]
            )
            corpus, ids, standards = [], [], []
            for row in rows:
                ids.append(row.get("chunk_id", ""))
                standards.append(row.get("standard_id", ""))
                corpus.append(
                    tokenize(
                        f"{row.get('clause_number', '')} {row.get('heading', '')} "
                        f"{row.get('text', '')}"
                    )
                )
            self._clause_index = _build(corpus)
            self._clause_ids = ids
            self._clause_standards = standards
            self._clause_count = total
            logger.info("BM25 clause index rebuilt (%s chunks)", total)

    def search_clauses(
        self, db: Database, query: str, k: int = 20,
        allowed_standard_ids: Optional[Sequence[str]] = None,
    ) -> List[BM25Hit]:
        self.ensure_clauses(db)
        if not self._clause_ids:
            return []
        scores = self._clause_index.get_scores(tokenize(query))
        allowed = set(allowed_standard_ids) if allowed_standard_ids else None
        ranked = sorted(range(len(scores)), key=lambda i: -scores[i])
        hits: List[BM25Hit] = []
        for i in ranked:
            if scores[i] <= 0:
                break
            if allowed and self._clause_standards[i] not in allowed:
                continue
            hits.append(BM25Hit(self._clause_ids[i], float(scores[i]), self._clause_standards[i]))
            if len(hits) >= k:
                break
        return hits

    # -- standards -------------------------------------------------------
    def ensure_standards(self, db: Database) -> None:
        repo = standards_repo(db)
        total = repo.count()
        if self._standard_index is not None and total == self._standard_count:
            return
        with self._lock:
            rows = repo.project(
                ["is_number", "title", "scope", "keywords", "product_category"]
            )
            corpus, ids = [], []
            for row in rows:
                ids.append(row["_id"])
                kw = " ".join(row.get("keywords") or [])
                corpus.append(
                    tokenize(
                        f"{row.get('is_number', '')} {row.get('title', '')} "
                        f"{row.get('product_category', '')} {kw} {row.get('scope', '')}"
                    )
                )
            self._standard_index = _build(corpus)
            self._standard_ids = ids
            self._standard_count = total
            logger.info("BM25 standard index rebuilt (%s standards)", total)

    def search_standards(self, db: Database, query: str, k: int = 15) -> List[BM25Hit]:
        self.ensure_standards(db)
        if not self._standard_ids:
            return []
        scores = self._standard_index.get_scores(tokenize(query))
        ranked = sorted(range(len(scores)), key=lambda i: -scores[i])
        hits: List[BM25Hit] = []
        for i in ranked:
            if scores[i] <= 0:
                break
            hits.append(BM25Hit(self._standard_ids[i], float(scores[i]), self._standard_ids[i]))
            if len(hits) >= k:
                break
        return hits

    def invalidate(self) -> None:
        self._clause_count = -1
        self._standard_count = -1


_index = BM25Index()


def get_bm25_index() -> BM25Index:
    return _index


def backend_name() -> str:
    return "rank-bm25" if HAS_RANK_BM25 else "builtin-bm25"
