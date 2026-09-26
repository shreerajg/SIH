#!/usr/bin/env python
"""Register the validated BIS source pack into the project's source manifest.

    python scripts/import_verified_bis_pack.py            # register + report
    python scripts/import_verified_bis_pack.py --dry-run  # show the mapping only

This does not invent a second corpus system: every document goes through
``app.ingestion.manifest.register_document``, the same validated path a
manually registered official document uses. The manifest is what grants
``is_verified``, so a file that is missing, empty, or whose SHA-256 no longer
matches the download validation report is refused here rather than quietly
becoming "official".

What these documents are, and are not: BIS Product Manuals, Quality Control
Orders and gazette notifications are official supporting and regulatory
documents. None of them is the full text of an Indian Standard, and nothing
downstream may present them as such - hence the explicit ``document_type`` on
every entry.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path
from typing import Dict, List

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "backend"))

from app.core.constants import DocumentType, SourceType  # noqa: E402
from app.ingestion.manifest import register_document  # noqa: E402

PACK_DIR = REPO_ROOT / "data" / "raw" / "verified_bis_2026_09_03"
RETRIEVED_ON = "2026-09-03"

#: local_target -> the identity this document takes in the project corpus.
#: ``is_number`` is set only where the document really is *about* one numbered
#: Indian Standard; a QCO covering five standards gets none, because pinning it
#: to a single number would misrepresent it.
MAPPING: Dict[str, Dict[str, str]] = {
    "water_heater/IS_2082_2018_Product_Manual_Sep_2024.pdf": {
        "document_id": "IS-2082-2018-PM",
        "is_number": "IS 2082:2018",
        "title": "Product Manual: Stationary Storage Type Electric Water Heaters (PM/IS 2082/6/September 2024)",
        "document_type": DocumentType.PRODUCT_MANUAL.value,
        "product_category": "electrical-appliance",
        "keywords": [
            "water heater", "storage water heater", "stationary storage", "geyser",
            "electric water heater", "domestic", "is 2082",
        ],
        "covered_areas": [
            "Certification scope", "Sampling guidelines", "Test equipment",
            "Scheme of inspection and testing", "Marking",
        ],
        "notes": (
            "Official BIS Product Manual for IS 2082:2018. Supporting/certification "
            "document - NOT the full text of IS 2082:2018. References IS 302 (Part 2/Sec 21):2024 "
            "/ IEC 60335-2-21:2022."
        ),
    },
    "water_heater/IS_302_Part2_Sec21_2024_Product_Manual_Sep_2024.pdf": {
        "document_id": "IS-302-P2S21-2024-PM",
        "is_number": "IS 302 (Part 2/Sec 21):2024",
        "title": "Product Manual: Household Appliances Safety Part 2 Sec 21 Storage Water Heaters (September 2024)",
        "document_type": DocumentType.PRODUCT_MANUAL.value,
        "product_category": "electrical-appliance",
        "keywords": [
            "water heater", "storage water heater", "household appliance", "electrical safety",
            "electric shock", "insulation", "is 302", "iec 60335",
        ],
        "covered_areas": [
            "Certification scope", "Sampling guidelines", "Test equipment",
            "Scheme of inspection and testing", "Marking",
        ],
        "notes": (
            "Official BIS Product Manual for IS 302 (Part 2/Sec 21):2024 / IEC 60335-2-21:2022. "
            "NOTE the version transition: the Domestic Water Heating QCO 2025 table names the "
            "2018 edition of IS 302 (Part 2/Sec 21), while this current manual covers the 2024 "
            "edition. Not the full standard text."
        ),
    },
    "water_heater/Domestic_Water_Heating_QCO_2025.pdf": {
        "document_id": "QCO-WATER-HEATING-2025",
        "is_number": "",
        "title": "Electrical Appliances for domestic water heating (Quality Control) Order, 2025 - S.O. 355(E)",
        "document_type": DocumentType.QCO.value,
        "product_category": "regulatory-order",
        "keywords": ['quality control order', 'qco', 'water heater', 'domestic water heating', 'mandatory certification', 'isi mark'],
        "covered_areas": ['Compulsory use of Standard Mark', 'Scope of goods covered', 'Implementation dates', 'Enforcement authority'],
        "notes": (
            "Gazette of India, notified 16 January 2025, published 21 January 2025. In "
            "supersession of the 2023 order. Table names IS 302 (Part 2/Sec 21):2018, "
            "IS 302 (Part 2/Sec 35):2017, IS 368:2014, IS 2082:2018 and IS 17150:2019. "
            "Implementation 1 March 2025 (general) and 1 September 2025 (micro and small)."
        ),
    },
    "pressure_cooker/IS_2347_2023_Product_Manual_Feb_2025.pdf": {
        "document_id": "IS-2347-2023-PM",
        "is_number": "IS 2347:2023",
        "title": "Product Manual: Domestic Pressure Cooker (PM/IS 2347/9/February 2025)",
        "document_type": DocumentType.PRODUCT_MANUAL.value,
        "product_category": "kitchenware",
        "keywords": [
            "pressure cooker", "cooker", "domestic", "kitchen", "aluminium",
            "stainless steel", "gasket", "is 2347",
        ],
        "covered_areas": [
            "Certification scope", "Grouping guidelines", "Sampling guidelines",
            "Test equipment", "Scheme of inspection and testing", "Marking",
        ],
        "notes": (
            "Official BIS Product Manual for IS 2347:2023. NOT the full standard text. "
            "Version transition: the 2020 QCO names IS 2347:2017. This pack does not contain "
            "the 2024/2025 amendments to IS 2347:2023 that BIS metadata indicates exist, so "
            "amendment coverage for this standard is incomplete."
        ),
    },
    "pressure_cooker/Domestic_Pressure_Cooker_QCO_2020.pdf": {
        "document_id": "QCO-PRESSURE-COOKER-2020",
        "is_number": "",
        "title": "Domestic Pressure Cooker (Quality Control) Order, 2020 - S.O. 294(E)",
        "document_type": DocumentType.QCO.value,
        "product_category": "regulatory-order",
        "keywords": ['quality control order', 'qco', 'pressure cooker', 'mandatory certification', 'isi mark'],
        "covered_areas": ['Compulsory use of Standard Mark', 'Scope of goods covered', 'Commencement', 'Enforcement authority'],
        "notes": (
            "Gazette of India, notified 21 January 2020, in force from 1 August 2020. Its table "
            "names IS 2347:2017; the order states the latest BIS-notified version and amendments "
            "apply, and the current Product Manual is for IS 2347:2023."
        ),
    },
    "pressure_cooker/Domestic_Pressure_Cooker_QCO_Amendment_2020.pdf": {
        "document_id": "QCO-PRESSURE-COOKER-2020-AMD",
        "is_number": "",
        "title": "Domestic Pressure Cooker (Quality Control) (Amendment) Order, 2020 - S.O. 2019(E)",
        "document_type": DocumentType.QCO.value,
        "product_category": "regulatory-order",
        "keywords": ['quality control order', 'amendment', 'pressure cooker', 'commencement'],
        "covered_areas": ['Amendment to commencement date'],
        "notes": "Gazette of India, 23 June 2020. Amends the commencement of the 2020 QCO.",
    },
    "helmet/IS_4151_2015_Product_Manual_Dec_2024.pdf": {
        "document_id": "IS-4151-2015-PM",
        "is_number": "IS 4151:2015",
        "title": "Product Manual: Protective Helmet for Two Wheeler Riders (PM/IS 4151/3/December 2024)",
        "document_type": DocumentType.PRODUCT_MANUAL.value,
        "product_category": "personal-protective-equipment",
        "keywords": [
            "helmet", "protective helmet", "two wheeler", "motorcycle", "scooter",
            "rider", "chin strap", "retention system", "visor", "is 4151",
        ],
        "covered_areas": [
            "Certification scope", "Sampling guidelines", "Test equipment",
            "Scheme of inspection and testing", "Marking",
        ],
        "notes": (
            "Official BIS Product Manual for IS 4151:2015. NOT the full standard text. "
            "No version conflict: the 2020 Helmet QCO names the same edition."
        ),
    },
    "helmet/Helmet_Two_Wheeler_QCO_2020.pdf": {
        "document_id": "QCO-HELMET-2020",
        "is_number": "",
        "title": "Helmet for riders of Two Wheeler Motor Vehicles (Quality Control) Order, 2020 - S.O. 4252(E)",
        "document_type": DocumentType.QCO.value,
        "product_category": "regulatory-order",
        "keywords": ['quality control order', 'qco', 'helmet', 'two wheeler', 'mandatory certification', 'isi mark'],
        "covered_areas": ['Compulsory use of Standard Mark', 'Scope of goods covered', 'Commencement', 'Enforcement authority'],
        "notes": (
            "Gazette of India, notified 26 November 2020, in force from 1 June 2021. Ministry of "
            "Road Transport and Highways. Table names IS 4151:2015."
        ),
    },
    "regulatory/Transition_Facilitation_QCO_2026.pdf": {
        "document_id": "QCO-TRANSITION-FACILITATION-2026",
        "is_number": "",
        "title": "Transition Facilitation (Quality Control) Order, 2026 - S.O. 3417(E)",
        "document_type": DocumentType.REGULATORY.value,
        "product_category": "regulatory-order",
        "keywords": ['transition facilitation', 'quality control order', 'toys', 'water heating', 'transition'],
        "covered_areas": ['Transition facilitation mechanism', 'Schedule of affected orders'],
        "notes": (
            "Gazette of India, 2026. A transition facilitation mechanism affecting the schedule "
            "that includes the Toys QCO 2020 and the domestic water heating QCO 2025. It must "
            "NOT be read as a blanket cancellation or postponement of those orders."
        ),
    },
    "regulatory/BIS_Current_Scheme_I_Compulsory_Certification.html": {
        "document_id": "BIS-SCHEME-I-INDEX",
        "is_number": "",
        "title": "BIS Scheme-I: Products under Compulsory Certification (current index page)",
        "document_type": DocumentType.REGULATORY.value,
        "product_category": "regulatory-order",
        "keywords": ['scheme-i', 'compulsory certification', 'products under compulsory certification', 'bis index'],
        "covered_areas": ['Current index of products under compulsory certification'],
        "notes": (
            "Provenance record only. This is a BIS web index page, not a clause-structured "
            "document; the ingestion parser accepts .pdf/.txt/.md, so it is registered as a "
            "source reference and is never parsed into clauses."
        ),
    },
}


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    report_path = PACK_DIR / "download_validation_report.json"
    if not report_path.exists():
        print(f"ERROR: no validation report at {report_path}. Run the pack's "
              f"download_and_validate_verified_bis_corpus.ps1 first.")
        return 2

    # PowerShell writes UTF-8 with a BOM.
    report = json.loads(report_path.read_text(encoding="utf-8-sig"))
    failed = [r for r in report if r.get("status") != "OK"]
    if failed:
        print(f"ERROR: {len(failed)} source(s) failed download validation. Nothing registered.")
        for row in failed:
            print(f"  FAILED {row.get('target')}: {row.get('error')}")
        return 2

    by_target = {r["target"].replace("\\", "/"): r for r in report}
    registered: List[str] = []
    problems: List[str] = []

    for target, spec in MAPPING.items():
        row = by_target.get(target)
        if row is None:
            problems.append(f"{target}: not present in the validation report")
            continue

        local = PACK_DIR / target
        if not local.exists() or local.stat().st_size == 0:
            problems.append(f"{target}: file missing or empty on disk")
            continue

        actual = sha256(local)
        if actual != row["sha256"]:
            problems.append(
                f"{target}: SHA-256 mismatch - file changed since validation "
                f"(report {row['sha256'][:16]}..., disk {actual[:16]}...)"
            )
            continue

        relative = local.relative_to(REPO_ROOT).as_posix()
        if args.dry_run:
            print(f"WOULD REGISTER {spec['document_id']:34} {spec['document_type']:16} {target}")
            registered.append(spec["document_id"])
            continue

        register_document(
            document_id=spec["document_id"],
            title=spec["title"],
            is_number=spec["is_number"],
            local_path=relative,
            source_url=row["url"],
            document_type=spec["document_type"],
            retrieved_at=RETRIEVED_ON,
            source_type=SourceType.OFFICIAL.value,
            notes=spec["notes"],
            product_category=spec.get("product_category", ""),
            keywords=spec.get("keywords", []),
            covered_areas=spec.get("covered_areas", []),
        )
        print(f"registered {spec['document_id']:34} {spec['document_type']:16} {target}")
        registered.append(spec["document_id"])

    print()
    print(f"{'Would register' if args.dry_run else 'Registered'}: {len(registered)} document(s)")
    if problems:
        print(f"Refused: {len(problems)}")
        for problem in problems:
            print(f"  {problem}")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
