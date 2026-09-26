"""Vector store backed by MongoDB.

Three logical collections are maintained:

* ``standards``        - one vector per standard (title + scope + keywords).
                         Used by stage 1 of retrieval (standard discovery).
* ``clauses``          - one vector per structure-aware clause chunk.
                         Used by stage 2 (clause retrieval), always filtered to
                         the standards selected in stage 1.
* ``product_evidence`` - uploaded manufacturer evidence. Kept separate on
                         purpose: a datasheet must never be retrievable as
                         though it were a clause of an Indian Standard.

They are stored in MongoDB as ``vectors_standards``, ``vectors_clauses`` and
``vectors_product_evidence``. The ``vectors_`` prefix matters - the unprefixed
names would collide with the ``standards`` and ``product_evidence`` *data*
collections.

Search runs one of two ways, and ``/api/health`` always reports which:

* **Atlas Vector Search** (``$vectorSearch``) when a queryable vector index
  exists for the collection - a real ANN index, which is what a full BIS
  corpus would need.
* **Brute-force cosine** over the same stored vectors otherwise, e.g. while an
  index is still building or on a deployment without Atlas Search. Correct, and
  at this corpus size (a few hundred vectors) indistinguishable in latency -
  but never silently substituted.

Both paths read the same documents, so the fallback cannot drift from the
indexed path.
"""
from __future__ import annotations

import json
import logging
import threading
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Sequence

import numpy as np
from pymongo import ReplaceOne
from pymongo.errors import OperationFailure, PyMongoError

from app.core.config import settings
from app.db.mongo import get_database
from app.search.embeddings import get_embedding_backend

logger = logging.getLogger(__name__)

STANDARDS_COLLECTION = "standards"
CLAUSES_COLLECTION = "clauses"
PRODUCT_EVIDENCE_COLLECTION = "product_evidence"

ALL_COLLECTIONS = (STANDARDS_COLLECTION, CLAUSES_COLLECTION, PRODUCT_EVIDENCE_COLLECTION)

#: MongoDB collection name for a logical vector collection.
def mongo_collection_name(collection: str) -> str:
    return f"vectors_{collection}"


#: Atlas Vector Search index name for a logical vector collection.
def index_name(collection: str) -> str:
    return f"vector_index_{collection}"


#: all-MiniLM-L6-v2 output width. Asserted on upsert so a model swap cannot
#: silently write vectors the index will reject.
EMBEDDING_DIMENSIONS = 384


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


def _scalar_metadata(meta: Dict[str, Any]) -> Dict[str, Any]:
    """Keep metadata values scalar.

    BSON would happily store nested structures, but the previous store could
    not, so every consumer already expects scalars. Preserving that keeps the
    metadata shape identical across the migration.
    """
    out: Dict[str, Any] = {}
    for key, value in meta.items():
        if value is None:
            continue
        if isinstance(value, (str, int, float, bool)):
            out[key] = value
        else:
            out[key] = json.dumps(value, default=str)
    return out


