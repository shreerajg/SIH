"""Certification process guidance.

Answers "how do I actually get certified for this product?" as an ordered
journey whose steps are backed by the documents the platform holds for that
specific product.

The design follows ``services/findings.py``: the stage *template* says what
happens, and the *evidence* for each stage is resolved at query time by finding
a clause in this standard's own documents (its BIS Product Manual, its Quality
Control Order) that literally contains the stage's topic. Nothing is quoted
into the template, so a citation can never drift from the corpus.

What keeps this honest:

* **A stage is evidenced or it is marked unevidenced.** A stage that matches no
  clause is still listed - the step exists in the real process - but it carries
  an explicit note that no supporting document is held, never invented prose.
* **Application mechanics are marked external.** The BIS portal procedure, fees
  and forms are not in this corpus, so that stage links to the official BIS page
  and says outright that it is not clause-cited.
* **The timeline is read from the order's own table**, including the separate
  implementation dates BIS sets for micro and small enterprises, rather than
  being generalised to a single date.
* **No scheme, no process.** Guidance is only produced for a scheme that the
  certification resolver actually confirmed for this standard.
"""
from __future__ import annotations

import logging
import re
from typing import Any, Dict, List, Optional, Sequence

from pymongo import ASCENDING
from pymongo.database import Database

from app.core.constants import DISCLAIMER
from app.db.repositories import clauses as clauses_repo
from app.db.repositories import processes as processes_repo
from app.db.repositories import standards as standards_repo
from app.models import Standard, StandardClause
from app.schemas.models import (
    ComplianceDeadline,
    ComplianceTimeline,
    ProcessGuidance,
    ProcessStage,
)
from app.services import certification
from app.services.serializers import clause_ref

logger = logging.getLogger(__name__)

NO_EVIDENCE_NOTE = (
    "No clause in the documents held for this standard covers this step. The step is part of "
    "the process, but this platform has no source for it - follow the official BIS guidance."
)

NO_SCHEME_MESSAGE = (
    "No certification scheme could be confirmed for this standard from available BIS data, so "
    "no certification process can be described. A process is only shown for a scheme that a "
    "stored Quality Control Order or the official BIS product list actually names."
)

#: Column headings in a QCO implementation table, mapped to a readable label.
#: Matching is on the heading text BIS itself uses.
ENTERPRISE_PATTERNS = [
    ("micro enterprises", "Micro enterprises"),
    ("small enterprises", "Small enterprises"),
    ("medium enterprises", "Medium enterprises"),
    ("other than micro and small", "All other enterprises"),
    ("in general", "All other enterprises"),
]

_DATE_RE = re.compile(
    r"\b\d{1,2}\s*(?:st|nd|rd|th)?\s+[A-Z][a-z]+,?\s+\d{4}\b|\b\d{4}-\d{2}-\d{2}\b"
)


# ---------------------------------------------------------------------------
# Evidence resolution
# ---------------------------------------------------------------------------

def _documents_for(db: Database, standard: Standard) -> List[Standard]:
    """The standard itself plus any regulatory document that names it.

    A Product Manual carries the process obligations; the Quality Control Order
    carries the legal position and the dates. Both are searched, so a stage can
    cite whichever one actually covers it.
    """
    docs = [standard]
    from app.db.repositories import qcos as qcos_repo

    seen = {standard.id}
    for qco in qcos_repo(db).find({"standard_id": standard.id}):
        if not qco.document_id or qco.document_id in seen:
            continue
        # QCO records name the gazette document they were transcribed from;
        # that document is itself ingested as a standard-like record.
        source = standards_repo(db).get(qco.document_id)
        if source is not None:
            docs.append(source)
            seen.add(source.id)
    return docs


def _clause_matching(
    clauses: Sequence[StandardClause], keywords: Sequence[str]
) -> Optional[StandardClause]:
    """The clause a stage is *about*, not merely the first that mentions it.

    Literal containment is still the gate - a stage can only ever cite text
    that really contains its topic, exactly as services/findings.py requires.
    Among the clauses that pass that gate the best one is chosen, because
    taking the first in clause order cites whichever clause happens to mention
    the term in passing: "Standard Mark" appears inside the Quality Assurance
    Plan clause long before the clause headed MARKING.

    The signals, in order of weight:

    * the term appears in the clause **heading** - headings are topical;
    * the clause **opens** with the term ("MARKING - The Standard Mark ...");
    * the term appears more than once;
    * earlier keywords in the stage's list are more specific than later ones;
    * table chunks are demoted - a table listing a term is rarely the clause
      that explains it.
    """
    best: Optional[StandardClause] = None
    best_score = 0.0

    for rank, keyword in enumerate(keywords):
        needle = keyword.lower().strip()
        if not needle:
            continue
        # Earlier keywords are the more specific phrasings.
        specificity = max(0.0, 3.0 - rank * 0.4)

        for clause in clauses:
            heading = (clause.heading or "").lower()
            text = (clause.text or "").lower()
            if needle not in heading and needle not in text:
                continue

            score = specificity
            if needle in heading:
                score += 10.0
            position = text.find(needle)
            if 0 <= position <= 60:
                score += 6.0
            score += min(text.count(needle), 3)
            if clause.is_table:
                score -= 5.0

            if score > best_score:
                best, best_score = clause, score

    return best


