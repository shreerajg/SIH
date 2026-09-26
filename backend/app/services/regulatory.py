"""Regulatory status resolution.

This module is the ONLY source of mandatory/voluntary answers in the platform.
It reads the structured QCO table and nothing else - no model is consulted, and
no model output can override it.

Two rules do most of the work:

1. **Absence is not evidence.** No record returns ``UNABLE_TO_VERIFY``, never
   ``VOLUNTARY``. The platform not holding a Quality Control Order says
   something about the platform, not about the law.
2. **A future effective date is not "mandatory yet".** A notified order whose
   effective date has not arrived is reported as ``UPCOMING``, with the date, so
   a manufacturer can see the deadline instead of being told they are already
   in breach.

``VOLUNTARY`` is reachable only from an explicit stored record that says so.
"""
from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, List, Optional

from pymongo import DESCENDING
from pymongo.database import Database

from app.core.constants import RegulatoryStatus
from app.db.repositories import qcos as qcos_repo
from app.db.repositories import standards as standards_repo
from app.models import QCO
from app.schemas.models import RegulatoryEvidence, RegulatoryStatusInfo

UNVERIFIED_MESSAGE = (
    "No verified regulatory record for this standard is present in the current "
    "dataset. This does NOT mean the standard is voluntary - it means the "
    "platform cannot verify its regulatory status. Confirm with the official "
    "BIS / notifying ministry source."
)

DEMO_SUFFIX = (
    " This regulatory record is part of the labelled demonstration dataset and "
    "is not an official notification."
)


def _fmt(value: Optional[datetime]) -> Optional[str]:
    return value.date().isoformat() if value else None


def _effective_status(record: QCO, now: Optional[datetime] = None) -> RegulatoryStatus:
    """Interpret the stored status against today's date.

    A record can say MANDATORY while its effective date is still in the future;
    reporting that flatly as "mandatory" would be misleading, so it becomes
    UPCOMING until the date passes.
    """
    now = now or datetime.utcnow()
    try:
        declared = RegulatoryStatus(record.status)
    except ValueError:
        return RegulatoryStatus.UNABLE_TO_VERIFY

    if declared is RegulatoryStatus.WITHDRAWN:
        return declared
    if declared is RegulatoryStatus.MANDATORY and record.effective_date:
        if record.effective_date > now:
            return RegulatoryStatus.UPCOMING
    return declared


def _message(record: QCO, status: RegulatoryStatus) -> str:
    if status is RegulatoryStatus.UPCOMING:
        message = (
            "This standard is covered by a notified Quality Control Order that has "
            f"not yet taken effect. It becomes applicable on {_fmt(record.effective_date)}."
        )
    elif status is RegulatoryStatus.WITHDRAWN:
        message = (
            "The Quality Control Order recorded for this standard has been withdrawn. "
            "Confirm the current position with the notifying ministry."
        )
    elif status is RegulatoryStatus.VOLUNTARY:
        message = (
            "A stored regulatory record explicitly states that conformity to this "
            "standard is voluntary."
        )
    else:
        message = "Regulatory status taken from a structured Quality Control Order record."

    if record.is_demo or record.is_mock or not record.is_verified:
        message += DEMO_SUFFIX
    return message


def _evidence(record: QCO, status: RegulatoryStatus) -> RegulatoryEvidence:
    return RegulatoryEvidence(
        qco_name=record.qco_name or None,
        notification_number=record.notification_number or None,
        notification_date=_fmt(record.notification_date),
        effective_date=_fmt(record.effective_date),
        declared_status=record.status,
        effective_status=status.value,
        scheme=record.scheme or None,
        ministry=record.ministry or None,
        source_url=record.source_url or None,
        document_id=record.document_id or None,
        retrieved_at=_fmt(record.retrieved_at),
        is_verified=bool(record.is_verified),
        is_demo=bool(record.is_demo),
        product_name=record.product_name or None,
    )


def _unable_to_verify(message: str = UNVERIFIED_MESSAGE) -> RegulatoryStatusInfo:
    return RegulatoryStatusInfo(
        status=RegulatoryStatus.UNABLE_TO_VERIFY,
        verified=False,
        source=None,
        is_mock=True,
        message=message,
    )


def resolve_regulatory_status(db: Database, standard_id: str) -> RegulatoryStatusInfo:
    """Return the regulatory position for a standard, strictly from the DB."""
    # Newest effective date first. BSON orders null below every date, so a
    # single descending sort puts undated records last - the behaviour the SQL
    # version had to spell out with an explicit "is null" sort key.
    records = qcos_repo(db).find(
        {"standard_id": standard_id}, sort=[("effective_date", DESCENDING)], limit=1
    )
    record: Optional[QCO] = records[0] if records else None
    if record is None:
        return _unable_to_verify()

    status = _effective_status(record)
    return RegulatoryStatusInfo(
        status=status,
        verified=bool(record.is_verified),
        source="QCO record",
        qco_name=record.qco_name or None,
        notification_number=record.notification_number or None,
        notification_date=_fmt(record.notification_date),
        effective_date=_fmt(record.effective_date),
        ministry=record.ministry or None,
        scheme=record.scheme or None,
        source_url=record.source_url or None,
        is_mock=bool(record.is_demo or record.is_mock),
        message=_message(record, status),
        evidence=_evidence(record, status),
    )


def resolve_for_is_number(db: Database, normalized_number: str) -> RegulatoryStatusInfo:
    standard = standards_repo(db).find_one({"normalized_number": normalized_number})
    if standard is None:
        return _unable_to_verify()
    return resolve_regulatory_status(db, standard.id)


def regulatory_history(db: Database, standard_id: str) -> List[RegulatoryEvidence]:
    """Every stored record for a standard, newest first.

    A standard can accumulate more than one order over time (a notification, an
    amendment to it, a withdrawal). The full list is exposed so the user can see
    the chain rather than only the most recent entry.
    """
    records = qcos_repo(db).find(
        {"standard_id": standard_id}, sort=[("effective_date", DESCENDING)]
    )
    return [_evidence(record, _effective_status(record)) for record in records]


def regulatory_overview(db: Database) -> Dict[str, Any]:
    """Corpus-level regulatory picture for the trust page."""
    repo = qcos_repo(db)
    total = standards_repo(db).count()
    # Replaces SELECT COUNT(DISTINCT standard_id) FROM qcos.
    with_record = len(repo.distinct("standard_id"))
    verified = repo.count({"is_verified": True})
    by_status: Dict[str, int] = {}
    all_records = repo.find()
    for record in all_records:
        status = _effective_status(record).value
        by_status[status] = by_status.get(status, 0) + 1
    return {
        "standards": total,
        "standards_with_regulatory_record": with_record,
        "standards_without_regulatory_record": total - with_record,
        "verified_regulatory_records": verified,
        "demo_regulatory_records": len(all_records) - verified,
        "by_effective_status": by_status,
        "note": (
            "Standards without a record are reported as UNABLE_TO_VERIFY. "
            "Absence of a stored order is never treated as evidence that a "
            "standard is voluntary."
        ),
    }