class MongoVectorStore(BaseVectorStore):
    name = "mongodb"

    def __init__(self) -> None:
        self._lock = threading.Lock()
        #: Cached matrices for the brute-force path, invalidated by document
        #: count - the same strategy the BM25 index uses.
        self._cache: Dict[str, Dict[str, Any]] = {}
        #: Per-collection record of whether a queryable Atlas index was found.
        self._index_ready: Dict[str, bool] = {}

    # -- plumbing --------------------------------------------------------
    def _collection(self, collection: str):
        return get_database()[mongo_collection_name(collection)]

    def _has_vector_index(self, collection: str) -> bool:
        """True when a queryable Atlas vector index exists for this collection.

        Re-checked whenever it has not yet been seen as ready, so an index that
        finishes building mid-process is picked up without a restart.
        """
        if self._index_ready.get(collection):
            return True
        try:
            for idx in self._collection(collection).list_search_indexes():
                if idx.get("name") == index_name(collection) and idx.get("queryable"):
                    self._index_ready[collection] = True
                    return True
        except (OperationFailure, PyMongoError) as exc:
            logger.debug("Vector index probe failed for %s: %s", collection, exc)
        return False

    def active_backend(self, collection: str = CLAUSES_COLLECTION) -> str:
        """What /api/health reports: the indexed path or the fallback."""
        return "atlas-vector-search" if self._has_vector_index(collection) else "brute-force-cosine"

    # -- writes ----------------------------------------------------------
    def upsert(self, collection, ids, documents, metadatas):
        if not ids:
            return
        vectors = get_embedding_backend().encode(list(documents))
        if vectors.shape[1] != EMBEDDING_DIMENSIONS:
            raise ValueError(
                f"Embedding backend produced {vectors.shape[1]} dimensions, but the vector "
                f"index expects {EMBEDDING_DIMENSIONS}. Rebuild the index if the model changed."
            )
        operations = []
        for i, doc_id in enumerate(ids):
            meta = _scalar_metadata(dict(metadatas[i]))
            operations.append(
                ReplaceOne(
                    {"_id": doc_id},
                    {
                        "_id": doc_id,
                        # float() keeps these BSON doubles rather than numpy
                        # scalars, which PyMongo cannot encode.
                        "embedding": [float(x) for x in vectors[i]],
                        "document": documents[i],
                        # Promoted out of metadata so Atlas can filter on it.
                        "standard_id": meta.get("standard_id", ""),
                        "metadata": meta,
                    },
                    upsert=True,
                )
            )
        self._collection(collection).bulk_write(operations, ordered=False)
        with self._lock:
            self._cache.pop(collection, None)

    # -- reads -----------------------------------------------------------
    def query(self, collection, text, k=10, allowed_standard_ids=None):
        if self.count(collection) == 0:
            return []
        query_vector = get_embedding_backend().encode([text])[0]
        allowed = list(dict.fromkeys(allowed_standard_ids)) if allowed_standard_ids else None

        if self._has_vector_index(collection):
            try:
                return self._search_indexed(collection, query_vector, k, allowed)
            except (OperationFailure, PyMongoError) as exc:
                # An index that exists but cannot serve this query is reported,
                # never silently ignored.
                logger.warning(
                    "Atlas vector search failed on %s (%s); using brute-force cosine.",
                    collection, exc,
                )
                self._index_ready[collection] = False
        return self._search_brute_force(collection, query_vector, k, allowed)

    def _search_indexed(self, collection, query_vector, k, allowed) -> List[VectorHit]:
        stage: Dict[str, Any] = {
            "index": index_name(collection),
            "path": "embedding",
            "queryVector": [float(x) for x in query_vector],
            # Atlas guidance: oversample candidates well beyond the limit.
            "numCandidates": max(k * 20, 150),
            "limit": k,
        }
        if allowed:
            stage["filter"] = {"standard_id": {"$in": allowed}}
        pipeline = [
            {"$vectorSearch": stage},
            {
                "$project": {
                    "document": 1,
                    "metadata": 1,
                    "score": {"$meta": "vectorSearchScore"},
                }
            },
        ]
        hits: List[VectorHit] = []
        for doc in self._collection(collection).aggregate(pipeline):
            # Atlas returns cosine similarity remapped to (1 + cos) / 2.
            # Convert back so scores mean the same thing they did before, and
            # match the brute-force path exactly.
            cosine = 2.0 * float(doc.get("score", 0.0)) - 1.0
            hits.append(
                VectorHit(
                    id=doc["_id"],
                    score=max(0.0, cosine),
                    metadata=doc.get("metadata") or {},
                    document=doc.get("document") or "",
                )
            )
        return hits

    def _matrix(self, collection: str) -> Dict[str, Any]:
        """Cached in-memory copy of a collection, for the brute-force path."""
        total = self._collection(collection).count_documents({})
        cached = self._cache.get(collection)
        if cached is not None and cached["count"] == total:
            return cached
        with self._lock:
            rows = list(
                self._collection(collection).find(
                    {}, {"embedding": 1, "document": 1, "metadata": 1}
                )
            )
            data = {
                "count": total,
                "ids": [r["_id"] for r in rows],
                "documents": [r.get("document", "") for r in rows],
                "metadatas": [r.get("metadata") or {} for r in rows],
                "vectors": (
                    np.array([r["embedding"] for r in rows], dtype=np.float32)
                    if rows else np.zeros((0, EMBEDDING_DIMENSIONS), np.float32)
                ),
            }
            self._cache[collection] = data
            logger.info("Vector cache built for %s (%s vectors)", collection, total)
            return data

    def _search_brute_force(self, collection, query_vector, k, allowed) -> List[VectorHit]:
        data = self._matrix(collection)
        if not data["ids"]:
            return []
        matrix = data["vectors"]
        query = np.asarray(query_vector, dtype=np.float32)
        # sentence-transformers returns normalised vectors, so a dot product is
        # cosine similarity. Normalise defensively anyway so a different
        # embedding backend cannot quietly change the score's meaning.
        denom = (np.linalg.norm(matrix, axis=1) * np.linalg.norm(query)) + 1e-12
        scores = (matrix @ query) / denom
        allowed_set = set(allowed) if allowed else None
        hits: List[VectorHit] = []
        for pos in np.argsort(-scores):
            meta = data["metadatas"][pos]
            if allowed_set and meta.get("standard_id") not in allowed_set:
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

    # -- admin -----------------------------------------------------------
    def count(self, collection):
        try:
            return int(self._collection(collection).count_documents({}))
        except PyMongoError:
            return 0

    def reset(self):
        db = get_database()
        for collection in ALL_COLLECTIONS:
            db.drop_collection(mongo_collection_name(collection))
        with self._lock:
            self._cache.clear()
        self._index_ready.clear()


