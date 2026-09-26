"""Seed structured knowledge (requirements, QCOs, amendments, relationships).

Runs after document ingestion, because every record here is attached to a
standard that ingestion created. Idempotent: re-running replaces the records it
owns rather than duplicating them.
"""
from __future__ import annotations

import json
import logging
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

from sqlalchemy.orm import Session

from app.core.config import settings
from app.models import (
    QCO,
    Amendment,
    ComplianceRequirement,
    Standard,
    StandardClause,
    StandardRelationship,
)

logger = logging.getLogger(__name__)


def _load(path: Path) -> Optional[Dict[str, Any]]:
    if not path.exists():
        logger.warning("Seed file missing: %s", path)
        return None
    return json.loads(path.read_text(encoding="utf-8"))


def _date(value: Optional[str]) -> Optional[datetime]:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value)
    except ValueError:
        return None


def seed_requirements(db: Session, directory: Optional[Path] = None) -> int:
    directory = directory or (settings.data_dir / "requirements")
    if not directory.exists():
        logger.warning("Requirements directory missing: %s", directory)
        return 0

    count = 0
    for path in sorted(directory.glob("*.json")):
        payload = _load(path)
        if not payload:
            continue
        standard_id = payload.get("standard_id")
        standard = db.get(Standard, standard_id)
        if standard is None:
            logger.warning("Requirements for unknown standard %s - skipped", standard_id)
            continue

        db.query(ComplianceRequirement).filter(
            ComplianceRequirement.standard_id == standard_id
        ).delete(synchronize_session=False)
        db.flush()

        for item in payload.get("requirements", []):
            clause_number = item.get("clause", "")
            clause = (
                db.query(StandardClause)
                .filter(
                    StandardClause.standard_id == standard_id,
                    StandardClause.clause_number == clause_number,
                )
                .first()
            )
            if clause is None and clause_number:
                # Fall back to the nearest parent clause so a citation always
                # resolves to text that actually exists in the document.
                parent = clause_number.rsplit(".", 1)[0]
                clause = (
                    db.query(StandardClause)
                    .filter(
                        StandardClause.standard_id == standard_id,
                        StandardClause.clause_number == parent,
                    )
                    .first()
                )
            check_rule = dict(item.get("check_rule") or {})
            if item.get("match_keywords"):
                check_rule["match_keywords"] = item["match_keywords"]
            if item.get("official_verification_required"):
                check_rule["official_verification_required"] = True

            db.add(
                ComplianceRequirement(
                    id=f"{standard_id}::{item['requirement_code']}",
                    standard_id=standard_id,
                    clause_id=clause.id if clause else None,
                    requirement_code=item["requirement_code"],
                    category=item.get("category", "safety"),
                    requirement_text=item.get("requirement_text", ""),
                    evidence_type=item.get("evidence_type", "document"),
                    severity=item.get("severity", "major"),
                    check_rule_json=check_rule,
                    applies_when_json=item.get("applies_when") or {},
                    source_clause_number=clause_number,
                )
            )
            count += 1
    db.commit()
    logger.info("Seeded %s compliance requirements", count)
    return count


def seed_regulatory(db: Session, path: Optional[Path] = None) -> int:
    """Load regulatory records from the demo seed and the verified seed.

    Both files are loaded in one pass because the table is cleared first:
    seeding only one of them would silently drop the other's records. Verified
    records are transcribed from official gazette text and carry
    ``is_verified: true``; demo records stay labelled synthetic.
    """
    seed_dir = settings.data_dir / "seed"
    paths = [path] if path is not None else [
        seed_dir / "regulatory.json",
        seed_dir / "regulatory_verified.json",
    ]
    records = []
    for candidate in paths:
        payload = _load(candidate)
        if payload:
            records.extend(payload.get("records", []))
    if not records:
        return 0
    db.query(QCO).delete(synchronize_session=False)
    db.flush()
    count = 0
    for record in records:
        if db.get(Standard, record["standard_id"]) is None:
            logger.warning("QCO for unknown standard %s - skipped", record["standard_id"])
            continue
        db.add(
            QCO(
                id=record["id"],
                standard_id=record["standard_id"],
                product_name=record.get("product_name", ""),
                qco_name=record.get("qco_name", ""),
                notification_number=record.get("notification_number", ""),
                notification_date=_date(record.get("notification_date")),
                effective_date=_date(record.get("effective_date")),
                status=record.get("status", "MANDATORY"),
                scheme=record.get("scheme", ""),
                ministry=record.get("ministry", ""),
                source_url=record.get("source_url") or "",
                document_id=record.get("document_id", ""),
                retrieved_at=_date(record.get("retrieved_at")),
                is_verified=bool(record.get("is_verified", False)),
                is_demo=bool(record.get("is_demo", record.get("is_mock", True))),
                is_mock=bool(record.get("is_mock", True)),
            )
        )
        count += 1
    db.commit()
    logger.info("Seeded %s regulatory records", count)
    return count


def seed_amendments(db: Session, path: Optional[Path] = None) -> int:
    path = path or (settings.data_dir / "seed" / "amendments.json")
    payload = _load(path)
    if not payload:
        return 0
    db.query(Amendment).delete(synchronize_session=False)
    db.flush()
    count = 0
    for record in payload.get("records", []):
        if db.get(Standard, record["standard_id"]) is None:
            continue
        db.add(
            Amendment(
                id=record["id"],
                standard_id=record["standard_id"],
                amendment_number=record.get("amendment_number", ""),
                publication_date=_date(record.get("publication_date")),
                effective_date=_date(record.get("effective_date")),
                affected_clause=record.get("affected_clause", ""),
                summary=record.get("summary", ""),
                old_text=record.get("old_text", ""),
                new_text=record.get("new_text", ""),
                source_url=record.get("source_url") or "",
                document_id=record.get("document_id", ""),
                retrieved_at=_date(record.get("retrieved_at")),
                is_verified=bool(record.get("is_verified", False)),
                is_demo=bool(record.get("is_demo", record.get("is_mock", True))),
                is_mock=bool(record.get("is_mock", True)),
            )
        )
        count += 1
    db.commit()
    logger.info("Seeded %s amendments", count)
    return count


def seed_relationships(db: Session, path: Optional[Path] = None) -> int:
    path = path or (settings.data_dir / "seed" / "relationships.json")
    payload = _load(path)
    if not payload:
        return 0
    db.query(StandardRelationship).delete(synchronize_session=False)
    db.flush()
    count = 0
    for record in payload.get("records", []):
        if db.get(Standard, record["source"]) is None or db.get(Standard, record["target"]) is None:
            continue
        db.add(
            StandardRelationship(
                id=f"rel-{record['source']}-{record['target']}-{record['type']}",
                source_standard_id=record["source"],
                target_standard_id=record["target"],
                relationship_type=record["type"],
                evidence=record.get("evidence", ""),
            )
        )
        count += 1
    db.commit()
    logger.info("Seeded %s standard relationships", count)
    return count


def seed_all(db: Session) -> Dict[str, int]:
    return {
        "requirements": seed_requirements(db),
        "regulatory": seed_regulatory(db),
        "amendments": seed_amendments(db),
        "relationships": seed_relationships(db),
    }
