"""Shared FastAPI dependencies and helpers."""
from __future__ import annotations

from typing import Iterator

from fastapi import Depends, HTTPException, status
from pymongo.database import Database
from pymongo.errors import ConnectionFailure, ServerSelectionTimeoutError

from app.db.mongo import DatabaseNotConfigured, get_db
from app.db.repositories import products
from app.models import Product

#: Shown whenever MongoDB cannot be reached. The platform has no local
#: fallback by design - answering from a different corpus because the network
#: is down would be worse than not answering.
UNREACHABLE_DETAIL = (
    "The MongoDB database is not reachable. Check your network connection and that "
    "MONGO_URI in backend/.env points at a running cluster, then try again."
)


def db_session() -> Iterator[Database]:
    try:
        yield from get_db()
    except (ConnectionFailure, ServerSelectionTimeoutError) as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=UNREACHABLE_DETAIL,
        ) from exc
    except DatabaseNotConfigured as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=str(exc),
        ) from exc


def get_product(product_id: str, db: Database = Depends(db_session)) -> Product:
    product = products(db).get(product_id)
    if product is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"No product with id '{product_id}'. Analyse a product first.",
        )
    return product
