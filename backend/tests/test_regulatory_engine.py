"""The regulatory / QCO engine.

The whole point of this subsystem is that a legal status is never an inference.
It is either read from a stored record, or reported as unverifiable.
"""
from __future__ import annotations

from datetime import datetime, timedelta

import pytest

from app.core.constants import RegulatoryStatus
from app.models import QCO
from app.services.regulatory import (
    _effective_status,
    regulatory_history,
    regulatory_overview,
    resolve_regulatory_status,
)


def _record(**kwargs) -> QCO:
    defaults = dict(
        id="tmp", standard_id="DEMO-STD-001", product_name="p", qco_name="q",
        notification_number="N/1", notification_date=datetime(2024, 1, 1),
        effective_date=datetime(2024, 6, 1), status="MANDATORY", scheme="Scheme I",
        ministry="m", source_url="", is_verified=False, is_demo=True, is_mock=True,
    )
    defaults.update(kwargs)
    return QCO(**defaults)


# ---------------------------------------------------------------------------
# The core rule: absence is not evidence
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("standard_id", ["DEMO-STD-002", "DEMO-STD-003", "DEMO-STD-006"])
def test_no_record_returns_unable_to_verify_never_voluntary(db, standard_id):
    status = resolve_regulatory_status(db, standard_id)
    assert status.status is RegulatoryStatus.UNABLE_TO_VERIFY
    assert status.status is not RegulatoryStatus.VOLUNTARY
    assert status.evidence is None
    assert "does not mean the standard is voluntary" in status.message.lower()


def test_unknown_standard_is_unable_to_verify(db):
    assert (
        resolve_regulatory_status(db, "NOT-A-STANDARD").status
        is RegulatoryStatus.UNABLE_TO_VERIFY
    )


def test_voluntary_requires_an_explicit_record():
    """VOLUNTARY must be reachable only from a record that says so."""
    assert _effective_status(_record(status="VOLUNTARY")) is RegulatoryStatus.VOLUNTARY
    # And nothing else produces it.
    for status in ("MANDATORY", "WITHDRAWN", "nonsense"):
        assert _effective_status(_record(status=status)) is not RegulatoryStatus.VOLUNTARY


# ---------------------------------------------------------------------------
# Effective-date interpretation
# ---------------------------------------------------------------------------

def test_a_future_effective_date_is_upcoming_not_mandatory():
    future = datetime.utcnow() + timedelta(days=200)
    assert _effective_status(_record(effective_date=future)) is RegulatoryStatus.UPCOMING


def test_a_past_effective_date_is_mandatory():
    past = datetime.utcnow() - timedelta(days=200)
    assert _effective_status(_record(effective_date=past)) is RegulatoryStatus.MANDATORY


def test_withdrawn_stays_withdrawn_regardless_of_dates():
    future = datetime.utcnow() + timedelta(days=200)
    assert (
        _effective_status(_record(status="WITHDRAWN", effective_date=future))
        is RegulatoryStatus.WITHDRAWN
    )


def test_an_unreadable_status_is_unable_to_verify():
    assert _effective_status(_record(status="???")) is RegulatoryStatus.UNABLE_TO_VERIFY


def test_upcoming_is_surfaced_with_its_date(db):
    """DEMO-STD-007 carries a notified order that is not yet in force."""
    status = resolve_regulatory_status(db, "DEMO-STD-007")
    assert status.status is RegulatoryStatus.UPCOMING
    assert status.effective_date, "an upcoming order must state when it starts"
    assert "not yet taken effect" in status.message
    assert status.evidence is not None
    assert status.evidence.declared_status == "MANDATORY"
    assert status.evidence.effective_status == "UPCOMING"


# ---------------------------------------------------------------------------
# Evidence exposure
# ---------------------------------------------------------------------------

def test_a_status_always_carries_the_record_behind_it(db):
    status = resolve_regulatory_status(db, "DEMO-STD-001")
    assert status.status is RegulatoryStatus.MANDATORY
    assert status.evidence is not None
    assert status.evidence.notification_number
    assert status.evidence.scheme
    assert status.evidence.is_demo is True
    assert status.scheme


def test_demo_records_say_so_in_the_message(db):
    status = resolve_regulatory_status(db, "DEMO-STD-001")
    assert "demonstration dataset" in status.message
    assert status.is_mock is True
    assert status.verified is False


def test_history_returns_every_record_newest_first(db):
    history = regulatory_history(db, "DEMO-STD-007")
    assert len(history) == 2, "the helmet standard has an order and an amending order"
    assert history[0].effective_status == "UPCOMING"
    assert history[1].effective_status == "MANDATORY"


def test_overview_counts_are_real(db):
    overview = regulatory_overview(db)
    # The total varies with what other tests have ingested into the shared
    # session database, so the invariants are asserted rather than a fixed
    # count: the split must always add up, and only 4 shipped standards carry
    # a regulatory record.
    assert overview["standards"] >= 8
    assert overview["standards_with_regulatory_record"] == 4
    assert (
        overview["standards_with_regulatory_record"]
        + overview["standards_without_regulatory_record"]
        == overview["standards"]
    )
    assert overview["verified_regulatory_records"] == 0, "no official record ships"
    assert "never treated as evidence" in overview["note"]


# ---------------------------------------------------------------------------
# API surface
# ---------------------------------------------------------------------------

def test_regulatory_endpoint_exposes_status_and_history(client):
    body = client.get("/api/standards/DEMO-STD-007/regulatory").json()
    assert body["status"]["status"] == "UPCOMING"
    assert len(body["history"]) == 2
    assert body["history"][0]["notification_number"]
    assert "never as voluntary" in body["note"]


def test_regulatory_endpoint_for_a_standard_without_a_record(client):
    body = client.get("/api/standards/DEMO-STD-002/regulatory").json()
    assert body["status"]["status"] == "UNABLE_TO_VERIFY"
    assert body["history"] == []


def test_regulatory_endpoint_404s_for_an_unknown_standard(client):
    assert client.get("/api/standards/NOPE/regulatory").status_code == 404
