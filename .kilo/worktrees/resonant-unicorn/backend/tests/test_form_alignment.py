"""Cross-boundary contract: the UI's evidence form must match the requirement data.

The gap analyzer matches evidence by (evidence_type, keyword). If the frontend
offers an evidence item whose name matches no requirement's keywords, ticking it
does nothing; and if a requirement's keywords match no offered evidence item, the
user can never move it out of TEST_REQUIRED / DOCUMENT_REQUIRED. Both are silent
failures that look like the analyzer is broken, so they are tested here.
"""
from __future__ import annotations

import json
import re
from pathlib import Path
from typing import List, Tuple

import pytest

from app.compliance.gap_analyzer import EVIDENCE_EQUIVALENTS
from app.core.config import REPO_ROOT

FORM_FILE = REPO_ROOT / "frontend" / "src" / "lib" / "gapForm.ts"
REQUIREMENTS_DIR = REPO_ROOT / "data" / "requirements"

PRESET_RE = re.compile(r"\{ evidence_type: '([a-z_]+)', name: '([^']+)' \}")

#: Requirements that intentionally cannot be satisfied by uploading anything,
#: because only the certifying authority can settle them.
INTENTIONALLY_UNSATISFIABLE = {"D8-R07"}


def _presets() -> List[Tuple[str, str]]:
    if not FORM_FILE.exists():
        pytest.skip("frontend form definitions not present")
    text = FORM_FILE.read_text(encoding="utf-8")
    return list(dict.fromkeys(PRESET_RE.findall(text)))


def _requirements():
    out = []
    for path in sorted(REQUIREMENTS_DIR.glob("*.json")):
        payload = json.loads(path.read_text(encoding="utf-8"))
        for item in payload["requirements"]:
            out.append(
                (
                    payload["standard_id"],
                    item["requirement_code"],
                    item["evidence_type"],
                    [k.lower() for k in item.get("match_keywords", [])],
                )
            )
    return out


def _matches(preset_type: str, preset_name: str, req_type: str, keywords: List[str]) -> bool:
    accepted = EVIDENCE_EQUIVALENTS.get(req_type, {req_type})
    if preset_type not in accepted:
        return False
    lowered = preset_name.lower()
    return any(keyword in lowered for keyword in keywords)


def test_every_offered_evidence_item_can_satisfy_something():
    presets = _presets()
    requirements = _requirements()
    assert presets, "the form should offer evidence items"

    dead = [
        f"{etype}: {name}"
        for etype, name in presets
        if not any(_matches(etype, name, rtype, kws) for _, _, rtype, kws in requirements)
    ]
    assert not dead, f"these evidence options match no requirement: {dead}"


def test_every_evidence_backed_requirement_is_reachable_from_the_form():
    presets = _presets()
    unreachable = []
    for standard_id, code, rtype, keywords in _requirements():
        if rtype == "declared_value" or not keywords:
            continue
        if code in INTENTIONALLY_UNSATISFIABLE:
            continue
        if not any(_matches(etype, name, rtype, keywords) for etype, name in presets):
            unreachable.append(f"{standard_id}/{code}")
    assert not unreachable, (
        "these requirements can never leave the 'required' state from the UI: "
        f"{unreachable}"
    )


def test_declared_value_rules_reference_fields_the_form_collects():
    """A check-rule attribute nobody can enter always evaluates to UNKNOWN."""
    if not FORM_FILE.exists():
        pytest.skip("frontend form definitions not present")
    form_text = FORM_FILE.read_text(encoding="utf-8")
    collected = set(re.findall(r"\{ key: '([a-z0-9_]+)'", form_text))
    # Attributes the product-understanding service extracts on its own.
    from app.services.product_understanding import ALLOWED_ATTRIBUTE_KEYS

    available = collected | ALLOWED_ATTRIBUTE_KEYS

    missing = []
    for path in sorted(REQUIREMENTS_DIR.glob("*.json")):
        payload = json.loads(path.read_text(encoding="utf-8"))
        for item in payload["requirements"]:
            attribute = (item.get("check_rule") or {}).get("attribute")
            if attribute and attribute not in available:
                missing.append(f"{payload['standard_id']}/{item['requirement_code']}:{attribute}")
    assert not missing, f"check-rule attributes that can never be supplied: {missing}"