def ensure_vector_indexes(create: bool = True) -> Dict[str, str]:
    """Create the Atlas vector search indexes if the deployment supports them.

    Returns {collection: status}. Index builds are asynchronous, so a freshly
    created index reports "building" and the store keeps using the brute-force
    path until it becomes queryable.
    """
    db = get_database()
    report: Dict[str, str] = {}
    for collection in ALL_COLLECTIONS:
        name = index_name(collection)
        mongo_name = mongo_collection_name(collection)
        try:
            existing = {
                idx.get("name"): idx for idx in db[mongo_name].list_search_indexes()
            }
        except (OperationFailure, PyMongoError) as exc:
            # Not an Atlas deployment, or the tier has no Search. The store
            # falls back to brute force; this is reported, not hidden.
            report[collection] = f"unavailable ({exc.__class__.__name__})"
            continue

        if name in existing:
            report[collection] = "queryable" if existing[name].get("queryable") else "building"
            continue
        if not create:
            report[collection] = "missing"
            continue
        try:
            # The raw command rather than Collection.create_search_index():
            # PyMongo 4.6's helper predates vectorSearch indexes and drops the
            # "type" field, which the server then rejects as a malformed Atlas
            # Search index ("Attribute mappings missing"). The command works on
            # every driver version.
            db.command(
                {
                    "createSearchIndexes": mongo_name,
                    "indexes": [
                        {
                            "name": name,
                            "type": "vectorSearch",
                            "definition": {
                                "fields": [
                                    {
                                        "type": "vector",
                                        "path": "embedding",
                                        "numDimensions": EMBEDDING_DIMENSIONS,
                                        "similarity": "cosine",
                                    },
                                    {"type": "filter", "path": "standard_id"},
                                ]
                            },
                        }
                    ],
                }
            )
            report[collection] = "created"
            logger.info("Created Atlas vector index %s on %s", name, mongo_name)
        except (OperationFailure, PyMongoError) as exc:
            report[collection] = f"failed ({exc.__class__.__name__})"
            logger.warning("Could not create vector index %s: %s", name, exc)
    return report


_store: Optional[BaseVectorStore] = None
_lock = threading.Lock()


def get_vector_store() -> BaseVectorStore:
    global _store
    if _store is not None:
        return _store
    with _lock:
        if _store is None:
            _store = MongoVectorStore()
            logger.info("Vector store: mongodb (database: %s)", settings.mongo_db_name)
        return _store


def reset_vector_store(store: Optional[BaseVectorStore] = None) -> None:
    global _store
    _store = store
