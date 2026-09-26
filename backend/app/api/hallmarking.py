"""BIS hallmarking guidance endpoints.

Read-only. Every fact returned is resolved to a clause in the official BIS
hallmarking documents ingested into this corpus; anything that cannot be is
returned with ``state: UNABLE_TO_VERIFY`` rather than omitted or asserted.

Note what is deliberately absent: there is no endpoint that validates a HUID or
reports a jeweller as registered. ``/hallmarking/huid/describe`` describes a
code against the documented format and always returns
``checked_against_bis: false``.
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, Query
from pymongo.database import Database

from app.api.deps import db_session
from app.schemas.models import (
    CentreDirectorySummary,
    CentreSearchResponse,
    ConsumerHallmarkGuide,
    HallmarkComponent,
    HallmarkingOverview,
    HuidGuidance,
    JewellerHallmarkGuide,
    PurityGrade,
)
from app.services import hallmarking

router = APIRouter(tags=["hallmarking"])


@router.get("/hallmarking/overview", response_model=HallmarkingOverview)
def get_overview(db: Database = Depends(db_session)) -> HallmarkingOverview:
    """What the BIS hallmarking scheme is, cited to the BIS source."""
    return hallmarking.overview(db)


@router.get("/hallmarking/purity-grades", response_model=List[PurityGrade])
def get_purity_grades(
    material: Optional[str] = Query(default=None, description="gold | silver"),
    db: Database = Depends(db_session),
) -> List[PurityGrade]:
    """Permitted purity / fineness grades.

    Values come from stored records transcribed from BIS documents; each one
    carries the clause that states it. No grade is computed or inferred.
    """
    return hallmarking.purity_grades(db, material)


@router.get("/hallmarking/components", response_model=List[HallmarkComponent])
def get_components(
    material: str = Query(default="gold"),
    db: Database = Depends(db_session),
) -> List[HallmarkComponent]:
    """The marks a hallmarked article carries."""
    return hallmarking.hallmark_components(db, material)


@router.get("/hallmarking/huid", response_model=HuidGuidance)
def get_huid(db: Database = Depends(db_session)) -> HuidGuidance:
    """What a HUID is, and an explicit statement that nothing is verified here."""
    return hallmarking.huid_guidance(db)


@router.get("/hallmarking/huid/describe")
def describe_huid(
    code: str = Query(..., description="A HUID to describe against the documented format"),
    db: Database = Depends(db_session),
) -> Dict[str, Any]:
    """Describe a code against the documented HUID format.

    This is **not** verification. ``checked_against_bis`` is always false and
    ``state`` is always UNABLE_TO_VERIFY: the platform is not connected to the
    BIS HUID service, so it cannot and does not say whether a code is genuine.
    """
    return hallmarking.describe_huid_format(db, code)


@router.get("/hallmarking/consumer-guide", response_model=ConsumerHallmarkGuide)
def get_consumer_guide(
    material: str = Query(default="gold"),
    db: Database = Depends(db_session),
) -> ConsumerHallmarkGuide:
    """What a buyer should check, with the BIS clause behind each point."""
    return hallmarking.consumer_guide(db, material)


@router.get("/hallmarking/jeweller-guide", response_model=JewellerHallmarkGuide)
def get_jeweller_guide(db: Database = Depends(db_session)) -> JewellerHallmarkGuide:
    """The hallmarking journey for a jeweller, stage by stage."""
    return hallmarking.jeweller_guide(db)


@router.get("/hallmarking/centres", response_model=CentreSearchResponse)
def get_centres(
    state: Optional[str] = Query(default=None),
    city: Optional[str] = Query(default=None),
    operative_only: bool = Query(default=False),
    limit: int = Query(default=50, le=200),
    db: Database = Depends(db_session),
) -> CentreSearchResponse:
    """Search the local snapshot of BIS recognised A&H Centres.

    The snapshot's retrieval date is always returned. A centre absent from it is
    reported as absent from the snapshot, never as unrecognised, and centres
    under suspension are returned with that status rather than filtered out.
    """
    return hallmarking.search_centres(
        db, state=state, city=city, operative_only=operative_only, limit=limit
    )


@router.get("/hallmarking/centres/summary", response_model=CentreDirectorySummary)
def get_centre_summary(db: Database = Depends(db_session)) -> CentreDirectorySummary:
    return hallmarking.centre_summary(db)
