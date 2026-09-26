"""Corpus mode enforcement.

The platform can hold two kinds of document at the same time:

* **verified** - official BIS / gazette material, ``is_verified=True``
* **demo**     - the labelled synthetic corpus, ``is_demo=True``

``CORPUS_MODE`` decides which of them may be used to answer:

============  ==========================================================
DEMO          only synthetic documents
VERIFIED      only official documents. If none are loaded the platform
              answers nothing rather than quietly using synthetic data -
              a demo standard must never be presented as a real one.
MIXED         both, verified preferred in ranking, demo always labelled
============  ==========================================================

Every retrieval path funnels its standard filter through here, so switching
mode changes the whole application - discovery, RAG, consumer lookup and the
compliance analyzer all narrow together.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Sequence

from pymongo.database import Database

from app.core.config import settings
from app.core.constants import CorpusMode
from app.db.repositories import standards as standards_repo
from app.models import Standard

logger = logging.getLogger(__name__)

#: Ranking bonus applied to verified documents in MIXED mode, so official
#: material outranks a synthetic document of otherwise equal score.
VERIFIED_PREFERENCE_BONUS = 0.15


def current_mode() -> CorpusMode:
    raw = (settings.corpus_mode or "MIXED").strip().upper()
    try:
        return CorpusMode(raw)
    except ValueError:
        logger.warning("Unknown CORPUS_MODE %r - falling back to MIXED", raw)
        return CorpusMode.MIXED


def content_mode(verified: int, demo: int) -> Optional[CorpusMode]:
    """What is actually loaded, as opposed to what policy allows.

    ``current_mode()`` is a *policy* control: it decides which documents the
    platform may answer from, and it is set by configuration. That is not the
    same question as "what is in the corpus", and reporting only the policy is
    misleading - a corpus holding nothing but synthetic documents would still
    describe itself as "Mixed" purely because MIXED is the default setting.

    Returns None for an empty corpus, where neither label would be true.
    """
    if verified and demo:
        return CorpusMode.MIXED
    if verified:
        return CorpusMode.VERIFIED
    if demo:
        return CorpusMode.DEMO
    return None


_LABELS = {
    CorpusMode.DEMO: "Demo Corpus",
    CorpusMode.VERIFIED: "Verified Corpus",
    CorpusMode.MIXED: "Mixed Corpus",
}


@dataclass
class CorpusStatus:
    mode: CorpusMode
    verified_standards: int
    demo_standards: int
    usable_standards: int
    #: True when the configured mode cannot be served by what is loaded.
    starved: bool
    message: str

    @property
    def content(self) -> Optional[CorpusMode]:
        return content_mode(self.verified_standards, self.demo_standards)

    def as_dict(self) -> Dict[str, Any]:
        content = self.content
        return {
            "mode": self.mode.value,
            "verified_standards": self.verified_standards,
            "demo_standards": self.demo_standards,
            "usable_standards": self.usable_standards,
            "starved": self.starved,
            "message": self.message,
            "label": _LABELS[self.mode],
            # What the corpus actually holds, independent of the policy above.
            "content_mode": content.value if content else "EMPTY",
            "content_label": _LABELS[content] if content else "Empty Corpus",
        }


def mode_filter(mode: Optional[CorpusMode] = None) -> Dict[str, Any]:
    """The MongoDB filter fragment the current mode allows.

    Under SQLAlchemy this narrowed a Query object; the MongoDB equivalent is a
    filter dict that callers merge into their own ``find()`` criteria.
    """
    mode = mode or current_mode()
    if mode is CorpusMode.VERIFIED:
        return {"is_verified": True}
    if mode is CorpusMode.DEMO:
        return {"is_demo": True}
    return {}


def apply_mode(
    filt: Optional[Dict[str, Any]] = None, mode: Optional[CorpusMode] = None
) -> Dict[str, Any]:
    """Merge the corpus-mode restriction into an existing filter."""
    combined = dict(filt or {})
    combined.update(mode_filter(mode))
    return combined


def allowed_standard_ids(db: Database, mode: Optional[CorpusMode] = None) -> List[str]:
    """The ids every retrieval path is permitted to return."""
    return [
        doc["_id"] for doc in standards_repo(db).project(["_id"], apply_mode(mode=mode))
    ]


def filter_ids(
    db: Database, standard_ids: Sequence[str], mode: Optional[CorpusMode] = None
) -> List[str]:
    """Intersect a caller-supplied id list with what the mode allows."""
    if not standard_ids:
        return []
    allowed = set(allowed_standard_ids(db, mode))
    return [sid for sid in standard_ids if sid in allowed]


def is_allowed(db: Database, standard_id: str, mode: Optional[CorpusMode] = None) -> bool:
    return standards_repo(db).count(apply_mode({"_id": standard_id}, mode)) > 0


def ranking_bonus(standard: Standard, mode: Optional[CorpusMode] = None) -> float:
    """Preference applied to verified documents when both kinds are in play."""
    mode = mode or current_mode()
    if mode is CorpusMode.MIXED and standard.is_verified:
        return VERIFIED_PREFERENCE_BONUS
    return 0.0


def status(db: Database, mode: Optional[CorpusMode] = None) -> CorpusStatus:
    mode = mode or current_mode()
    repo = standards_repo(db)
    verified = repo.count({"is_verified": True})
    demo = repo.count({"is_demo": True})
    usable = len(allowed_standard_ids(db, mode))

    starved = usable == 0
    if mode is CorpusMode.VERIFIED and starved:
        message = (
            "CORPUS_MODE=VERIFIED but no official documents are loaded. The platform will "
            "answer nothing rather than fall back to the synthetic corpus. Ingest verified "
            "documents, or set CORPUS_MODE=MIXED to use the labelled demo corpus."
        )
    elif mode is CorpusMode.VERIFIED:
        message = f"Answering only from {verified} verified official document(s)."
    elif mode is CorpusMode.DEMO:
        message = (
            f"Answering only from {demo} synthetic demonstration document(s). "
            "No identifier here is a real IS number."
        )
    else:
        message = (
            f"Answering from {verified} verified and {demo} demonstration document(s). "
            "Verified records are preferred in ranking and demo records are labelled."
        )
    return CorpusStatus(
        mode=mode,
        verified_standards=verified,
        demo_standards=demo,
        usable_standards=usable,
        starved=starved,
        message=message,
    )


def starvation_note(db: Database) -> Optional[str]:
    """Message to surface to the user when the mode has nothing to work with."""
    state = status(db)
    return state.message if state.starved else None
