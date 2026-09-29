"""Dynamic chat API endpoint with grounded BIS knowledge retrieval."""
from __future__ import annotations

import logging
from pathlib import Path
from typing import Any, Dict, Optional

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from pymongo.database import Database

from app.api.deps import db_session
from app.core.config import settings
from app.core.constants import DISCLAIMER
from app.retrieval.bis_retriever import BISRetriever
from app.retrieval.cache import SearchCache
from app.retrieval.search_provider import SerperSearchProvider, NullSearchProvider
from app.services.gemini_grounded import get_gemini_grounded_service

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/chat", tags=["chat"])


class ChatRequest(BaseModel):
    """Dynamic chat request."""

    message: str = Field(description="User's question or message")
    conversation_id: Optional[str] = Field(default=None, description="Optional conversation ID for context")
    language: str = Field(default="en", description="Language code: en or hi")


class ChatResponse(BaseModel):
    """Dynamic chat response with grounded sources."""

    answer: str
    sources: list[Dict[str, Any]]
    intent: str
    answerable: bool
    llm_used: bool
    conversation_id: Optional[str] = None
    search_queries: Optional[list[str]] = None
    query_understanding: Optional[Dict[str, Any]] = None
    confidence: Optional[str] = None
    disclaimer: str


# Initialize search infrastructure
_search_provider = None
_retriever = None
_cache = None


def get_search_infrastructure():
    """Lazy initialization of search components."""
    global _search_provider, _retriever, _cache

    if _search_provider is None:
        # Initialize search provider
        if settings.serper_api_key:
            _search_provider = SerperSearchProvider(
                api_key=settings.serper_api_key,
                timeout=10,
            )
            logger.info("Serper search provider initialized")
        else:
            _search_provider = NullSearchProvider()
            logger.warning("No search API key configured - dynamic retrieval unavailable")

    if _cache is None:
        # Initialize cache
        cache_dir = Path(settings.upload_dir).parent / "search_cache"
        _cache = SearchCache(cache_dir, ttl_seconds=settings.search_cache_ttl)
        logger.info("Search cache initialized at %s", cache_dir)

    if _retriever is None:
        # Initialize BIS retriever
        _retriever = BISRetriever(_search_provider)
        logger.info("BIS retriever initialized")

    return _search_provider, _retriever, _cache


@router.post("/message", response_model=ChatResponse)
def chat_message(
    payload: ChatRequest,
    db: Database = Depends(db_session),
) -> ChatResponse:
    """Dynamic chat endpoint with live BIS knowledge retrieval.

    This endpoint:
    1. Understands the user's query intent
    2. Dynamically searches authoritative BIS sources
    3. Generates a grounded answer from retrieved evidence
    4. Returns the answer with clickable source citations

    No pre-ingested corpus required - information is retrieved at query time.
    """
    provider, retriever, cache = get_search_infrastructure()

    if not provider.available:
        return ChatResponse(
            answer=(
                "Dynamic BIS knowledge retrieval is not configured. "
                "A search API key is required to enable live information retrieval.\n\n"
                "To enable: Set SERPER_API_KEY in backend/.env (get free key at serper.dev)"
            ),
            sources=[],
            intent="system_message",
            answerable=False,
            llm_used=False,
            disclaimer=DISCLAIMER,
        )

    # Check cache first
    cached_sources = cache.get(payload.message, payload.language)

    if cached_sources:
        logger.info("Using cached sources for query")
        # Still generate fresh answer, but skip search
        service = get_gemini_grounded_service(retriever)

        # Build response directly with cached sources
        from app.services.gemini_grounded import GeminiGroundedService
        temp_service = GeminiGroundedService(retriever=retriever)
        understanding = temp_service._understand_query(payload.message)

        if temp_service.llm.available:
            generated = temp_service._call_gemini(
                payload.message, cached_sources, payload.language
            )
            if generated:
                result = {
                    "answer": generated,
                    "sources": [temp_service._source_to_dict(s) for s in cached_sources],
                    "intent": understanding.intent.value,
                    "answerable": True,
                    "confidence": "High",
                    "llm_used": True,
                }
            else:
                result = temp_service._extractive_response(
                    payload.message, cached_sources, understanding, payload.language
                )
        else:
            result = temp_service._extractive_response(
                payload.message, cached_sources, understanding, payload.language
            )
    else:
        # Full retrieval pipeline
        service = get_gemini_grounded_service(retriever)
        result = service.answer(
            payload.message,
            language=payload.language,
            max_sources=8,
        )

        # Cache the sources for future queries
        if result.get("sources"):
            # Reconstruct sources for caching
            from app.retrieval.bis_retriever import RetrievedSource
            sources_to_cache = [
                RetrievedSource(
                    id=s["id"],
                    title=s["title"],
                    url=s["url"],
                    snippet=s["snippet"],
                    domain=s["domain"],
                    official=s["official"],
                    trust_level=s["trust_level"],
                    relevance_score=0.8,
                    position=int(s["id"][1:]),
                )
                for s in result["sources"]
            ]
            cache.set(payload.message, sources_to_cache, payload.language)

    return ChatResponse(
        answer=result["answer"],
        sources=result.get("sources", []),
        intent=result.get("intent", "unknown"),
        answerable=result.get("answerable", False),
        llm_used=result.get("llm_used", False),
        conversation_id=payload.conversation_id,
        search_queries=result.get("search_queries"),
        query_understanding=result.get("query_understanding"),
        confidence=result.get("confidence"),
        disclaimer=DISCLAIMER,
    )


@router.get("/health")
def chat_health():
    """Check dynamic chat system health."""
    provider, retriever, cache = get_search_infrastructure()

    return {
        "search_provider_available": provider.available,
        "cache_enabled": True,
        "retrieval_enabled": retriever is not None,
    }
