"""Persistent vector store with a ChromaDB backend and a NumPy fallback.

Two collections are maintained:

* ``standards``  - one vector per standard (title + scope + keywords).
                   Used by stage 1 of retrieval (standard discovery).
* ``clauses``    - one vector per structure-aware clause chunk.
                   Used by stage 2 (clause retrieval), always filtered to the
                   standards selected in stage 1.
"""
from __future__ import annotations

import json
import logging
import os
import threading
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence

import numpy as np

from app.core.config import settings
from app.search.embeddings import get_embedding_backend

logger = logging.getLogger(__name__)

STANDARDS_COLLECTION = "standards"
CLAUSES_COLLECTION = "clauses"
#: Uploaded manufacturer evidence. Kept separate on purpose: a datasheet must
#: never be retrievable as though it were a clause of an Indian Standard.
PRODUCT_EVIDENCE_COLLECTION = "product_evidence"


@dataclass
class VectorHit:
    id: str
    score: float
    metadata: Dict[str, Any]
    document: str


class BaseVectorStore:
    name = "abstract"

    def upsert(self, collection: str, ids: Sequence[str], documents: Sequence[str],
               metadatas: Sequence[Dict[str, Any]]) -> None:
        raise NotImplementedError

    def query(self, collection: str, text: str, k: int = 10,
              allowed_standard_ids: Optional[Sequence[str]] = None) -> List[VectorHit]:
        raise NotImplementedError

    def count(self, collection: str) -> int:
        raise NotImplementedError

    def reset(self) -> None:
        raise NotImplementedError


def _flatten(meta: Dict[str, Any]) -> Dict[str, Any]:
    """Chroma only accepts scalar metadata values."""
    out: Dict[str, Any] = {}
    for key, value in meta.items():
        if value is None:
            continue
        if isinstance(value, (str, int, float, bool)):
            out[key] = value
        else:
            out[key] = json.dumps(value, default=str)
    return out


class ChromaVectorStore(BaseVectorStore):
    name = "chromadb"

    def __init__(self, path: str) -> None:
        import chromadb
        from chromadb.config import Settings as ChromaSettings

        Path(path).mkdir(parents=True, exist_ok=True)
        self._client = chromadb.PersistentClient(
            path=path, settings=ChromaSettings(anonymized_telemetry=False, allow_reset=True)
        )
        self._collections: Dict[str, Any] = {}

    def _collection(self, name: str):
        if name not in self._collections:
            self._collections[name] = self._client.get_or_create_collection(
                name=name, metadata={"hnsw:space": "cosine"}
            )
        return self._collections[name]

    def upsert(self, collection, ids, documents, metadatas):
        if not ids:
            return
        embeddings = get_embedding_backend().encode(list(documents)).tolist()
        self._collection(collection).upsert(
            ids=list(ids),
            documents=list(documents),
            metadatas=[_flatten(m) for m in metadatas],
            embeddings=embeddings,
        )

    def query(self, collection, text, k=10, allowed_standard_ids=None):
        col = self._collection(collection)
        if col.count() == 0:
            return []
        where = None
        if allowed_standard_ids:
            ids = list(dict.fromkeys(allowed_standard_ids))
            where = {"standard_id": {"$in": ids}} if len(ids) > 1 else {"standard_id": ids[0]}
        embedding = get_embedding_backend().encode([text])[0].tolist()
        result = col.query(
            query_embeddings=[embedding],
            n_results=min(k, max(col.count(), 1)),
            where=where,
            include=["documents", "metadatas", "distances"],
        )
        hits: List[VectorHit] = []
        for idx, doc_id in enumerate(result["ids"][0]):
            distance = result["distances"][0][idx]
            hits.append(
                VectorHit(
                    id=doc_id,
                    score=max(0.0, 1.0 - float(distance)),
                    metadata=result["metadatas"][0][idx] or {},
                    document=result["documents"][0][idx] or "",
                )
            )
        return hits

    def count(self, collection):
        try:
            return int(self._collection(collection).count())
        except Exception:
            return 0

    def reset(self):
        for name in (STANDARDS_COLLECTION, CLAUSES_COLLECTION, PRODUCT_EVIDENCE_COLLECTION):
            try:
                self._client.delete_collection(name)
            except Exception:
                pass
        self._collections.clear()


