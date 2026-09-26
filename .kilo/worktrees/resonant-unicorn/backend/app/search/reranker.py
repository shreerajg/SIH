"""Reranking stage.

Hybrid retrieval is tuned for *recall* - it casts a wide net so the right
clause is somewhere in the candidate set. Reranking is about *precision*: given
the question and each candidate's full text, reorder so the most directly
responsive clause is first, because that is the one the model will lean on and
the one the user sees at the top of the citation list.

Two backends:

* ``cross-encoder`` - a small sentence-transformers cross-encoder that scores
  (question, clause) pairs jointly. Better, but needs a model download.
* ``lexical`` - a dependency-free scorer using term overlap, phrase hits,
  clause-type affinity and numeric-match signals. Always available.

The lexical reranker is the default fallback rather than "no reranking",
because doing nothing would leave BM25/vector fusion order untouched, and that
order is measurably worse for questions that name a specific quantity.
"""
from __future__ import annotations

import logging
import math
import re
import threading
from dataclasses import dataclass
from typing import List, Optional, Sequence, Tuple

from app.core.config import settings
from app.core.constants import QueryType
from app.core.text_utils import content_tokens

logger = logging.getLogger(__name__)

#: How much the reranker is allowed to move things. 1.0 = rerank order wins.
RERANK_WEIGHT = 0.65

#: Clause types that tend to answer each kind of question.
TYPE_AFFINITY = {
    QueryType.TEST_REQUIREMENT: {"test": 0.25, "table": 0.15, "requirement": 0.05},
    QueryType.MARKING_REQUIREMENT: {"marking": 0.30, "documentation": 0.10},
    QueryType.STANDARD_EXPLANATION: {"scope": 0.30, "definition": 0.15},
    QueryType.CONSUMER_LOOKUP: {"scope": 0.30, "definition": 0.10},
    QueryType.CLAUSE_LOOKUP: {"requirement": 0.15, "test": 0.10, "table": 0.10},
    QueryType.RELATED_STANDARD: {"reference": 0.35},
    QueryType.AMENDMENT_QUERY: {"requirement": 0.10},
    QueryType.PRODUCT_GAP_ANALYSIS: {"requirement": 0.20, "test": 0.15},
}

_NUMBER_RE = re.compile(r"\d+(?:\.\d+)?")


@dataclass
class RerankItem:
    """Anything rerankable: an id, the text to score, and its retrieval score."""

    id: str
    text: str
    retrieval_score: float = 0.0
    clause_type: str = ""


@dataclass
class RerankResult:
    id: str
    score: float
    rerank_score: float
    retrieval_score: float
    backend: str


class LexicalReranker:
    """Deterministic precision scorer. No model, no download, no network."""

    name = "lexical"

    def score(self, question: str, items: Sequence[RerankItem],
              query_type: Optional[QueryType] = None) -> List[float]:
        q_tokens = content_tokens(question)
        q_set = set(q_tokens)
        q_lower = (question or "").lower()
        q_numbers = set(_NUMBER_RE.findall(q_lower))
        # Bigrams catch "temperature rise" scoring above two loose words.
        q_bigrams = {f"{a} {b}" for a, b in zip(q_tokens, q_tokens[1:])}
        affinity = TYPE_AFFINITY.get(query_type, {}) if query_type else {}

        scores: List[float] = []
        for item in items:
            text_lower = (item.text or "").lower()
            t_tokens = content_tokens(item.text)
            t_set = set(t_tokens)
            if not t_set or not q_set:
                scores.append(0.0)
                continue

            overlap = len(q_set & t_set) / len(q_set)
            # Long clauses should not win purely by containing more words.
            density = len(q_set & t_set) / math.sqrt(len(t_set))
            phrase = sum(1 for bg in q_bigrams if bg in text_lower)
            phrase_score = min(1.0, phrase / max(len(q_bigrams), 1)) if q_bigrams else 0.0
            numbers = set(_NUMBER_RE.findall(text_lower))
            number_score = (
                len(q_numbers & numbers) / len(q_numbers) if q_numbers else 0.0
            )
            type_bonus = affinity.get(item.clause_type, 0.0)

            scores.append(
                0.40 * overlap
                + 0.20 * min(1.0, density)
                + 0.25 * phrase_score
                + 0.15 * number_score
                + type_bonus
            )
        return scores


class CrossEncoderReranker:
    """Cross-encoder scoring of (question, clause) pairs."""

    def __init__(self, model_name: str) -> None:
        from sentence_transformers import CrossEncoder  # heavy, local import

        self._model = CrossEncoder(model_name)
        self.name = f"cross-encoder:{model_name}"

    def score(self, question: str, items: Sequence[RerankItem],
              query_type: Optional[QueryType] = None) -> List[float]:
        del query_type
        pairs = [(question, item.text[:1500]) for item in items]
        raw = self._model.predict(pairs)
        lo, hi = float(min(raw)), float(max(raw))
        if hi - lo < 1e-9:
            return [0.5] * len(items)
        return [float((value - lo) / (hi - lo)) for value in raw]


_reranker = None
_lock = threading.Lock()


def get_reranker():
    """Process-wide reranker. Falls back to lexical, never to nothing."""
    global _reranker
    if _reranker is not None:
        return _reranker
    with _lock:
        if _reranker is not None:
            return _reranker
        if not settings.enable_reranker:
            _reranker = LexicalReranker()
            return _reranker
        model_name = (settings.reranker_model or "").strip()
        if model_name:
            try:
                _reranker = CrossEncoderReranker(model_name)
                logger.info("Reranker: %s", _reranker.name)
                return _reranker
            except Exception as exc:
                logger.warning(
                    "Cross-encoder '%s' unavailable (%s); using the lexical reranker.",
                    model_name, exc,
                )
        _reranker = LexicalReranker()
        return _reranker


def reset_reranker(reranker=None) -> None:
    """Test hook."""
    global _reranker
    _reranker = reranker


def rerank(
    question: str,
    items: Sequence[RerankItem],
    *,
    query_type: Optional[QueryType] = None,
    top_k: Optional[int] = None,
) -> List[RerankResult]:
    """Blend retrieval score with rerank score and reorder."""
    if not items:
        return []
    engine = get_reranker()
    try:
        rerank_scores = engine.score(question, items, query_type)
    except Exception as exc:  # pragma: no cover - model runtime issues
        logger.warning("Reranking failed (%s); keeping retrieval order.", exc)
        rerank_scores = [0.0] * len(items)

    results = [
        RerankResult(
            id=item.id,
            score=round(
                (1 - RERANK_WEIGHT) * item.retrieval_score + RERANK_WEIGHT * score, 6
            ),
            rerank_score=round(score, 6),
            retrieval_score=round(item.retrieval_score, 6),
            backend=getattr(engine, "name", "unknown"),
        )
        for item, score in zip(items, rerank_scores)
    ]
    results.sort(key=lambda r: -r.score)
    return results[:top_k] if top_k else results


def backend_name() -> str:
    return getattr(get_reranker(), "name", "unknown")
