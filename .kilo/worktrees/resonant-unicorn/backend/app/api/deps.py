"""Shared FastAPI dependencies and helpers."""
from __future__ import annotations

from typing import Iterator

from fastapi import Depends, HTTPException, status
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import Session

from app.db.base import get_db
from app.models import Product


def db_session() -> Iterator[Session]:
    try:
        yield from get_db()
    except OperationalError as exc:  # pragma: no cover - infra dependent
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=(
                "The database is not reachable. Start MySQL (docker compose up -d mysql) "
                "or set DATABASE_URL, then run scripts/setup_demo.py."
            ),
        ) from exc


def get_product(product_id: str, db: Session = Depends(db_session)) -> Product:
    product = db.get(Product, product_id)
    if product is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"No product with id '{product_id}'. Analyse a product first.",
        )
    return product
