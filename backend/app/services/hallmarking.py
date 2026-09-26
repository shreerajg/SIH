"""BIS hallmarking guidance - consumer and jeweller.

Answers "what is hallmarking?", "what should I check before buying?" and "how
do I get jewellery hallmarked?" from the official BIS hallmarking documents
ingested into this corpus.

The anti-hallucination contract, the same one the rest of the platform follows:

* **Every fact is resolved to a clause at query time.** A stored record carries
  only the fact plus the keywords that identify it; the supporting text is
  found live in the ingested BIS document. A fact whose keywords match nothing
  is returned as ``UNABLE_TO_VERIFY`` with no evidence, never as bare prose.
* **No live HUID verification exists here.** The platform explains what a HUID
  is and where BIS publishes verification. It never reports a HUID as genuine,
  valid or registered, because it has not checked one - see :func:`huid_guidance`.
* **A jeweller is never described as BIS-registered** and a centre is never
  described as recognised except by quoting the directory BIS publishes, with
  its retrieval date attached.
* **Absence is not a negative finding.** A centre missing from the local
  snapshot means the snapshot does not list it, not that it is unrecognised.
* **Suspended centres are shown as suspended**, not filtered away, because a
  jeweller needs to know why a centre they used is no longer usable.
"""
from __future__ import annotations

import logging
import re
from typing import Any, Dict, List, Optional, Sequence

from pymongo import ASCENDING
from pymongo.database import Database

from app.core.constants import DISCLAIMER, VerificationState
from app.db.repositories import clauses as clauses_repo
from app.db.repositories import hallmarking as hallmarking_repo
from app.db.repositories import hallmarking_centres as centres_repo
from app.db.repositories import standards as standards_repo
from app.models import HallmarkingKnowledge, Standard, StandardClause
from app.schemas.models import (
    AssayingCentre,
    CentreDirectorySummary,
    CentreSearchResponse,
    ConsumerHallmarkGuide,
    HallmarkComponent,
    HallmarkFact,
    HallmarkingOverview,
    HallmarkProcessStage,
    HuidGuidance,
    JewellerHallmarkGuide,
    PurityGrade,
)
from app.services.serializers import clause_ref

logger = logging.getLogger(__name__)

#: The ingested official BIS hallmarking documents. Facts are only ever cited
#: from these - a hallmarking claim can never borrow a clause from a product
#: standard that happens to use the word "marking".
HALLMARKING_DOCUMENT_IDS = [
    "BIS-HM-BRIEF",
    "BIS-HM-FAQ-GENERAL",
    "BIS-HM-FAQ-CONSUMER",
    "BIS-HM-CONSUMER-PROTECTION",
    "BIS-HM-REGULATIONS-2018",
    "BIS-HM-MANDATORY-ORDER-2020",
    "BIS-HM-JEWELLER-GUIDELINES",
    "BIS-HM-JEWELLER-REGISTRATION",
    "BIS-HM-AHC-GUIDELINES",
]

NO_EVIDENCE_NOTE = (
    "No clause in the ingested BIS hallmarking documents supports this point, so it is "
    "reported as unable to verify rather than stated."
)

NO_CORPUS_MESSAGE = (
    "No official BIS hallmarking document is loaded in this corpus. Run "
    "scripts/fetch_hallmarking_sources.py, scripts/prepare_hallmarking_corpus.py and then "
    "ingest data/raw/hallmarking. Until then the platform cannot answer hallmarking "
    "questions from verified data."
)

NO_CENTRE_DIRECTORY = (
    "No verified Assaying & Hallmarking Centre directory is currently available in the local "
    "corpus. Use the official BIS list rather than assuming a centre is or is not recognised."
)

HUID_NOT_VERIFIED = (
    "This platform is not connected to the BIS HUID verification service and has NOT checked "
    "this code. It cannot tell you whether a HUID is genuine, or whether a particular article "
    "is hallmarked. Verify through the official BIS channels."
)