class NumpyVectorStore(BaseVectorStore):
    """Dependency-light fallback: cosine similarity over a persisted matrix."""

    name = "numpy"

    def __init__(self, path: str) -> None:
        self.path = Path(path)
        self.path.mkdir(parents=True, exist_ok=True)
        self._data: Dict[str, Dict[str, Any]] = {}
        for collection in (STANDARDS_COLLECTION, CLAUSES_COLLECTION, PRODUCT_EVIDENCE_COLLECTION):
            self._data[collection] = self._load(collection)

    def _file(self, collection: str) -> Path:
        return self.path / f"{collection}.npz"

    def _load(self, collection: str) -> Dict[str, Any]:
        file = self._file(collection)
        if not file.exists():
            return {"ids": [], "documents": [], "metadatas": [], "vectors": None}
        blob = np.load(file, allow_pickle=True)
        return {
            "ids": list(blob["ids"]),
            "documents": list(blob["documents"]),
            "metadatas": [json.loads(m) for m in blob["metadatas"]],
            "vectors": blob["vectors"],
        }

    def _save(self, collection: str) -> None:
        data = self._data[collection]
        np.savez(
            self._file(collection),
            ids=np.array(data["ids"], dtype=object),
            documents=np.array(data["documents"], dtype=object),
            metadatas=np.array(
                [json.dumps(m, default=str) for m in data["metadatas"]], dtype=object
            ),
            vectors=data["vectors"] if data["vectors"] is not None else np.zeros((0, 1), np.float32),
        )

    def upsert(self, collection, ids, documents, metadatas):
        if not ids:
            return
        data = self._data[collection]
        vectors = get_embedding_backend().encode(list(documents))
        index = {doc_id: i for i, doc_id in enumerate(data["ids"])}
        existing = data["vectors"]
        new_ids, new_docs, new_meta, new_vecs = [], [], [], []
        for i, doc_id in enumerate(ids):
            if doc_id in index and existing is not None:
                pos = index[doc_id]
                data["documents"][pos] = documents[i]
                data["metadatas"][pos] = dict(metadatas[i])
                existing[pos] = vectors[i]
            else:
                new_ids.append(doc_id)
                new_docs.append(documents[i])
                new_meta.append(dict(metadatas[i]))
                new_vecs.append(vectors[i])
        if new_ids:
            data["ids"].extend(new_ids)
            data["documents"].extend(new_docs)
            data["metadatas"].extend(new_meta)
            stacked = np.vstack(new_vecs).astype(np.float32)
            data["vectors"] = stacked if existing is None or len(existing) == 0 else np.vstack([existing, stacked])
        self._save(collection)

    def query(self, collection, text, k=10, allowed_standard_ids=None):
        data = self._data[collection]
        if data["vectors"] is None or len(data["ids"]) == 0:
            return []
        query_vec = get_embedding_backend().encode([text])[0]
        matrix = data["vectors"]
        scores = matrix @ query_vec
        allowed = set(allowed_standard_ids) if allowed_standard_ids else None
        order = np.argsort(-scores)
        hits: List[VectorHit] = []
        for pos in order:
            meta = data["metadatas"][pos]
            if allowed and meta.get("standard_id") not in allowed:
                continue
            hits.append(
                VectorHit(
                    id=data["ids"][pos],
                    score=float(max(0.0, scores[pos])),
                    metadata=meta,
                    document=data["documents"][pos],
                )
            )
            if len(hits) >= k:
                break
        return hits

    def count(self, collection):
        return len(self._data.get(collection, {}).get("ids", []))

    def reset(self):
        for collection in (STANDARDS_COLLECTION, CLAUSES_COLLECTION, PRODUCT_EVIDENCE_COLLECTION):
            file = self._file(collection)
            if file.exists():
                os.remove(file)
            self._data[collection] = {"ids": [], "documents": [], "metadatas": [], "vectors": None}


_store: Optional[BaseVectorStore] = None
_lock = threading.Lock()


def get_vector_store() -> BaseVectorStore:
    global _store
    if _store is not None:
        return _store
    with _lock:
        if _store is not None:
            return _store
        preference = (settings.vector_backend or "auto").lower()
        if preference in ("auto", "chroma", "chromadb"):
            try:
                _store = ChromaVectorStore(settings.chroma_path)
                logger.info("Vector store: chromadb at %s", settings.chroma_path)
                return _store
            except Exception as exc:
                logger.warning("ChromaDB unavailable (%s); using NumPy vector store.", exc)
        _store = NumpyVectorStore(str(Path(settings.chroma_path).parent / "numpy_vectors"))
        return _store


def reset_vector_store(store: Optional[BaseVectorStore] = None) -> None:
    global _store
    _store = store
