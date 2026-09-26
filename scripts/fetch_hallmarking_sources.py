"""Download the official BIS hallmarking sources.

Every URL here is referenced by ``BIS_Current_Scheme_I_Compulsory_Certification.html``,
the BIS page already registered in ``data/source_manifest.json``. Nothing is
invented: this script only follows links BIS itself publishes, and records the
size and SHA-256 of what came back so a later reader can tell whether the bytes
changed.

Following the repository convention, the downloaded documents are **not
committed** - ``.gitignore`` excludes ``data/raw/verified_bis_*``. They are
fetched on demand and described by the manifest.

Usage::

    python scripts/fetch_hallmarking_sources.py
    python scripts/fetch_hallmarking_sources.py --dry-run
"""
from __future__ import annotations

import argparse
import hashlib
import http.client
import json
import logging
import sys
import time
import urllib.error
import urllib.request
from datetime import date
from pathlib import Path
from typing import Any, Dict, List

REPO_ROOT = Path(__file__).resolve().parents[1]
OUT_DIR = REPO_ROOT / "data" / "raw" / "verified_bis_hallmarking"
REPORT = OUT_DIR / "download_validation_report.json"

logging.basicConfig(level=logging.INFO, format="%(levelname)-7s %(message)s")
log = logging.getLogger("fetch-hallmarking")

UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) SIH26107-corpus-builder"

#: (document_id, filename, url, what it contributes).
#: Chosen to cover the capability's two flows - consumer verification and the
#: jeweller journey - plus the legal basis underneath both.
SOURCES: List[Dict[str, str]] = [
    {
        "document_id": "BIS-HM-BRIEF",
        "filename": "BIS_Brief_on_Hallmarking.pdf",
        "url": "https://www.bis.gov.in/wp-content/uploads/2020/12/brief-on-Hallmarking.pdf",
        "contributes": "Scheme overview, hallmark components, purity/fineness grades",
    },
    {
        "document_id": "BIS-HM-REGULATIONS-2018",
        "filename": "BIS_Hallmarking_Regulations_2018.pdf",
        "url": "https://www.bis.gov.in/bs/BIS_Hallmarking_Regulations_2018_Gazette_notification.pdf",
        "contributes": "Legal basis, definitions, obligations of jewellers and A&H centres",
    },
    {
        "document_id": "BIS-HM-MANDATORY-ORDER-2020",
        "filename": "BIS_Mandatory_Hallmarking_Order_2020.pdf",
        "url": "https://www.bis.gov.in/wp-content/uploads/2020/01/Mandatory-Hallmarking-Order-15.01.2020.pdf",
        "contributes": "Applicability - which articles must be hallmarked, and from when",
    },
    {
        "document_id": "BIS-HM-JEWELLER-REGISTRATION",
        "filename": "BIS_Guide_Jeweller_Registration.pdf",
        "url": "https://www.bis.gov.in/wp-content/uploads/2020/10/Guide_Jeweller_Registration_v1.1.pdf",
        "contributes": "Jeweller registration procedure",
    },
    {
        "document_id": "BIS-HM-JEWELLER-GUIDELINES",
        "filename": "BIS_Guidelines_for_Jewellers.pdf",
        "url": "https://www.bis.gov.in/wp-content/uploads/2026/07/Guidelines-for-Jewellers.pdf",
        "contributes": "Obligations of a registered jeweller",
    },
    {
        "document_id": "BIS-HM-AHC-GUIDELINES",
        "filename": "BIS_Guidelines_AHC.pdf",
        "url": "https://www.bis.gov.in/wp-content/uploads/2019/09/Guidelines_AHC_30092019.pdf",
        "contributes": "Assaying & Hallmarking Centre recognition and operation",
    },
    # HTML pages: the FAQ set is where BIS answers consumers directly.
    {
        "document_id": "BIS-HM-FAQ-GENERAL",
        "filename": "BIS_Hallmarking_FAQ_General.html",
        "url": "https://www.bis.gov.in/hallmarking-overview/hallmarking-faqs/hallmarking-faq/?lang=en",
        "contributes": "General hallmarking FAQ",
    },
    {
        "document_id": "BIS-HM-FAQ-CONSUMER",
        "filename": "BIS_Hallmarking_FAQ_Consumer.html",
        "url": "https://www.bis.gov.in/hallmarking-overview/hallmarking-faqs/mandatory/?lang=en",
        "contributes": "Consumer-facing FAQ on mandatory hallmarking",
    },
    {
        "document_id": "BIS-HM-OVERVIEW",
        "filename": "BIS_Hallmarking_Overview.html",
        "url": "https://www.bis.gov.in/hallmarking-overview/?lang=en",
        "contributes": "Hallmarking overview page",
    },
    {
        "document_id": "BIS-HM-CONSUMER-PROTECTION",
        "filename": "BIS_Hallmarking_Consumer_Protection.html",
        "url": "https://www.bis.gov.in/hallmarking-overview/consumer-protection/?lang=en",
        "contributes": "Consumer protection / grievance route",
    },
    {
        "document_id": "BIS-HM-JEWELLERS-PAGE",
        "filename": "BIS_Hallmarking_Jewellers.html",
        "url": "https://www.bis.gov.in/hallmarking-jewellers/?lang=en",
        "contributes": "Jeweller-facing hallmarking page",
    },
    {
        "document_id": "BIS-HM-AHC-PAGE",
        "filename": "BIS_Hallmarking_AHC.html",
        "url": "https://www.bis.gov.in/a-h-centre/?lang=en",
        "contributes": "Assaying & Hallmarking Centre page",
    },
]

