"""Lightweight caching for search results."""
from __future__ import annotations

import hashlib
import json
import logging
import time
from dataclasses import asdict
from pathlib import Path
from typing import Dict, List, Optional

from app.retrieval.bis_retriever import RetrievedSource

logger = logging.getLogger(__name__)


class SearchCache:
    """Simple file-based cache for search results."""

    def __init__(self, cache_dir: Path, ttl_seconds: int = 3600):
        """Initialize cache.

        Args:
            cache_dir: Directory to store cache files
            ttl_seconds: Time to live for cached results (default 1 hour)
        """
        self.cache_dir = cache_dir
        self.ttl_seconds = ttl_seconds
        self.cache_dir.mkdir(parents=True, exist_ok=True)

    def get(self, query: str, language: str = "en") -> Optional[List[RetrievedSource]]:
        """Retrieve cached results if available and fresh."""
        cache_key = self._make_key(query, language)
        cache_file = self.cache_dir / f"{cache_key}.json"

        if not cache_file.exists():
            return None

        try:
            with open(cache_file, "r", encoding="utf-8") as f:
                data = json.load(f)

            # Check TTL
            cached_at = data.get("cached_at", 0)
            if time.time() - cached_at > self.ttl_seconds:
                cache_file.unlink()
                return None

            # Reconstruct sources
            sources = [
                RetrievedSource(**item) for item in data.get("sources", [])
            ]
            logger.info("Cache hit for query: %s", query[:50])
            return sources

        except Exception as exc:
            logger.warning("Cache read error: %s", exc)
            return None

    def set(self, query: str, sources: List[RetrievedSource], language: str = "en") -> None:
        """Store search results in cache."""
        cache_key = self._make_key(query, language)
        cache_file = self.cache_dir / f"{cache_key}.json"

        try:
            data = {
                "query": query,
                "language": language,
                "cached_at": time.time(),
                "sources": [asdict(s) for s in sources],
            }

            with open(cache_file, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)

            logger.info("Cached %d sources for query: %s", len(sources), query[:50])

        except Exception as exc:
            logger.warning("Cache write error: %s", exc)

    def _make_key(self, query: str, language: str) -> str:
        """Generate cache key from query."""
        combined = f"{query}:{language}".lower()
        return hashlib.sha256(combined.encode()).hexdigest()[:16]

    def clear_expired(self) -> int:
        """Remove expired cache entries. Returns count removed."""
        removed = 0
        now = time.time()

        for cache_file in self.cache_dir.glob("*.json"):
            try:
                with open(cache_file, "r", encoding="utf-8") as f:
                    data = json.load(f)

                cached_at = data.get("cached_at", 0)
                if now - cached_at > self.ttl_seconds:
                    cache_file.unlink()
                    removed += 1

            except Exception:
                pass

        return removed
