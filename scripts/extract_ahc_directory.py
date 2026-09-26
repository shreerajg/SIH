"""Extract the BIS directory of Assaying & Hallmarking Centres.

Source: the recognised-centre list published on the BIS HUID portal
(``huid.manakonline.in/MANAK/AHCListForWebsite``), downloaded by
``scripts/fetch_hallmarking_sources.py``.

Each row carries its own recognition number, validity date and operative
status, so a centre shown to a user is one BIS actually lists. Centres are
never inferred, and a row that cannot be parsed is dropped rather than
half-filled.

Output: ``data/seed/hallmarking_centres.json``

Usage::

    python scripts/extract_ahc_directory.py
    python scripts/extract_ahc_directory.py --dry-run
"""
from __future__ import annotations

import argparse
import html
import json
import logging
import re
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

REPO_ROOT = Path(__file__).resolve().parents[1]
SOURCE = REPO_ROOT / "data" / "raw" / "verified_bis_hallmarking" / "BIS_AHC_List.html"
REPORT = REPO_ROOT / "data" / "raw" / "verified_bis_hallmarking" / "download_validation_report.json"
OUT = REPO_ROOT / "data" / "seed" / "hallmarking_centres.json"

logging.basicConfig(level=logging.INFO, format="%(levelname)-7s %(message)s")
log = logging.getLogger("ahc-directory")

_TAG = re.compile(r"<[^>]+>")
_WS = re.compile(r"\s+")

#: Indian states and union territories, used only to split the address tail.
#: Matching is on the directory's own text - nothing is looked up elsewhere.
STATES = [
    "ANDHRA PRADESH", "ARUNACHAL PRADESH", "ASSAM", "BIHAR", "CHHATTISGARH", "GOA",
    "GUJARAT", "HARYANA", "HIMACHAL PRADESH", "JHARKHAND", "KARNATAKA", "KERALA",
    "MADHYA PRADESH", "MAHARASHTRA", "MANIPUR", "MEGHALAYA", "MIZORAM", "NAGALAND",
    "ODISHA", "PUNJAB", "RAJASTHAN", "SIKKIM", "TAMIL NADU", "TELANGANA", "TRIPURA",
    "UTTAR PRADESH", "UTTARAKHAND", "WEST BENGAL", "DELHI", "JAMMU AND KASHMIR",
    "LADAKH", "PUDUCHERRY", "CHANDIGARH", "ANDAMAN AND NICOBAR ISLANDS",
    "DADRA AND NAGAR HAVELI", "DAMAN AND DIU", "LAKSHADWEEP",
]


def _cell_text(fragment: str) -> str:
    return _WS.sub(" ", html.unescape(_TAG.sub(" ", fragment))).strip()


def _parse_details(detail: str) -> Optional[Dict[str, Any]]:
    """Split one "AHC Details" cell into its parts.

    Shape published by BIS::

        Recognition No.: <no> Validity:<dd/mm/yyyy> <NAME>
        AHC Address: <address>, <CITY>, <DISTRICT>, <STATE> ,<PIN>
        Recognized for <scope> Hallmarking
    """
    recognition = re.search(r"Recognition No\.?\s*:\s*([A-Z0-9/\-]+)", detail, re.I)
    if not recognition:
        return None

    validity = re.search(r"Validity\s*:\s*([0-9]{2}/[0-9]{2}/[0-9]{4})", detail, re.I)
    scope = re.search(r"Recognized for\s+(.+?)\s+Hallmarking", detail, re.I)
    address_match = re.search(r"AHC Address\s*:\s*(.+?)(?:\s*Recognized for|$)", detail, re.I)

    # The name sits between the validity date (or recognition no.) and "AHC Address".
    head = detail[: address_match.start()] if address_match else detail
    head = re.sub(r"Recognition No\.?\s*:\s*[A-Z0-9/\-]+", " ", head, flags=re.I)
    head = re.sub(r"Validity\s*:\s*[0-9/]+", " ", head, flags=re.I)
    name = _WS.sub(" ", head).strip(" ,-")

    address = _WS.sub(" ", address_match.group(1)).strip() if address_match else ""
    pin = re.search(r"\b(\d{6})\b", address)

    state = ""
    upper = address.upper()
    for candidate in STATES:
        if candidate in upper:
            # Prefer the longest match ("TAMIL NADU" over "NAGALAND" inside it).
            if len(candidate) > len(state):
                state = candidate

    # City/district are the comma-separated fields before the state.
    city = ""
    parts = [p.strip() for p in address.split(",") if p.strip()]
    if state:
        for index, part in enumerate(parts):
            if state in part.upper():
                if index >= 1:
                    city = parts[index - 1]
                break
    if not city and len(parts) >= 2:
        city = parts[-2]

    return {
        "recognition_number": recognition.group(1).strip(),
        "validity": validity.group(1) if validity else None,
        "name": name or None,
        "address": address or None,
        "city": re.sub(r"\s*\(.*?\)\s*", " ", city).strip() or None,
        "state": state.title() or None,
        "pin": pin.group(1) if pin else None,
        "scope": scope.group(1).strip() if scope else None,
    }


