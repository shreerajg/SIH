"""BIS certification scheme guidance endpoints.

Read-only. Every answer here is resolved from stored records by
``app/services/certification.py``; nothing on this router infers a scheme from
a product description, and an unknown scheme is reported as such rather than
approximated.
"""
from __future__ import annotations

from typing import Any, Dict, List

from fastapi import APIRouter, Depends, HTTPException, Query
from pymongo.database import Database

from app.api.deps import db_session, get_product
from app.core.constants import DISCLAIMER
from app.models import Product
from app.schemas.models import (
    ProcessGuidance,
    ProductSchemeGuidance,
    SchemeGuidance,
    SchemeInfo,
)
from app.services import certification, certification_process

router = APIRouter(tags=["certification"])


@router.get("/certification/schemes", response_model=List[SchemeInfo])
def list_schemes(db: Database = Depends(db_session)) -> List[SchemeInfo]:
    """The registered BIS certification schemes.

    Schemes whose descriptive content has not been sourced from an official BIS
    document are still listed - with their unsourced fields named in
    ``unavailable_fields`` - so the registry never looks more complete than it
    is.
    """
    return certification.list_schemes(db)


@router.get("/certification/schemes/{scheme_id}", response_model=SchemeInfo)
def get_scheme(scheme_id: str, db: Database = Depends(db_session)) -> SchemeInfo:
    record = certification.get_scheme(db, scheme_id)
    if record is None:
        raise HTTPException(
            status_code=404,
            detail=(
                f"No BIS certification scheme is registered under '{scheme_id}'. "
                "GET /api/certification/schemes lists the ones that are."
            ),
        )
    return certification.to_info(record)


@router.get("/certification/lookup", response_model=SchemeInfo)
def lookup_scheme(
    q: str = Query(..., description="Free text, e.g. 'Scheme I' or 'ISI mark'"),
    db: Database = Depends(db_session),
) -> SchemeInfo:
    """Resolve a scheme from a plain-language name.

    Backs the assistant's "what is Scheme I?" path. Matching is against stored
    aliases only - an unrecognised name is a 404, never a nearest guess.
    """
    record = certification.find_scheme_by_text(db, q)
    if record is None:
        raise HTTPException(
            status_code=404,
            detail=(
                f"'{q}' does not match any BIS certification scheme on record. "
                "GET /api/certification/schemes lists the registered ones."
            ),
        )
    return certification.to_info(record)


@router.get("/standards/{standard_id}/certification-scheme", response_model=SchemeGuidance)
def scheme_for_standard(
    standard_id: str, db: Database = Depends(db_session)
) -> SchemeGuidance:
    """Which scheme applies to one standard, with the records that say so."""
    return certification.resolve_for_standard(db, standard_id)


@router.get(
    "/products/{product_id}/certification-scheme", response_model=ProductSchemeGuidance
)
def scheme_for_product(
    product: Product = Depends(get_product), db: Database = Depends(db_session)
) -> ProductSchemeGuidance:
    """Scheme guidance for a product, resolved through its matched standards.

    The chain is product -> matched standard -> QCO / BIS Scheme-I list ->
    scheme. A product with no discovered standards gets an explicit note, not a
    guess from its description.
    """
    payload: Dict[str, Any] = certification.resolve_for_product(db, product)
    return ProductSchemeGuidance(**payload, disclaimer=DISCLAIMER)


# ---------------------------------------------------------------------------
# Certification process guidance
# ---------------------------------------------------------------------------

@router.get(
    "/standards/{standard_id}/certification-process", response_model=ProcessGuidance
)
def process_for_standard(
    standard_id: str, db: Database = Depends(db_session)
) -> ProcessGuidance:
    """The certification journey for one standard, stage by stage.

    Each stage cites a clause from the documents actually held for this
    standard. A stage with no supporting clause is still listed, marked as
    unevidenced - the step is real even where this platform has no source for
    it. A standard with no confirmed scheme gets no process at all.
    """
    return certification_process.resolve_for_standard(db, standard_id)


@router.get(
    "/products/{product_id}/certification-process", response_model=ProcessGuidance
)
def process_for_product(
    product: Product = Depends(get_product), db: Database = Depends(db_session)
) -> ProcessGuidance:
    """The certification journey for a product, via its resolved scheme."""
    return certification_process.resolve_for_product(db, product)
