"""FastAPI application entry point."""
from __future__ import annotations

import logging

from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pymongo.errors import ConnectionFailure, PyMongoError, ServerSelectionTimeoutError

from app.api import certification, chat, evidence, hallmarking, health, products, standards
from app.api.deps import UNREACHABLE_DETAIL
from app.core.config import settings
from app.core.constants import DISCLAIMER
from app.db.indexes import ensure_indexes
from app.db.mongo import DatabaseNotConfigured, active_backend, init_client
from app.search.vector_store import ensure_vector_indexes

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-7s %(name)s: %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger(__name__)

@asynccontextmanager
async def lifespan(_: FastAPI):
    try:
        db = init_client()
        # MongoDB creates collections on first write, so startup only has to
        # declare indexes. create_index is idempotent.
        report = ensure_indexes(db)
        logger.info(
            "Database ready (%s): %s index(es) ensured", active_backend(), len(report["created"])
        )
        # Atlas vector indexes. Builds are asynchronous, so retrieval uses the
        # brute-force cosine path over the same vectors until they are ready.
        vector_report = ensure_vector_indexes()
        logger.info("Vector indexes: %s", vector_report)
    except DatabaseNotConfigured as exc:
        logger.error("Database not configured: %s", exc)
    except (ConnectionFailure, ServerSelectionTimeoutError) as exc:
        # Do not abort startup: /api/health must stay reachable so the operator
        # can see *why* the platform is refusing to answer.
        logger.error("MongoDB unreachable at startup: %s", exc)
    except PyMongoError as exc:  # pragma: no cover - infra dependent
        logger.error("Database initialisation failed: %s", exc)
    yield


app = FastAPI(
    lifespan=lifespan,
    title=settings.app_name,
    version="1.0.0",
    description=(
        "AI-powered BIS standards intelligence and pre-compliance platform (SIH26107).\n\n"
        + DISCLAIMER
    ),
    docs_url="/docs",
    openapi_url="/openapi.json",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_origin_regex=settings.cors_origin_regex,
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(health.router, prefix=settings.api_prefix)
app.include_router(products.router, prefix=settings.api_prefix)
app.include_router(standards.router, prefix=settings.api_prefix)
app.include_router(evidence.router, prefix=settings.api_prefix)
app.include_router(certification.router, prefix=settings.api_prefix)
app.include_router(hallmarking.router, prefix=settings.api_prefix)
app.include_router(chat.router, prefix=settings.api_prefix)


@app.exception_handler(ConnectionFailure)
@app.exception_handler(ServerSelectionTimeoutError)
def handle_db_down(request: Request, exc: Exception) -> JSONResponse:
    """MongoDB unreachable - almost always a dropped network or a paused cluster."""
    del request, exc
    return JSONResponse(status_code=503, content={"detail": UNREACHABLE_DETAIL})


@app.exception_handler(DatabaseNotConfigured)
def handle_db_unconfigured(request: Request, exc: DatabaseNotConfigured) -> JSONResponse:
    del request
    return JSONResponse(status_code=503, content={"detail": str(exc)})


@app.exception_handler(PyMongoError)
def handle_db_error(request: Request, exc: PyMongoError) -> JSONResponse:
    del request
    logger.exception("Database error: %s", exc)
    return JSONResponse(
        status_code=500, content={"detail": "A database error occurred while serving this request."}
    )


@app.get("/")
def root() -> dict:
    return {
        "app": settings.app_name,
        "docs": "/docs",
        "health": f"{settings.api_prefix}/health",
        "disclaimer": DISCLAIMER,
    }
