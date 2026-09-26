"""Concrete search provider implementations."""
from __future__ import annotations

import logging
from typing import List, Optional

import httpx

from app.retrieval.base import SearchProvider, SearchResponse, SearchResult
from app.retrieval.source_validator import get_domain

logger = logging.getLogger(__name__)


class SerperSearchProvider(SearchProvider):
    """Serper.dev Google Search API implementation.

    Serper provides fast, reliable Google search results via API.
    Get a free API key at serper.dev (2,500 free queries/month).
    """

    def __init__(self, api_key: str, timeout: int = 10):
        self.api_key = api_key
        self.timeout = timeout
        self.base_url = "https://google.serper.dev/search"

    @property
    def available(self) -> bool:
        return bool(self.api_key)

    def search(
        self,
        query: str,
        *,
        domains: Optional[List[str]] = None,
        max_results: int = 10,
        language: str = "en",
    ) -> SearchResponse:
        if not self.available:
            return SearchResponse(query=query, results=[])

        # Build site-restricted query if domains specified
        search_query = query
        if domains:
            site_filters = " OR ".join(f"site:{d}" for d in domains)
            search_query = f"({site_filters}) {query}"

        payload = {
            "q": search_query,
            "num": max_results,
            "gl": "in",  # India
            "hl": language,
        }

        try:
            resp = httpx.post(
                self.base_url,
                json=payload,
                headers={
                    "X-API-KEY": self.api_key,
                    "Content-Type": "application/json",
                },
                timeout=self.timeout,
            )
            resp.raise_for_status()
            data = resp.json()

            results = []
            for idx, item in enumerate(data.get("organic", [])[:max_results]):
                results.append(
                    SearchResult(
                        title=item.get("title", ""),
                        url=item.get("link", ""),
                        snippet=item.get("snippet", ""),
                        domain=get_domain(item.get("link", "")),
                        position=idx + 1,
                        metadata={
                            "date": item.get("date"),
                            "position": item.get("position"),
                        },
                    )
                )

            return SearchResponse(
                query=query,
                results=results,
                total_results=data.get("searchInformation", {}).get("totalResults"),
                search_time_ms=data.get("searchInformation", {}).get("searchTime", 0) * 1000,
            )

        except httpx.TimeoutException:
            logger.warning("Serper search timed out for query: %s", query)
            return SearchResponse(query=query, results=[])
        except httpx.HTTPError as exc:
            logger.warning("Serper API error: %s", exc)
            return SearchResponse(query=query, results=[])
        except Exception as exc:
            logger.exception("Unexpected search error: %s", exc)
            return SearchResponse(query=query, results=[])


class NullSearchProvider(SearchProvider):
    """Fallback provider when no search API is configured."""

    @property
    def available(self) -> bool:
        return False

    def search(
        self,
        query: str,
        *,
        domains: Optional[List[str]] = None,
        max_results: int = 10,
        language: str = "en",
    ) -> SearchResponse:
        return SearchResponse(query=query, results=[])
