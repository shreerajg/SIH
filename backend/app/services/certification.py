"""BIS certification scheme guidance.

Answers "which BIS certification scheme applies to this product, and why?"
without ever guessing.

The anti-hallucination contract of this module, in the same spirit as
``services/regulatory.py``:

* **Applicability is resolved from stored records only.** Two independent kinds
  of evidence are consulted, in priority order:

  1. the ``scheme`` field recorded on a stored QCO for the standard, and
  2. the standard's presence in the extracted official BIS Scheme-I product
     list (``scheme_product_index``).

* **A scheme is never inferred from a product category, a product name or a
  standard's subject matter.** If neither source names a scheme, the answer is
  ``UNABLE_TO_VERIFY`` with an explanatory message - never a plausible guess.
* **Absence is not evidence.** A standard missing from the Scheme-I list means
  "not found in the snapshot we hold", not "not covered by Scheme-I".
* **Mandatory vs voluntary is delegated**, not re-derived: the existing
  ``resolve_regulatory_status`` remains the single source of that answer, and
  its ``UNABLE_TO_VERIFY`` state is passed through unchanged.
* **Descriptive fields are only shown where they were sourced.** A scheme whose
  content has not been transcribed from an official BIS document reports those
  fields as unavailable rather than filling them in.
"""
from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

from pymongo.database import Database

from app.core.constants import RegulatoryStatus, SchemeApplicability
from app.core.text_utils import normalize_is_number
from app.db.repositories import qcos as qcos_repo
from app.db.repositories import scheme_products as scheme_products_repo
from app.db.repositories import schemes as schemes_repo
from app.db.repositories import standards as standards_repo
from app.models import CertificationScheme, Standard
from app.schemas.models import (
    SchemeEvidence,
    SchemeGuidance,
    SchemeInfo,
    SchemeReason,
)
from app.services.regulatory import resolve_regulatory_status

logger = logging.getLogger(__name__)

UNVERIFIABLE_FIELD = "Unable to verify from available BIS data"

UNABLE_MESSAGE = (
    "No stored BIS record names a certification scheme for this standard. The platform "
    "will not infer a scheme from the product type - check the applicable Quality Control "
    "Order or the BIS product certification pages directly."
)


# ---------------------------------------------------------------------------
# Scheme registry
# ---------------------------------------------------------------------------

def list_schemes(db: Database) -> List[SchemeInfo]:
    """Every registered scheme, verified ones first."""
    rows = schemes_repo(db).find()
    rows.sort(key=lambda s: (not s.is_verified, s.code))
    return [to_info(s) for s in rows]


def get_scheme(db: Database, scheme_id: str) -> Optional[CertificationScheme]:
    repo = schemes_repo(db)
    record = repo.get(scheme_id) or repo.get((scheme_id or "").upper())
    if record is not None:
        return record
    return repo.find_one({"code": scheme_id})


def find_scheme_by_text(db: Database, text: str) -> Optional[CertificationScheme]:
    """Resolve a scheme from free text ("what is Scheme I?", "ISI mark").

    Matching is against stored aliases only, longest alias first so "scheme i"
    cannot shadow a more specific phrase. Nothing is fuzzy-matched: an
    unrecognised name returns None and the caller says so.
    """
    lowered = (text or "").lower()
    if not lowered.strip():
        return None
    best: Optional[CertificationScheme] = None
    best_len = 0
    for record in schemes_repo(db).find():
        for alias in list(record.aliases or []) + [record.code.lower(), record.name.lower()]:
            alias = (alias or "").strip().lower()
            if not alias or alias not in lowered:
                continue
            if len(alias) > best_len:
                best, best_len = record, len(alias)
    return best


def _field(value: Any) -> Optional[str]:
    """A descriptive field, or None when it was never sourced."""
    if isinstance(value, str):
        return value.strip() or None
    return value or None