# ---------------------------------------------------------------------------
# Citation resolution
# ---------------------------------------------------------------------------

def corpus_available(db: Database) -> bool:
    return standards_repo(db).count({"_id": {"$in": HALLMARKING_DOCUMENT_IDS}}) > 0


def _documents(db: Database, prefer: Sequence[str] = ()) -> List[Standard]:
    """The ingested hallmarking documents, preferred ones first."""
    rows = standards_repo(db).find({"_id": {"$in": HALLMARKING_DOCUMENT_IDS}})
    order = {doc_id: index for index, doc_id in enumerate(prefer)}
    rows.sort(key=lambda s: (order.get(s.id, len(order)), s.id))
    return rows


def _best_clause(
    clauses: Sequence[StandardClause], keywords: Sequence[str]
) -> Optional[StandardClause]:
    """The clause a fact is *about*.

    Literal containment is the gate - a fact may only cite text that really
    contains its term. Among the clauses that pass, the best is chosen, because
    taking the first would cite whichever clause mentions the phrase in passing.
    """
    best: Optional[StandardClause] = None
    best_score = 0.0
    for rank, keyword in enumerate(keywords):
        needle = (keyword or "").lower().strip()
        if not needle:
            continue
        specificity = max(0.0, 3.0 - rank * 0.4)
        for clause in clauses:
            heading = (clause.heading or "").lower()
            text = (clause.text or "").lower()
            if needle not in heading and needle not in text:
                continue
            score = specificity
            if needle in heading:
                score += 8.0
            position = text.find(needle)
            if 0 <= position <= 80:
                score += 4.0
            score += min(text.count(needle), 3)
            if clause.is_table:
                score -= 4.0
            if score > best_score:
                best, best_score = clause, score
    return best


class _Resolver:
    """Caches the hallmarking clauses so one request does not re-read them."""

    def __init__(self, db: Database) -> None:
        self.db = db
        self._documents = {d.id: d for d in _documents(db)}
        self._clauses: Dict[str, List[StandardClause]] = {}

    def clauses_for(self, document_id: str) -> List[StandardClause]:
        if document_id not in self._clauses:
            self._clauses[document_id] = clauses_repo(self.db).find(
                {"standard_id": document_id}, sort=[("clause_number", ASCENDING)]
            )
        return self._clauses[document_id]

    def cite(self, record: HallmarkingKnowledge):
        """(evidence, state) for one knowledge record."""
        keywords = list(record.clause_keywords or [])
        if not keywords:
            return None, VerificationState.UNABLE_TO_VERIFY

        prefer = list(record.prefer_document_ids or [])
        if record.source_document_id:
            prefer = [record.source_document_id] + prefer
        ordered = [d for d in prefer if d in self._documents]
        ordered += [d for d in self._documents if d not in ordered]

        for document_id in ordered:
            document = self._documents[document_id]
            match = _best_clause(self.clauses_for(document_id), keywords)
            if match is not None:
                return clause_ref(match, document, excerpt_chars=600), VerificationState.VERIFIED
        return None, VerificationState.UNABLE_TO_VERIFY


def _records(db: Database, kind: str) -> List[HallmarkingKnowledge]:
    return hallmarking_repo(db).find({"kind": kind}, sort=[("order", ASCENDING)])


# ---------------------------------------------------------------------------
# Overview
# ---------------------------------------------------------------------------