#: The A&H centre directory lives on the HUID portal, not bis.gov.in. Fetched
#: separately because it is a different host and may not be scriptable.
CENTRE_DIRECTORY = {
    "document_id": "BIS-HM-AHC-DIRECTORY",
    "filename": "BIS_AHC_List.html",
    "url": "https://huid.manakonline.in/MANAK/AHCListForWebsite",
    "contributes": "Directory of recognised Assaying & Hallmarking Centres",
}


def fetch(url: str, target: Path, timeout: int = 60, attempts: int = 3) -> Dict[str, Any]:
    """Fetch one document, retrying a truncated transfer.

    The BIS server closes some connections early on larger PDFs, which arrives
    as http.client.IncompleteRead. A partial file would be worse than none - it
    would parse into a corpus that silently stops mid-document - so a short read
    is discarded and retried rather than kept.
    """
    payload = b""
    content_type = ""
    last_error = ""

    for attempt in range(1, attempts + 1):
        request = urllib.request.Request(url, headers={"User-Agent": UA})
        try:
            with urllib.request.urlopen(request, timeout=timeout) as response:
                content_type = response.headers.get("Content-Type", "")
                expected = response.headers.get("Content-Length")
                payload = response.read()
            if expected and len(payload) != int(expected):
                last_error = f"short read: {len(payload)} of {expected} bytes"
                payload = b""
                time.sleep(2.0 * attempt)
                continue
            break
        except http.client.IncompleteRead as exc:
            # Keep what arrived only if it is the whole document; otherwise retry.
            last_error = f"IncompleteRead: {len(exc.partial)} bytes, {exc.expected} more expected"
            payload = b""
            time.sleep(2.0 * attempt)
        except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError, OSError) as exc:
            last_error = f"{exc.__class__.__name__}: {exc}"
            payload = b""
            time.sleep(2.0 * attempt)

    if not payload:
        return {"status": "FAILED", "error": last_error or "empty response"}

    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(payload)
    return {
        "status": "OK",
        "bytes": len(payload),
        "sha256": hashlib.sha256(payload).hexdigest(),
        "content_type": content_type,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dry-run", action="store_true", help="list sources without fetching")
    parser.add_argument("--timeout", type=int, default=60)
    args = parser.parse_args()

    sources = SOURCES + [CENTRE_DIRECTORY]

    if args.dry_run:
        for source in sources:
            log.info("%-32s %s", source["document_id"], source["url"][:88])
        log.info("%s source(s) would be fetched into %s", len(sources), OUT_DIR)
        return 0

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    report: List[Dict[str, Any]] = []
    ok = 0

    for source in sources:
        target = OUT_DIR / source["filename"]
        result = fetch(source["url"], target, timeout=args.timeout)
        row = {
            "document_id": source["document_id"],
            "url": source["url"],
            "target": source["filename"],
            "contributes": source["contributes"],
            "retrieved_at": date.today().isoformat(),
            **result,
        }
        report.append(row)
        if result["status"] == "OK":
            ok += 1
            log.info("OK      %-32s %8d bytes  %s",
                     source["document_id"], result["bytes"], result.get("content_type", "")[:28])
        else:
            log.warning("FAILED  %-32s %s", source["document_id"], result.get("error", "")[:70])
        # Be a considerate client of a government server.
        time.sleep(1.0)

    REPORT.write_text(json.dumps(report, indent=2), encoding="utf-8")
    log.info("-" * 60)
    log.info("%s/%s fetched. Report: %s", ok, len(sources), REPORT)
    if ok < len(sources):
        log.warning(
            "Sources that failed are simply absent from the corpus - the platform reports "
            "'unable to verify' for anything they would have supported."
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
