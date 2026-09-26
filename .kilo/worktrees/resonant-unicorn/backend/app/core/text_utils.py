"""Deterministic text helpers.

Everything here is rule based and unit tested. None of it depends on an LLM,
which is what makes the no-API fallback mode usable.
"""
from __future__ import annotations

import re
import unicodedata
from typing import Dict, List, Optional, Tuple

_WORD_RE = re.compile(r"[a-z0-9]+(?:\.[0-9]+)*")

STOPWORDS = {
    "a", "an", "and", "are", "as", "at", "be", "by", "for", "from", "has", "have",
    "in", "is", "it", "its", "of", "on", "or", "our", "that", "the", "this", "to",
    "was", "we", "were", "will", "with", "which", "shall", "manufacture",
    "manufactures", "manufacturer", "manufacturing", "make", "makes", "produce",
    "produces", "product", "products", "company", "used", "use", "using",
}


def slugify(value: str) -> str:
    value = unicodedata.normalize("NFKD", value or "")
    value = re.sub(r"[^\w\s-]", "", value).strip().lower()
    return re.sub(r"[-\s]+", "-", value) or "item"


def tokenize(text: str) -> List[str]:
    return _WORD_RE.findall((text or "").lower())


def content_tokens(text: str) -> List[str]:
    return [t for t in tokenize(text) if t not in STOPWORDS and len(t) > 2]


# ---------------------------------------------------------------------------
# IS number handling
# ---------------------------------------------------------------------------

#: Accepts IS 302, IS302, is-302, IS 302 (Part 2), IS 302-2-201, DEMO-STD-001 ...
_IS_PATTERNS = [
    re.compile(r"^(?:is|indian\s*standard)?[\s\-:/]*([0-9]{2,6})(.*)$", re.IGNORECASE),
]
_PART_RE = re.compile(r"part\s*([0-9]+)", re.IGNORECASE)
_SEC_RE = re.compile(r"sec(?:tion)?\s*([0-9]+)", re.IGNORECASE)
_YEAR_RE = re.compile(r"(?:^|[\s:\-/])((?:19|20)[0-9]{2})(?:$|[\s\)])")
_DEMO_RE = re.compile(r"^(demo)[\s\-_]*(std)?[\s\-_]*([0-9]{1,4})([\s\-_a-z0-9]*)$", re.IGNORECASE)


def normalize_is_number(raw: str) -> str:
    """Normalise user input into the canonical corpus key.

    ``IS 302 (Part 2)`` -> ``IS-302-P2``;  ``demo std 1`` -> ``DEMO-STD-001``.
    Returns "" when the input cannot be interpreted as a standard reference.
    """
    if not raw:
        return ""
    value = str(raw).strip()
    value = re.sub(r"\s+", " ", value)

    demo = _DEMO_RE.match(value.replace(":", " "))
    if demo:
        number = int(demo.group(3))
        suffix = _normalise_suffix(demo.group(4) or "")
        return f"DEMO-STD-{number:03d}{suffix}"

    compact = value.replace(":", " ")
    for pattern in _IS_PATTERNS:
        match = pattern.match(compact)
        if not match:
            continue
        base = match.group(1)
        rest = match.group(2) or ""
        return f"IS-{base}{_normalise_suffix(rest)}"
    return ""


def _normalise_suffix(rest: str) -> str:
    """Turn '(Part 2) Sec 1 : 2019' into '-P2-S1'. Years are dropped."""
    parts: List[str] = []
    part = _PART_RE.search(rest)
    sec = _SEC_RE.search(rest)
    if part:
        parts.append(f"P{int(part.group(1))}")
    if sec:
        parts.append(f"S{int(sec.group(1))}")
    if not parts:
        # Bare numeric suffixes such as "302-2-201" or "-2".
        stripped = _YEAR_RE.sub(" ", rest)
        for token in re.findall(r"[0-9]+", stripped):
            parts.append(f"P{int(token)}")
            break
    return ("-" + "-".join(parts)) if parts else ""


def extract_is_numbers(text: str) -> List[str]:
    """Find every IS/DEMO standard reference inside free text."""
    found: List[str] = []
    for match in re.finditer(
        r"\b(?:IS|Indian Standard)\s*:?\s*[0-9]{2,6}(?:\s*\(?Part\s*[0-9]+\)?)?"
        r"|\bDEMO[\s\-_]*STD[\s\-_]*[0-9]{1,4}(?:-P[0-9]+)?",
        text or "",
        flags=re.IGNORECASE,
    ):
        normalized = normalize_is_number(match.group(0))
        if normalized and normalized not in found:
            found.append(normalized)
    return found


def display_is_number(normalized: str) -> str:
    """Inverse of :func:`normalize_is_number` for presentation.

    Only formats values that really are IS numbers. A corpus also holds
    documents that are not Indian Standards at all - Quality Control Orders,
    gazette notifications - and running their identifiers through this would
    manufacture an IS number that does not exist: ``QCO-PRESSURE-COOKER-2020``
    became ``IS QCO (Part RESSURE)``. Those are returned unchanged so the
    caller displays the real document identifier instead.
    """
    if not normalized:
        return ""
    if normalized.startswith("DEMO-STD-"):
        return normalized
    if not normalized.startswith("IS-"):
        # Not an IS number; never dress it up as one.
        return normalized
    body = normalized[3:]
    bits = body.split("-")
    if not bits or not bits[0].isdigit():
        return normalized
    out = f"IS {bits[0]}"
    for bit in bits[1:]:
        if bit.startswith("P"):
            out += f" (Part {bit[1:]})"
        elif bit.startswith("S"):
            out += f" Sec {bit[1:]}"
    return out


