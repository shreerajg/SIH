"""BIS source validation and trust scoring."""
from __future__ import annotations

import re
from typing import Dict, Literal
from urllib.parse import urlparse


# Official BIS domains verified as of 2026
OFFICIAL_BIS_DOMAINS = {
    "bis.gov.in",
    "www.bis.gov.in",
    "bis.org.in",
    "www.bis.org.in",
    "standards.bis.gov.in",
    "lims.bis.gov.in",
    "manakonline.in",
    "services.bis.gov.in",
}

# Supporting domains that may contain relevant BIS information
SUPPORTING_DOMAINS = {
    "makeinindia.com",
    "indiacode.nic.in",  # Indian legal code
}

TrustLevel = Literal["official", "supporting", "unknown"]


def is_official_bis_source(url: str) -> bool:
    """Check if URL is from an official BIS domain."""
    try:
        parsed = urlparse(url)
        domain = parsed.netloc.lower()
        # Remove port if present
        domain = domain.split(":")[0]
        return domain in OFFICIAL_BIS_DOMAINS
    except Exception:
        return False


def get_domain(url: str) -> str:
    """Extract domain from URL."""
    try:
        parsed = urlparse(url)
        return parsed.netloc.lower().split(":")[0]
    except Exception:
        return ""


def classify_source(url: str) -> Dict[str, any]:
    """Classify a source URL by trust level.

    Returns:
        Dict with keys: official, domain, trust_level
    """
    domain = get_domain(url)

    if domain in OFFICIAL_BIS_DOMAINS:
        return {
            "official": True,
            "domain": domain,
            "trust_level": "official",
        }
    elif domain in SUPPORTING_DOMAINS:
        return {
            "official": False,
            "domain": domain,
            "trust_level": "supporting",
        }
    else:
        return {
            "official": False,
            "domain": domain,
            "trust_level": "unknown",
        }


def extract_is_number(text: str) -> Optional[str]:
    """Extract IS number from text if present.

    Matches patterns like:
    - IS 2082
    - IS 2082:2018
    - IS/ISO 9001
    """
    pattern = r'\bIS[\s/-]?\d{1,5}(?:[\s:-]\d{4})?(?:\s*\([^)]+\))?\b'
    match = re.search(pattern, text, re.IGNORECASE)
    return match.group(0) if match else None


def compute_relevance_score(
    result: Dict,
    query: str,
    prefer_official: bool = True,
) -> float:
    """Compute relevance score for a search result.

    Args:
        result: Search result dict with title, snippet, url
        query: Original query
        prefer_official: Boost official BIS sources

    Returns:
        Score between 0 and 1
    """
    score = 0.5  # Base score

    title = result.get("title", "").lower()
    snippet = result.get("snippet", "").lower()
    url = result.get("url", "")
    query_lower = query.lower()

    classification = classify_source(url)

    # Official source bonus
    if classification["official"] and prefer_official:
        score += 0.3

    # Query terms in title
    query_words = query_lower.split()
    title_matches = sum(1 for word in query_words if word in title)
    score += 0.1 * (title_matches / max(len(query_words), 1))

    # IS number present
    if extract_is_number(title) or extract_is_number(snippet):
        score += 0.15

    # BIS keywords
    bis_keywords = ["bureau", "indian", "standards", "certification", "is number"]
    keyword_matches = sum(1 for kw in bis_keywords if kw in title or kw in snippet)
    score += 0.05 * keyword_matches

    return min(score, 1.0)
