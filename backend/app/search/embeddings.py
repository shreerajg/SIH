"""Embedding backends.

``all-MiniLM-L6-v2`` via sentence-transformers is preferred. When the model
cannot be loaded (no network on first run, restricted environment) the service
degrades to a deterministic hashing embedder so that ingestion, indexing and
semantic-ish retrieval still work. The active backend is surfaced through
``/api/health`` so nothing is silently swapped.
"""
from __future__ import annotations

import hashlib
import logging
import re
import threading
from typing import List, Optional, Sequence

import numpy as np

from app.core.config import settings

logger = logging.getLogger(__name__)

_TOKEN_RE = re.compile(r"[a-z0-9]+")


class EmbeddingBackend:
    name = "abstract"
    dimension = 0

    def encode(self, texts: Sequence[str]) -> np.ndarray:  # pragma: no cover
        raise NotImplementedError


class HashingEmbedding(EmbeddingBackend):
    """Deterministic bag-of-ngrams projection.

    Not a neural embedding, but it is stable, dependency free and gives usable
    lexical-semantic overlap for the demo corpus when transformers are absent.
    """

    name = "hashing-fallback"

    def __init__(self, dimension: int = 384) -> None:
        self.dimension = dimension

    def _features(self, text: str) -> List[str]:
        tokens = _TOKEN_RE.findall((text or "").lower())
        feats = list(tokens)
        feats += [f"{a}_{b}" for a, b in zip(tokens, tokens[1:])]
        for token in tokens:
            if len(token) > 5:
                feats += [token[i : i + 4] for i in range(len(token) - 3)]
        return feats

    def encode(self, texts: Sequence[str]) -> np.ndarray:
        out = np.zeros((len(texts), self.dimension), dtype=np.float32)
        for row, text in enumerate(texts):
            for feature in self._features(text):
                digest = hashlib.blake2b(feature.encode("utf-8"), digest_size=8).digest()
                index = int.from_bytes(digest[:4], "little") % self.dimension
                sign = 1.0 if digest[4] % 2 == 0 else -1.0
                out[row, index] += sign
            norm = np.linalg.norm(out[row])
            if norm > 0:
                out[row] /= norm
        return out


class SentenceTransformerEmbedding(EmbeddingBackend):
    name = "sentence-transformers"

    def __init__(self, model_name: str) -> None:
        from sentence_transformers import SentenceTransformer  # local import: heavy

        self._model = SentenceTransformer(model_name)
        self.name = f"sentence-transformers:{model_name}"
        self.dimension = int(self._model.get_sentence_embedding_dimension())

    def encode(self, texts: Sequence[str]) -> np.ndarray:
        vectors = self._model.encode(
            list(texts), normalize_embeddings=True, show_progress_bar=False,
            batch_size=32, convert_to_numpy=True,
        )
        return np.asarray(vectors, dtype=np.float32)


_backend: Optional[EmbeddingBackend] = None
_lock = threading.Lock()


def get_embedding_backend() -> EmbeddingBackend:
    """Process-wide singleton - the model is loaded exactly once."""
    global _backend
    if _backend is not None:
        return _backend
    with _lock:
        if _backend is not None:
            return _backend
        preference = (settings.embedding_backend or "auto").lower()
        if preference in ("auto", "sentence-transformers", "st"):
            try:
                _backend = SentenceTransformerEmbedding(settings.embedding_model)
                logger.info("Embedding backend: %s (dim=%s)", _backend.name, _backend.dimension)
                return _backend
            except Exception as exc:
                logger.warning(
                    "sentence-transformers unavailable (%s); using hashing fallback.", exc
                )
        _backend = HashingEmbedding()
        return _backend


def reset_embedding_backend(backend: Optional[EmbeddingBackend] = None) -> None:
    """Test hook."""
    global _backend
    _backend = backend