# ---------------------------------------------------------------------------
# Numeric attribute extraction from a product description
# ---------------------------------------------------------------------------

_NUM = r"([0-9]+(?:\.[0-9]+)?)"

ATTRIBUTE_PATTERNS: List[Tuple[str, re.Pattern, str]] = [
    ("capacity_litres", re.compile(_NUM + r"\s*(?:l|lt|ltr|litre|liter|litres|liters)\b", re.I), "float"),
    ("voltage_v", re.compile(_NUM + r"\s*(?:v|volt|volts|vac)\b", re.I), "float"),
    ("power_w", re.compile(_NUM + r"\s*(?:w|watt|watts)\b", re.I), "float"),
    ("power_w", re.compile(_NUM + r"\s*(?:kw|kilowatt|kilowatts)\b", re.I), "kilo"),
    ("frequency_hz", re.compile(_NUM + r"\s*(?:hz|hertz)\b", re.I), "float"),
    ("pressure_bar", re.compile(_NUM + r"\s*(?:bar)\b", re.I), "float"),
    ("pressure_kpa", re.compile(_NUM + r"\s*(?:kpa)\b", re.I), "float"),
    ("temperature_c", re.compile(_NUM + r"\s*(?:deg\s*c|degc|celsius|\u00b0c)\b", re.I), "float"),
    ("mass_kg", re.compile(_NUM + r"\s*(?:kg|kilogram|kilograms)\b", re.I), "float"),
    ("age_group_min_years", re.compile(r"(?:above|over|ages?)\s*" + _NUM + r"\s*(?:years?|yrs?)", re.I), "float"),
]


def extract_numeric_attributes(text: str) -> Dict[str, float]:
    """Pull quantities such as 15 L / 230 V / 2000 W out of plain English."""
    result: Dict[str, float] = {}
    for key, pattern, mode in ATTRIBUTE_PATTERNS:
        match = pattern.search(text or "")
        if not match:
            continue
        try:
            value = float(match.group(1))
        except ValueError:
            continue
        if mode == "kilo":
            value *= 1000
        result.setdefault(key, value)
    return result


def coerce_number(value) -> Optional[float]:
    if value is None:
        return None
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return float(value)
    match = re.search(_NUM, str(value))
    return float(match.group(1)) if match else None


def truncate(text: str, limit: int = 320) -> str:
    text = re.sub(r"\s+", " ", (text or "").strip())
    if len(text) <= limit:
        return text
    return text[: limit - 1].rsplit(" ", 1)[0] + "\u2026"

# ---------------------------------------------------------------------------
# Script detection
# ---------------------------------------------------------------------------

#: Official BIS gazette documents are published bilingually: the Hindi text of
#: an order appears first, then the identical English text, and the parser
#: emits them as separate chunks. Both renderings say the same thing, so the
#: Hindi chunks are duplicates rather than extra information - and quoting them
#: back to an English-speaking user is noise. This measures how much of a
#: chunk's alphabetic content is Devanagari so ingestion can keep one rendering.


def devanagari_ratio(text: str) -> float:
    """Share of a string's letters that are Devanagari, between 0.0 and 1.0."""
    letters = [c for c in (text or "") if c.isalpha()]
    if not letters:
        return 0.0
    devanagari = sum(1 for c in letters if "ऀ" <= c <= "ॿ")
    return devanagari / len(letters)


def is_predominantly_devanagari(text: str, threshold: float = 0.30) -> bool:
    """True when a chunk is the Hindi rendering rather than the English one.

    The threshold is deliberately low: a genuinely English clause carries at
    most a stray transliterated word, whereas the Hindi rendering of a gazette
    clause is overwhelmingly Devanagari. Mixed chunks that still carry
    substantial English are kept.
    """
    return devanagari_ratio(text) >= threshold


_DEVANAGARI_RUN = re.compile(r"[ऀ-ॿ][ऀ-ॿ\s]*")


def strip_devanagari(text: str, min_remaining: int = 24) -> str:
    """Remove Devanagari runs from a chunk that is otherwise English.

    Bilingual BIS documents also mix the two scripts *within* a line - a
    heading reads "लाइसेंस का दायरा / Scope of the Licence". Dropping the whole
    chunk would throw away the English, so the Hindi run is removed and the
    separator it leaves behind is tidied up.

    Returns the original text unchanged when stripping would leave too little
    to be useful, so a Hindi-only chunk is never silently reduced to
    punctuation.
    """
    if not text:
        return text
    cleaned = _DEVANAGARI_RUN.sub(" ", text)
    # Tidy separators orphaned by the removal: " / Scope", "-: Scope", "  ,".
    cleaned = re.sub(r"\s*([/|:;,\-–—])\s*(?=[/|:;,\-–—])", " ", cleaned)
    cleaned = re.sub(r"^[\s/|:;,\-–—.]+", "", cleaned)
    cleaned = re.sub(r"\s+", " ", cleaned).strip()
    if len(cleaned) < min_remaining:
        return text
    return cleaned