def _resolve_stage(
    db: Database,
    stage: Dict[str, Any],
    documents: List[Standard],
    clauses_by_standard: Dict[str, List[StandardClause]],
) -> ProcessStage:
    external = bool(stage.get("external"))
    built = ProcessStage(
        id=stage["id"],
        order=int(stage.get("order", 0)),
        title=stage.get("title", ""),
        actor=stage.get("actor", "manufacturer"),
        summary=stage.get("summary", ""),
        what_you_do=list(stage.get("what_you_do") or []),
        documents=list(stage.get("documents") or []),
        external=external,
        external_url=stage.get("external_url") or None,
    )
    if external:
        built.evidence_note = stage.get("external_note") or NO_EVIDENCE_NOTE
        return built

    keywords = list(stage.get("clause_keywords") or [])
    preferred = {t.lower() for t in (stage.get("prefer_document_types") or [])}

    # Search the preferred document type first, then everything else, so a
    # Product Manual stage cites the manual rather than a gazette that happens
    # to use the same word.
    ordered = sorted(
        documents,
        key=lambda d: 0 if (d.document_type or "").lower() in preferred else 1,
    )
    for document in ordered:
        clauses = clauses_by_standard.get(document.id) or []
        match = _clause_matching(clauses, keywords)
        if match is not None:
            built.evidence = clause_ref(match, document, excerpt_chars=700)
            return built

    built.evidence_note = NO_EVIDENCE_NOTE
    return built


# ---------------------------------------------------------------------------
# Timeline
# ---------------------------------------------------------------------------

def _extract_timeline(
    documents: List[Standard], clauses_by_standard: Dict[str, List[StandardClause]]
) -> ComplianceTimeline:
    """Implementation dates from a QCO table, split by enterprise size.

    Read out of the stored table structure rather than parsed from prose, and
    only reported when the table really carries dated columns.
    """
    for document in documents:
        for clause in clauses_by_standard.get(document.id) or []:
            table = clause.table_json or {}
            headers = [str(h) for h in (table.get("headers") or [])]
            if not headers:
                continue
            date_columns = {
                index: label
                for index, header in enumerate(headers)
                for pattern, label in ENTERPRISE_PATTERNS
                if pattern in header.lower()
            }
            if not date_columns:
                continue

            deadlines: List[ComplianceDeadline] = []
            for row in table.get("rows") or []:
                cells = [str(c).strip() for c in row]
                # Skip the "(1) (2) (3)" column-number row BIS tables carry.
                if all(re.fullmatch(r"\(\d+\)", c or "") for c in cells if c):
                    continue
                for index, label in date_columns.items():
                    if index >= len(cells):
                        continue
                    value = cells[index]
                    if not value or not _DATE_RE.search(value):
                        continue
                    deadlines.append(
                        ComplianceDeadline(
                            enterprise_category=label,
                            date=value,
                            standard=cells[1] if len(cells) > 1 else None,
                            product=cells[0] if cells else None,
                        )
                    )
            if deadlines:
                return ComplianceTimeline(
                    available=True,
                    deadlines=deadlines,
                    evidence=clause_ref(clause, document, excerpt_chars=400),
                    note=(
                        "Implementation dates read from the Quality Control Order's own table. "
                        "BIS sets different dates for micro and small enterprises, so check the "
                        "row that matches your enterprise category."
                    ),
                )

    return ComplianceTimeline(
        available=False,
        note=(
            "No implementation-date table was found in the documents held for this standard. "
            "Check the Quality Control Order directly for the date that applies to you."
        ),
    )


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def _empty(message: str, standard_id: Optional[str] = None) -> ProcessGuidance:
    return ProcessGuidance(
        standard_id=standard_id,
        available=False,
        message=message,
        disclaimer=DISCLAIMER,
    )


def resolve_for_standard(db: Database, standard_id: str) -> ProcessGuidance:
    """The certification journey for one standard, stage by stage."""
    standard = standards_repo(db).get(standard_id)
    if standard is None:
        return _empty(f"No standard with id '{standard_id}' is in the corpus.", standard_id)

    # The process only exists for a scheme that was actually confirmed.
    scheme_guidance = certification.resolve_for_standard(db, standard_id)
    if scheme_guidance.scheme is None:
        return _empty(NO_SCHEME_MESSAGE, standard_id)

    template = processes_repo(db).find_one({"scheme_id": scheme_guidance.scheme.id})
    if template is None:
        return _empty(
            f"No certification process is described for {scheme_guidance.scheme.name} in this "
            "platform's data.",
            standard_id,
        )

    documents = _documents_for(db, standard)
    clauses_by_standard = {
        document.id: clauses_repo(db).find(
            {"standard_id": document.id}, sort=[("clause_number", ASCENDING)]
        )
        for document in documents
    }

    stages = [
        _resolve_stage(db, stage, documents, clauses_by_standard)
        for stage in sorted(template.stages, key=lambda s: int(s.get("order", 0)))
    ]
    evidenced = sum(1 for s in stages if s.evidence is not None)

    return ProcessGuidance(
        scheme_id=scheme_guidance.scheme.id,
        scheme_name=scheme_guidance.scheme.name,
        standard_id=standard_id,
        title=template.title,
        summary=template.summary,
        process_url=template.process_url or scheme_guidance.scheme.process_url,
        stages=stages,
        timeline=_extract_timeline(documents, clauses_by_standard),
        stages_with_evidence=evidenced,
        available=True,
        message=(
            f"{evidenced} of {len(stages)} steps are supported by a clause in the documents held "
            f"for {standard.is_number}."
        ),
        disclaimer=DISCLAIMER,
    )


def resolve_for_product(db: Database, product) -> ProcessGuidance:
    """The journey for a product, via the scheme resolved for its standards."""
    scheme_payload = certification.resolve_for_product(db, product)
    primary = scheme_payload.get("primary")
    if primary is None or primary.scheme is None or not primary.standard_id:
        return _empty(
            scheme_payload.get("note") or NO_SCHEME_MESSAGE,
        )
    return resolve_for_standard(db, primary.standard_id)