def overview(db: Database, resolver: Optional[_Resolver] = None) -> HallmarkingOverview:
    if not corpus_available(db):
        return HallmarkingOverview(available=False, message=NO_CORPUS_MESSAGE, disclaimer=DISCLAIMER)

    resolver = resolver or _Resolver(db)
    rows = _records(db, "scheme")
    if not rows:
        return HallmarkingOverview(available=False, message=NO_CORPUS_MESSAGE, disclaimer=DISCLAIMER)

    record = rows[0]
    payload = record.payload or {}
    evidence, state = resolver.cite(record)

    standards: List[HallmarkFact] = []
    keywords = payload.get("standards_clause_keywords") or []
    if keywords:
        probe = HallmarkingKnowledge(
            id="scheme::standards",
            kind="scheme",
            clause_keywords=keywords,
            source_document_id="BIS-HM-FAQ-GENERAL",
        )
        standard_evidence, standard_state = resolver.cite(probe)
        standards.append(
            HallmarkFact(
                id="hallmarking-standards",
                text="The Indian Standards that govern hallmarking of gold and silver articles.",
                state=standard_state,
                evidence=standard_evidence,
                note="" if standard_evidence else NO_EVIDENCE_NOTE,
            )
        )

    return HallmarkingOverview(
        available=True,
        name=payload.get("name", "BIS Hallmarking Scheme"),
        summary=payload.get("summary", ""),
        operated_by=payload.get("operated_by"),
        materials=list(payload.get("materials") or []),
        legal_basis=payload.get("legal_basis"),
        state=state,
        evidence=evidence,
        source_url=payload.get("source_url"),
        standards=standards,
        message="" if evidence else NO_EVIDENCE_NOTE,
        disclaimer=DISCLAIMER,
    )


# ---------------------------------------------------------------------------
# Purity grades / components / HUID
# ---------------------------------------------------------------------------

def purity_grades(
    db: Database, material: Optional[str] = None, resolver: Optional[_Resolver] = None
) -> List[PurityGrade]:
    resolver = resolver or _Resolver(db)
    out: List[PurityGrade] = []
    for record in _records(db, "purity_grade"):
        payload = record.payload or {}
        if material and (payload.get("material") or "").lower() != material.lower():
            continue
        evidence, state = resolver.cite(record)
        out.append(
            PurityGrade(
                id=record.id.split("::", 1)[-1],
                material=payload.get("material", ""),
                carat=payload.get("carat"),
                fineness=payload.get("fineness"),
                permitted_marking=payload.get("permitted_marking"),
                mandatory_order_covered=bool(payload.get("mandatory_order_covered")),
                note=payload.get("note"),
                state=state,
                evidence=evidence,
            )
        )
    return out


def hallmark_components(
    db: Database, material: str = "gold", resolver: Optional[_Resolver] = None
) -> List[HallmarkComponent]:
    resolver = resolver or _Resolver(db)
    out: List[HallmarkComponent] = []
    for record in _records(db, "hallmark_component"):
        payload = record.payload or {}
        applies = [a.lower() for a in (payload.get("applies_to") or [])]
        if material and applies and material.lower() not in applies:
            continue
        evidence, state = resolver.cite(record)
        out.append(
            HallmarkComponent(
                id=record.id.split("::", 1)[-1],
                order=record.order,
                name=payload.get("name", ""),
                description=payload.get("description", ""),
                applies_to=list(payload.get("applies_to") or []),
                state=state,
                evidence=evidence,
            )
        )
    return out


def huid_guidance(db: Database, resolver: Optional[_Resolver] = None) -> HuidGuidance:
    """What a HUID is - and an explicit statement that nothing was checked.

    ``live_verification_available`` is hard-coded False. It is not a setting: no
    HUID verification service is integrated, so there is no state in which this
    platform may report a HUID as valid.
    """
    resolver = resolver or _Resolver(db)
    rows = _records(db, "huid")
    if not rows:
        return HuidGuidance(
            available=False,
            state=VerificationState.UNABLE_TO_VERIFY,
            live_verification_available=False,
            verification_note=HUID_NOT_VERIFIED,
        )
    record = rows[0]
    payload = record.payload or {}
    evidence, state = resolver.cite(record)
    return HuidGuidance(
        available=True,
        length=payload.get("length"),
        character_set=payload.get("character_set"),
        description=payload.get("description", ""),
        in_force_from=payload.get("in_force_from"),
        state=state,
        evidence=evidence,
        live_verification_available=False,
        # The scheme-level statement of what this platform can and cannot do.
        # HUID_NOT_VERIFIED is reserved for describe_huid_format(), which is
        # about one specific submitted code - saying both here just repeats it.
        verification_note=payload.get("verification_note", "") or HUID_NOT_VERIFIED,
        official_verification_url=payload.get("official_verification_url"),
    )


