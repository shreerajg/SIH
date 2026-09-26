"""BIS-specific dynamic retrieval orchestration."""
from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import List, Optional

from app.retrieval.base import SearchProvider, SearchResult
from app.retrieval.source_validator import (
    OFFICIAL_BIS_DOMAINS,
    classify_source,
    compute_relevance_score,
)

logger = logging.getLogger(__name__)


@dataclass
class RetrievedSource:
    """A retrieved and validated source."""

    id: str  # S1, S2, etc.
    title: str
    url: str
    snippet: str
    domain: str
    official: bool
    trust_level: str
    relevance_score: float
    position: int


class BISRetriever:
    """Orchestrates BIS-specific search and source validation."""

    def __init__(self, search_provider: SearchProvider):
        self.search_provider = search_provider

    def retrieve(
        self,
        query: str,
        *,
        max_results: int = 8,
        prefer_official: bool = True,
        language: str = "en",
    ) -> List[RetrievedSource]:
        """Retrieve and validate sources for a BIS query.

        Args:
            query: User's question
            max_results: Maximum sources to return
            prefer_official: Prioritize official BIS sources
            language: Language code

        Returns:
            List of validated, ranked sources
        """
        if not self.search_provider.available:
            logger.warning("No search provider available")
            return []

        # Generate search queries
        queries = self._generate_search_queries(query, language)

        # Execute searches
        all_results: List[SearchResult] = []
        seen_urls = set()

        for search_query in queries:
            response = self.search_provider.search(
                search_query,
                domains=list(OFFICIAL_BIS_DOMAINS) if prefer_official else None,
                max_results=max_results,
                language=language,
            )

            for result in response.results:
                if result.url not in seen_urls:
                    seen_urls.add(result.url)
                    all_results.append(result)

        # Validate and score
        sources = []
        for idx, result in enumerate(all_results[:max_results * 2]):
            classification = classify_source(result.url)
            relevance = compute_relevance_score(
                {
                    "title": result.title,
                    "snippet": result.snippet,
                    "url": result.url,
                },
                query,
                prefer_official=prefer_official,
            )

            # Filter out very low relevance
            if relevance < 0.3:
                continue

            sources.append(
                RetrievedSource(
                    id=f"S{idx + 1}",
                    title=result.title,
                    url=result.url,
                    snippet=result.snippet,
                    domain=result.domain,
                    official=classification["official"],
                    trust_level=classification["trust_level"],
                    relevance_score=relevance,
                    position=result.position,
                )
            )

        # Rank: official sources first, then by relevance
        sources.sort(key=lambda s: (not s.official, -s.relevance_score))

        return sources[:max_results]

    def _generate_search_queries(self, query: str, language: str) -> List[str]:
        """Generate multiple search query variations.

        Creates targeted queries to maximize recall of relevant BIS information.
        """
        queries = []

        # Direct query with BIS context
        queries.append(f"BIS {query}")

        # Bureau of Indian Standards full form
        if "standard" in query.lower() and "bis" not in query.lower():
            queries.append(f"Bureau of Indian Standards {query}")

        # IS number specific
        if any(word in query.lower() for word in ["standard", "is number", "certification"]):
            queries.append(f"Indian Standard {query}")

        return queries[:3]  # Limit to avoid excessive API calls
