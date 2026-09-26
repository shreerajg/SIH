"""Base interfaces for search providers."""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import List, Optional


@dataclass
class SearchResult:
    """A single search result."""

    title: str
    url: str
    snippet: str
    domain: str
    position: int
    metadata: dict


@dataclass
class SearchResponse:
    """Complete search response."""

    query: str
    results: List[SearchResult]
    total_results: Optional[int] = None
    search_time_ms: Optional[float] = None


class SearchProvider(ABC):
    """Abstract search provider interface."""

    @abstractmethod
    def search(
        self,
        query: str,
        *,
        domains: Optional[List[str]] = None,
        max_results: int = 10,
        language: str = "en",
    ) -> SearchResponse:
        """Execute a search query.

        Args:
            query: Search query string
            domains: Optional list of domains to restrict search to
            max_results: Maximum number of results to return
            language: Language code for results

        Returns:
            SearchResponse with results
        """
        pass

    @property
    @abstractmethod
    def available(self) -> bool:
        """Whether this provider is configured and available."""
        pass