def describe_huid_format(db: Database, huid: str) -> Dict[str, Any]:
    """Describe a submitted code against the documented HUID format.

    This is a *format* observation only. It deliberately returns no verdict on
    authenticity: ``checked_against_bis`` is always False, and the caller must
    present the result as "not verified" no matter how well the code matches.
    """
    guidance = huid_guidance(db)
    cleaned = re.sub(r"\s+", "", huid or "").upper()
    expected = guidance.length or 6

    observations: List[str] = []
    if not cleaned:
        observations.append("No code was entered.")
    else:
        observations.append(f"You entered {len(cleaned)} character(s).")
        if guidance.available:
            observations.append(
                f"BIS documents a {expected}-character alphanumeric HUID."
            )
            if len(cleaned) != expected:
                observations.append(
                    f"That is a different length from the documented format."
                )
            if not cleaned.isalnum():
                observations.append("A HUID is alphanumeric; this contains other characters.")

    return {
        "entered": cleaned,
        "expected_length": expected if guidance.available else None,
        "matches_documented_format": bool(
            guidance.available and cleaned and len(cleaned) == expected and cleaned.isalnum()
        ),
        # The load-bearing flag: nothing was checked against BIS.
        "checked_against_bis": False,
        "state": VerificationState.UNABLE_TO_VERIFY.value,
        "observations": observations,
        "verification_note": HUID_NOT_VERIFIED,
        "official_verification_url": guidance.official_verification_url,
    }


# ---------------------------------------------------------------------------
# Consumer guide
# ---------------------------------------------------------------------------

def consumer_guide(db: Database, material: str = "gold") -> ConsumerHallmarkGuide:
    if not corpus_available(db):
        return ConsumerHallmarkGuide(
            available=False, material=material, message=NO_CORPUS_MESSAGE, disclaimer=DISCLAIMER
        )

    resolver = _Resolver(db)
    checks: List[HallmarkFact] = []
    for record in _records(db, "consumer_check"):
        payload = record.payload or {}
        evidence, state = resolver.cite(record)
        checks.append(
            HallmarkFact(
                id=record.id.split("::", 1)[-1],
                text=payload.get("text", ""),
                state=state,
                evidence=evidence,
                note="" if evidence else NO_EVIDENCE_NOTE,
            )
        )

    components = hallmark_components(db, material, resolver)
    grades = purity_grades(db, material, resolver)
    evidenced = (
        sum(1 for c in checks if c.evidence)
        + sum(1 for c in components if c.evidence)
        + sum(1 for g in grades if g.evidence)
    )

    return ConsumerHallmarkGuide(
        available=True,
        material=material,
        overview=overview(db, resolver),
        components=components,
        purity_grades=grades,
        checks=checks,
        huid=huid_guidance(db, resolver),
        facts_with_evidence=evidenced,
        message=(
            f"{evidenced} point(s) are supported by a clause in the official BIS hallmarking "
            "documents held in this corpus."
        ),
        disclaimer=DISCLAIMER,
    )


# ---------------------------------------------------------------------------
# Jeweller journey
# ---------------------------------------------------------------------------

