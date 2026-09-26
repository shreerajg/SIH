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

from pymongo.database import Database

from app.core.config import settings
from app.db.repositories import amendments as amendments_repo
from app.db.repositories import hallmarking as hallmarking_repo
from app.db.repositories import hallmarking_centres as hallmarking_centres_repo
from app.db.repositories import processes as processes_repo
from app.db.repositories import scheme_products as scheme_products_repo
from app.db.repositories import schemes as schemes_repo
from app.db.repositories import clauses as clauses_repo
from app.db.repositories import qcos as qcos_repo
from app.db.repositories import relationships as relationships_repo
from app.db.repositories import requirements as requirements_repo
from app.db.repositories import standards as standards_repo
from app.models import (
    CertificationProcess,
    HallmarkingCentre,
    HallmarkingKnowledge,
    CertificationScheme,
    SchemeProductEntry,
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


def seed_requirements(db: Database, directory: Optional[Path] = None) -> int:
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
        standard = standards_repo(db).get(standard_id)
        if standard is None:
            logger.warning("Requirements for unknown standard %s - skipped", standard_id)
            continue

        requirements_repo(db).delete_many({"standard_id": standard_id})
        pending: List[ComplianceRequirement] = []

        for item in payload.get("requirements", []):
            clause_number = item.get("clause", "")
            clause = clauses_repo(db).find_one(
                {"standard_id": standard_id, "clause_number": clause_number}
            )
            if clause is None and clause_number:
                # Fall back to the nearest parent clause so a citation always
                # resolves to text that actually exists in the document.
                parent = clause_number.rsplit(".", 1)[0]
                clause = clauses_repo(db).find_one(
                    {"standard_id": standard_id, "clause_number": parent}
                )
            check_rule = dict(item.get("check_rule") or {})
            if item.get("match_keywords"):
                check_rule["match_keywords"] = item["match_keywords"]
            if item.get("official_verification_required"):
                check_rule["official_verification_required"] = True

            pending.append(
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
        requirements_repo(db).save_many(pending)
    logger.info("Seeded %s compliance requirements", count)
    return count


def seed_regulatory(db: Database, path: Optional[Path] = None) -> int:
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
    qcos_repo(db).delete_many({})
    standards = standards_repo(db)
    pending: List[QCO] = []
    count = 0
    for record in records:
        if not standards.exists(record["standard_id"]):
            logger.warning("QCO for unknown standard %s - skipped", record["standard_id"])
            continue
        pending.append(
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
    qcos_repo(db).save_many(pending)
    logger.info("Seeded %s regulatory records", count)
    return count


def seed_amendments(db: Database, path: Optional[Path] = None) -> int:
    path = path or (settings.data_dir / "seed" / "amendments.json")
    payload = _load(path)
    if not payload:
        return 0
    amendments_repo(db).delete_many({})
    standards = standards_repo(db)
    pending: List[Amendment] = []
    count = 0
    for record in payload.get("records", []):
        if not standards.exists(record["standard_id"]):
            continue
        pending.append(
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
    amendments_repo(db).save_many(pending)
    logger.info("Seeded %s amendments", count)
    return count


def seed_relationships(db: Database, path: Optional[Path] = None) -> int:
    path = path or (settings.data_dir / "seed" / "relationships.json")
    payload = _load(path)
    if not payload:
        return 0
    relationships_repo(db).delete_many({})
    standards = standards_repo(db)
    pending: List[StandardRelationship] = []
    count = 0
    for record in payload.get("records", []):
        if not standards.exists(record["source"]) or not standards.exists(record["target"]):
            continue
        pending.append(
            StandardRelationship(
                id=f"rel-{record['source']}-{record['target']}-{record['type']}",
                source_standard_id=record["source"],
                target_standard_id=record["target"],
                relationship_type=record["type"],
                evidence=record.get("evidence", ""),
            )
        )
        count += 1
    relationships_repo(db).save_many(pending)
    logger.info("Seeded %s standard relationships", count)
    return count


def seed_certification_schemes(db: Database, path: Optional[Path] = None) -> int:
    """Load the BIS certification scheme registry.

    Descriptive content only. Which scheme *applies* to a product is never read
    from here - that is resolved at query time from stored QCO records and the
    extracted BIS Scheme-I product list.
    """
    path = path or (settings.data_dir / "seed" / "certification_schemes.json")
    payload = _load(path)
    records = (payload or {}).get("schemes", [])
    if not records:
        logger.warning("No certification schemes to seed (%s)", path)
        return 0

    schemes_repo(db).delete_many({})
    pending: List[CertificationScheme] = []
    for record in records:
        pending.append(
            CertificationScheme(
                id=record["id"],
                code=record.get("code", ""),
                name=record.get("name", ""),
                aliases=[a.lower() for a in record.get("aliases", [])],
                mark=record.get("mark", ""),
                purpose=record.get("purpose", ""),
                applies_to=record.get("applies_to", ""),
                product_applicability=record.get("product_applicability", ""),
                legal_basis=record.get("legal_basis", ""),
                testing_requirement=record.get("testing_requirement", ""),
                key_documents=list(record.get("key_documents") or []),
                process_url=record.get("process_url", ""),
                source_url=record.get("source_url", ""),
                document_id=record.get("document_id", ""),
                retrieved_at=record.get("retrieved_at"),
                is_verified=bool(record.get("is_verified")),
                is_demo=bool(record.get("is_demo", False)),
                field_sources=dict(record.get("field_sources") or {}),
            )
        )
    schemes_repo(db).save_many(pending)
    logger.info("Seeded %s certification schemes", len(pending))
    return len(pending)


def seed_scheme_product_index(db: Database, path: Optional[Path] = None) -> int:
    """Load the official BIS Scheme-I product list.

    This is the applicability oracle: a standard appearing here is evidence
    that it is covered by Scheme-I. Generated by
    ``scripts/extract_scheme_index.py`` from the manifest-registered BIS page,
    so it is absent until that has been run - which is not an error, it just
    means scheme applicability degrades to "unable to verify".
    """
    path = path or (settings.data_dir / "seed" / "certification_scheme_index.json")
    payload = _load(path)
    entries = (payload or {}).get("entries", [])
    if not entries:
        logger.info(
            "No Scheme-I product index at %s - run scripts/extract_scheme_index.py to "
            "build it. Scheme applicability will report 'unable to verify' until then.",
            path,
        )
        return 0

    scheme_products_repo(db).delete_many({})
    pending: List[SchemeProductEntry] = []
    for index, entry in enumerate(entries):
        normalized = entry.get("normalized_number", "")
        if not normalized:
            continue
        pending.append(
            SchemeProductEntry(
                id=f"{entry.get('scheme_id', 'SCHEME-I')}::{normalized}::{index}",
                scheme_id=entry.get("scheme_id", "SCHEME-I"),
                is_number=entry.get("is_number", ""),
                normalized_number=normalized,
                product=entry.get("product", ""),
                product_group=entry.get("product_group", ""),
                notification=entry.get("notification", ""),
                source_url=payload.get("source_url", ""),
                document_id=payload.get("document_id", ""),
                retrieved_at=payload.get("retrieved_at"),
                is_verified=bool(payload.get("is_verified")),
            )
        )
    scheme_products_repo(db).save_many(pending)
    logger.info("Seeded %s Scheme-I product entries", len(pending))
    return len(pending)


def seed_certification_processes(db: Database, path: Optional[Path] = None) -> int:
    """Load the certification process stage templates.

    Templates only: no clause text is stored here. The evidence supporting each
    stage is resolved against the corpus at query time by
    ``services/certification_process.py``.
    """
    path = path or (settings.data_dir / "seed" / "certification_process.json")
    payload = _load(path)
    records = (payload or {}).get("processes", [])
    if not records:
        logger.warning("No certification processes to seed (%s)", path)
        return 0

    processes_repo(db).delete_many({})
    pending: List[CertificationProcess] = []
    for record in records:
        pending.append(
            CertificationProcess(
                id=f"process::{record['scheme_id']}",
                scheme_id=record["scheme_id"],
                title=record.get("title", ""),
                summary=record.get("summary", ""),
                process_url=record.get("process_url", ""),
                stages=list(record.get("stages") or []),
            )
        )
    processes_repo(db).save_many(pending)
    logger.info("Seeded %s certification process template(s)", len(pending))
    return len(pending)


def seed_hallmarking(db: Database, path: Optional[Path] = None) -> int:
    """Load the structured BIS hallmarking knowledge.

    Facts only - no clause text. Each record keeps the keywords that let the
    service resolve its citation against the ingested BIS hallmarking documents
    at query time, so evidence is always live corpus text.
    """
    path = path or (settings.data_dir / "seed" / "hallmarking.json")
    payload = _load(path)
    if not payload:
        logger.warning("No hallmarking knowledge to seed (%s)", path)
        return 0

    hallmarking_repo(db).delete_many({})
    pending: List[HallmarkingKnowledge] = []

    def add(kind: str, record: Dict[str, Any], order: int) -> None:
        payload_fields = {
            k: v
            for k, v in record.items()
            if k not in ("id", "clause_keywords", "source_document_id", "prefer_document_ids")
        }
        pending.append(
            HallmarkingKnowledge(
                id=f"{kind}::{record.get('id', order)}",
                kind=kind,
                order=int(record.get("order", order)),
                payload=payload_fields,
                clause_keywords=list(record.get("clause_keywords") or []),
                source_document_id=record.get("source_document_id", ""),
                prefer_document_ids=list(record.get("prefer_document_ids") or []),
            )
        )

    scheme = payload.get("scheme")
    if scheme:
        add("scheme", scheme, 0)
    huid = payload.get("huid")
    if huid:
        add("huid", {**huid, "id": "HUID"}, 0)
    for index, record in enumerate(payload.get("purity_grades", [])):
        add("purity_grade", record, index)
    for index, record in enumerate(payload.get("hallmark_components", [])):
        add("hallmark_component", record, index)
    for index, record in enumerate(payload.get("consumer_checks", [])):
        add("consumer_check", record, index)
    for index, record in enumerate(payload.get("process_stages", [])):
        add("process_stage", record, index)

    hallmarking_repo(db).save_many(pending)
    logger.info("Seeded %s hallmarking knowledge record(s)", len(pending))
    return len(pending)


def seed_hallmarking_centres(db: Database, path: Optional[Path] = None) -> int:
    """Load the BIS directory of Assaying & Hallmarking Centres.

    Built by ``scripts/extract_ahc_directory.py`` from the list BIS publishes.
    Absent until that has been run, which is not an error - the API then
    reports that no verified directory is available rather than inventing one.
    """
    path = path or (settings.data_dir / "seed" / "hallmarking_centres.json")
    payload = _load(path)
    centres = (payload or {}).get("centres", [])
    if not centres:
        logger.info(
            "No A&H centre directory at %s - run scripts/extract_ahc_directory.py to build it.",
            path,
        )
        return 0

    hallmarking_centres_repo(db).delete_many({})
    pending: List[HallmarkingCentre] = []
    for index, record in enumerate(centres):
        recognition = (record.get("recognition_number") or "").strip()
        if not recognition:
            continue
        pending.append(
            HallmarkingCentre(
                id=f"ahc::{recognition}::{index}",
                recognition_number=recognition,
                name=record.get("name") or "",
                address=record.get("address") or "",
                city=record.get("city") or "",
                state=record.get("state") or "",
                pin=record.get("pin") or "",
                scope=record.get("scope") or "",
                status=record.get("status") or "",
                validity=record.get("validity"),
                phone=record.get("phone"),
                email=record.get("email"),
                source_url=payload.get("source_url", ""),
                document_id=payload.get("document_id", ""),
                retrieved_at=payload.get("retrieved_at"),
                is_verified=bool(payload.get("is_verified")),
            )
        )
    hallmarking_centres_repo(db).save_many(pending)
    logger.info("Seeded %s Assaying & Hallmarking Centre(s)", len(pending))
    return len(pending)


def seed_all(db: Database) -> Dict[str, int]:
    return {
        "requirements": seed_requirements(db),
        "regulatory": seed_regulatory(db),
        "amendments": seed_amendments(db),
        "relationships": seed_relationships(db),
        "certification_schemes": seed_certification_schemes(db),
        "scheme_product_index": seed_scheme_product_index(db),
        "certification_processes": seed_certification_processes(db),
        "hallmarking": seed_hallmarking(db),
        "hallmarking_centres": seed_hallmarking_centres(db),
    }