def to_info(record: CertificationScheme) -> SchemeInfo:
    return SchemeInfo(
        id=record.id,
        code=record.code,
        name=record.name,
        mark=_field(record.mark),
        purpose=_field(record.purpose),
        applies_to=_field(record.applies_to),
        product_applicability=_field(record.product_applicability),
        legal_basis=_field(record.legal_basis),
        testing_requirement=_field(record.testing_requirement),
        key_documents=list(record.key_documents or []),
        process_url=_field(record.process_url),
        source_url=_field(record.source_url),
        document_id=_field(record.document_id),
        retrieved_at=record.retrieved_at,
        is_verified=bool(record.is_verified),
        field_sources=dict(record.field_sources or {}),
        unavailable_fields=sorted(
            name
            for name in (
                "purpose", "applies_to", "product_applicability", "legal_basis",
                "testing_requirement", "mark", "process_url",
            )
            if not _field(getattr(record, name, None))
        ),
        unavailable_note=UNVERIFIABLE_FIELD,
    )


# ---------------------------------------------------------------------------
# Applicability resolution
# ---------------------------------------------------------------------------

def _unable(reason: str, standard_id: str = "") -> SchemeGuidance:
    return SchemeGuidance(
        applicability=SchemeApplicability.UNABLE_TO_VERIFY,
        scheme=None,
        standard_id=standard_id or None,
        reasons=[],
        evidence=[],
        regulatory=None,
        message=reason,
    )


def resolve_for_standard(db: Database, standard_id: str) -> SchemeGuidance:
    """Which scheme applies to one standard, and on what evidence.

    Evidence is gathered from the QCO record first (it names the scheme
    explicitly and is the stronger source) and then from the official Scheme-I
    product list. Both are reported; the scheme is only returned when at least
    one of them names it.
    """
    standard: Optional[Standard] = standards_repo(db).get(standard_id)
    if standard is None:
        return _unable(f"No standard with id '{standard_id}' is in the corpus.", standard_id)

    reasons: List[SchemeReason] = []
    evidence: List[SchemeEvidence] = []
    resolved: Optional[CertificationScheme] = None

    # --- evidence 1: the scheme named on a stored QCO --------------------
    qco = None
    qco_rows = qcos_repo(db).find({"standard_id": standard_id})
    # Prefer a verified record over a demo one when both exist.
    qco_rows.sort(key=lambda q: (not q.is_verified,))
    if qco_rows:
        qco = qco_rows[0]
    if qco is not None and (qco.scheme or "").strip():
        named = find_scheme_by_text(db, qco.scheme)
        evidence.append(
            SchemeEvidence(
                kind="qco_record",
                label=qco.qco_name or qco.notification_number or qco.id,
                detail=qco.scheme,
                source_url=qco.source_url or None,
                document_id=qco.document_id or None,
                is_verified=bool(qco.is_verified),
                retrieved_at=qco.retrieved_at.date().isoformat() if qco.retrieved_at else None,
            )
        )
        if named is not None:
            resolved = named
            reasons.append(
                SchemeReason(
                    factor="Quality Control Order",
                    detail=(
                        f"The stored Quality Control Order for {standard.is_number} names "
                        f"\"{qco.scheme}\"."
                    ),
                    source="qco_record",
                    is_verified=bool(qco.is_verified),
                )
            )
        else:
            logger.info(
                "QCO %s names scheme %r which is not in the scheme registry",
                qco.id, qco.scheme,
            )

    # --- evidence 2: the official BIS Scheme-I product list ---------------
    normalized = standard.normalized_number or normalize_is_number(standard.is_number) or ""
    listing = None
    if normalized:
        listing = scheme_products_repo(db).find_one({"normalized_number": normalized})
    if listing is not None:
        evidence.append(
            SchemeEvidence(
                kind="scheme_product_list",
                label=f"{listing.is_number} - {listing.product}",
                detail=(
                    "Listed by BIS under products requiring compulsory certification"
                    + (f" (group: {listing.product_group})" if listing.product_group else "")
                ),
                source_url=listing.source_url or None,
                document_id=listing.document_id or None,
                is_verified=bool(listing.is_verified),
                retrieved_at=listing.retrieved_at,
            )
        )
        if resolved is None:
            resolved = get_scheme(db, listing.scheme_id)
        if resolved is not None:
            reasons.append(
                SchemeReason(
                    factor="BIS product list",
                    detail=(
                        f"{listing.is_number} appears in the official BIS Scheme-I list of "
                        f"products under compulsory certification, as \"{listing.product}\"."
                    ),
                    source="scheme_product_list",
                    is_verified=bool(listing.is_verified),
                )
            )

    if resolved is None:
        guidance = _unable(UNABLE_MESSAGE, standard_id)
        guidance.evidence = evidence
        guidance.regulatory = resolve_regulatory_status(db, standard_id)
        return guidance

    # Mandatory / voluntary is answered by the existing regulatory engine, not
    # re-derived here, so there is exactly one source of that answer.
    regulatory = resolve_regulatory_status(db, standard_id)
    if regulatory.status is RegulatoryStatus.UNABLE_TO_VERIFY:
        reasons.append(
            SchemeReason(
                factor="Regulatory status",
                detail=(
                    "No Quality Control Order record is stored for this standard, so whether "
                    "certification is legally required cannot be confirmed here."
                ),
                source="regulatory_engine",
                is_verified=False,
            )
        )
    else:
        reasons.append(
            SchemeReason(
                factor="Regulatory status",
                detail=(
                    f"Certification under this scheme is {regulatory.status.value} for this "
                    f"standard, per the stored regulatory record."
                ),
                source="regulatory_engine",
                is_verified=bool(regulatory.verified),
            )
        )

    # Both sources agreeing is a stronger answer than either alone.
    confirmed = len([e for e in evidence if e.is_verified]) > 0
    applicability = (
        SchemeApplicability.APPLICABLE if confirmed else SchemeApplicability.LIKELY
    )
    message = (
        f"{resolved.name} applies to {standard.is_number} on the evidence below."
        if confirmed
        else (
            f"{resolved.name} is indicated for {standard.is_number}, but the supporting "
            "record is from the demonstration corpus rather than a verified BIS source."
        )
    )

    return SchemeGuidance(
        applicability=applicability,
        scheme=to_info(resolved),
        standard_id=standard_id,
        reasons=reasons,
        evidence=evidence,
        regulatory=regulatory,
        message=message,
    )