def jeweller_guide(db: Database) -> JewellerHallmarkGuide:
    summary = centre_summary(db)
    if not corpus_available(db):
        return JewellerHallmarkGuide(
            available=False,
            centre_summary=summary,
            message=NO_CORPUS_MESSAGE,
            disclaimer=DISCLAIMER,
        )

    resolver = _Resolver(db)
    stages: List[HallmarkProcessStage] = []
    for record in _records(db, "process_stage"):
        payload = record.payload or {}
        evidence, state = resolver.cite(record)
        stages.append(
            HallmarkProcessStage(
                id=record.id.split("::", 1)[-1],
                order=record.order,
                title=payload.get("title", ""),
                actor=payload.get("actor", "jeweller"),
                summary=payload.get("summary", ""),
                what_you_do=list(payload.get("what_you_do") or []),
                state=state,
                evidence=evidence,
                evidence_note="" if evidence else NO_EVIDENCE_NOTE,
            )
        )
    stages.sort(key=lambda s: s.order)
    evidenced = sum(1 for s in stages if s.evidence)

    return JewellerHallmarkGuide(
        available=bool(stages),
        title="Getting jewellery hallmarked",
        summary=(
            "The route from confirming that hallmarking applies to you, through jeweller "
            "registration and a recognised Assaying & Hallmarking Centre, to the hallmark and "
            "HUID on each article."
        ),
        stages=stages,
        stages_with_evidence=evidenced,
        centre_summary=summary,
        message=(
            f"{evidenced} of {len(stages)} steps are supported by a clause in the official BIS "
            "hallmarking documents held in this corpus."
        ),
        disclaimer=DISCLAIMER,
    )


# ---------------------------------------------------------------------------
# Assaying & Hallmarking Centres
# ---------------------------------------------------------------------------

def centre_summary(db: Database) -> CentreDirectorySummary:
    repo = centres_repo(db)
    total = repo.count()
    if total == 0:
        return CentreDirectorySummary(available=False, note=NO_CENTRE_DIRECTORY)

    sample = repo.find({}, limit=1)
    first = sample[0] if sample else None
    return CentreDirectorySummary(
        available=True,
        total=total,
        operative=repo.count({"status": {"$regex": "^Operative", "$options": "i"}}),
        states=sorted(s for s in repo.distinct("state") if s),
        source_url=first.source_url if first else None,
        retrieved_at=first.retrieved_at if first else None,
        note=(
            "A snapshot of the directory BIS publishes. Recognition can change between "
            "snapshots, so confirm a centre against the live BIS list before relying on it. "
            "Centres under suspension are shown with that status rather than hidden."
        ),
    )


def search_centres(
    db: Database,
    *,
    state: Optional[str] = None,
    city: Optional[str] = None,
    operative_only: bool = False,
    limit: int = 50,
) -> CentreSearchResponse:
    summary = centre_summary(db)
    if not summary.available:
        return CentreSearchResponse(summary=summary, message=NO_CENTRE_DIRECTORY)

    filt: Dict[str, Any] = {}
    if state:
        filt["state"] = {"$regex": f"^{re.escape(state)}$", "$options": "i"}
    if city:
        filt["city"] = {"$regex": re.escape(city), "$options": "i"}
    if operative_only:
        filt["status"] = {"$regex": "^Operative", "$options": "i"}

    repo = centres_repo(db)
    total = repo.count(filt)
    rows = repo.find(filt, sort=[("state", ASCENDING), ("city", ASCENDING)], limit=limit)

    return CentreSearchResponse(
        summary=summary,
        total_matching=total,
        results=[
            AssayingCentre(
                recognition_number=c.recognition_number,
                name=c.name,
                city=c.city or None,
                state=c.state or None,
                pin=c.pin or None,
                scope=c.scope or None,
                status=c.status,
                validity=c.validity,
                phone=c.phone,
                email=c.email,
            )
            for c in rows
        ],
        message=(
            f"{total} centre(s) match in a snapshot of {summary.total} taken on "
            f"{summary.retrieved_at}."
            if total
            else (
                "No centre in the local snapshot matches that filter. That means the snapshot "
                "does not list one - not that none exists. Check the official BIS list."
            )
        ),
    )