def extract(source: Path) -> List[Dict[str, Any]]:
    raw = source.read_text(encoding="utf-8", errors="ignore")
    tables = re.findall(r"<table.*?</table>", raw, re.S | re.I)
    if not tables:
        raise SystemExit("No table found in the AHC directory page - the layout may have changed.")

    centres: List[Dict[str, Any]] = []
    skipped = 0
    for row in re.findall(r"<tr.*?</tr>", tables[0], re.S | re.I):
        cells = [_cell_text(c) for c in re.findall(r"<t[dh].*?</t[dh]>", row, re.S | re.I)]
        cells = [c for c in cells if c]
        if len(cells) < 4 or not re.fullmatch(r"\d+", cells[0] or ""):
            continue

        parsed = _parse_details(cells[1])
        if parsed is None or not parsed["name"]:
            skipped += 1
            continue

        contact = cells[2] if len(cells) > 2 else ""
        phone = re.search(r"Tel\s*:\s*([0-9,\s+\-]{6,})", contact)
        email = re.search(r"Email\s*:\s*([^\s]+@[^\s]+)", contact)

        centres.append(
            {
                **parsed,
                "status": cells[3].strip() if len(cells) > 3 else "",
                "phone": phone.group(1).strip().rstrip(",") if phone else None,
                "email": email.group(1).strip() if email else None,
            }
        )

    if skipped:
        log.info("%s row(s) skipped as unparseable rather than partially filled", skipped)
    return centres


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    if not SOURCE.exists():
        raise SystemExit(
            f"{SOURCE} not found. Run scripts/fetch_hallmarking_sources.py first."
        )

    download = {}
    if REPORT.exists():
        for row in json.loads(REPORT.read_text(encoding="utf-8")):
            if row.get("document_id") == "BIS-HM-AHC-DIRECTORY":
                download = row

    centres = extract(SOURCE)
    operative = sum(1 for c in centres if (c["status"] or "").lower().startswith("operative"))
    states = sorted({c["state"] for c in centres if c["state"]})

    log.info("Parsed %s centre(s); %s operative; %s state(s)", len(centres), operative, len(states))
    if args.dry_run:
        for c in centres[:5]:
            log.info("   %-46s %-16s %s", (c["name"] or "")[:46], c["city"] or "", c["state"] or "")
        return 0

    payload = {
        "document_id": "BIS-HM-AHC-DIRECTORY",
        "source_url": download.get("url", "https://huid.manakonline.in/MANAK/AHCListForWebsite"),
        "retrieved_at": download.get("retrieved_at"),
        "sha256": download.get("sha256"),
        "is_verified": True,
        "note": (
            "Directory of Assaying & Hallmarking Centres as published by BIS on the HUID portal. "
            "This is a snapshot: a centre's recognition can change, so the platform always shows "
            "the retrieval date and links to the live BIS list rather than presenting this as "
            "current status."
        ),
        "centres": centres,
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    log.info("Wrote %s centres to %s", len(centres), OUT)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