def resolve_for_product(db: Database, product) -> Dict[str, Any]:
    """Scheme guidance for a product, across its matched standards.

    Runs on the standards discovery already produced for the product, so the
    chain the user sees is: product -> matched standard -> QCO / BIS list ->
    scheme. A product with no discovered standards gets an explicit note rather
    than a guess.
    """
    matches = list(product.matches or [])
    if not matches:
        return {
            "product_id": product.id,
            "primary": None,
            "per_standard": [],
            "note": (
                "No applicable standards are on file for this product yet. Run standard "
                "discovery first - the certification scheme is resolved from the standards "
                "matched to the product, never from the product description alone."
            ),
        }

    per_standard = [resolve_for_standard(db, m.standard_id) for m in matches]

    # The primary recommendation is the strongest verified answer available.
    def rank(g: SchemeGuidance) -> tuple:
        order = {
            SchemeApplicability.APPLICABLE: 0,
            SchemeApplicability.LIKELY: 1,
            SchemeApplicability.UNABLE_TO_VERIFY: 2,
        }
        mandatory = (
            0 if g.regulatory and g.regulatory.status is RegulatoryStatus.MANDATORY else 1
        )
        return (order[g.applicability], mandatory)

    ranked = sorted(per_standard, key=rank)
    primary = ranked[0] if ranked and ranked[0].scheme is not None else None

    return {
        "product_id": product.id,
        "primary": primary,
        "per_standard": per_standard,
        "note": (
            ""
            if primary is not None
            else (
                "None of the standards matched to this product has a stored record naming a "
                "certification scheme, so no scheme can be confirmed from available BIS data."
            )
        ),
    }
