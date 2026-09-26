"""FastAPI application entry point."""
from __future__ import annotations

import logging

from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy.exc import OperationalError, SQLAlchemyError

from app.api import evidence, health, products, standards
from app.core.config import settings
from app.core.constants import DISCLAIMER
from app.db.base import active_backend, create_all
from app.db.migrations import run_migrations

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-7s %(name)s: %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger(__name__)

@asynccontextmanager
async def lifespan(_: FastAPI):
    try:
        create_all()
        # Additive-only: brings a database created before an upgrade up to date
        # without dropping anything. Safe to run on every start.
        report = run_migrations()
        if report.changed:
            logger.info("Schema migration: %s", report.summary())
        logger.info("Database ready (%s)", active_backend())
    except Exception as exc:  # pragma: no cover - infra dependent
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


@app.exception_handler(OperationalError)
def handle_db_down(request: Request, exc: OperationalError) -> JSONResponse:
    del request, exc
    return JSONResponse(
        status_code=503,
        content={
            "detail": (
                "The database is not reachable. Start MySQL (docker compose up -d mysql) "
                "or set DATABASE_URL, then run scripts/setup_demo.py."
            )
        },
    )


@app.exception_handler(SQLAlchemyError)
def handle_db_error(request: Request, exc: SQLAlchemyError) -> JSONResponse:
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
