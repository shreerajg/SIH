"""Portable JSON column type (MySQL JSON / SQLite TEXT)."""
from __future__ import annotations

import json
from typing import Any, Optional

from sqlalchemy import JSON, Text
from sqlalchemy.types import TypeDecorator


class JSONType(TypeDecorator):
    """JSON column that behaves identically on MySQL 8 and SQLite."""

    impl = Text
    cache_ok = True

    def load_dialect_impl(self, dialect):
        if dialect.name == "mysql":
            return dialect.type_descriptor(JSON())
        return dialect.type_descriptor(Text())

    def process_bind_param(self, value: Any, dialect) -> Optional[Any]:
        if value is None:
            return None
        if dialect.name == "mysql":
            return value
        return json.dumps(value, ensure_ascii=False, default=str)

    def process_result_value(self, value: Any, dialect) -> Any:
        if value is None:
            return None
        if dialect.name == "mysql":
            return value
        if isinstance(value, (dict, list)):
            return value
        try:
            return json.loads(value)
        except (TypeError, ValueError):
            return None
