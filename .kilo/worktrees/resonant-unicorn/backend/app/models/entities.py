"""ORM models for the BIS standards intelligence platform.

Every knowledge record carries provenance (source_type, source_url,
is_verified, is_mock) so the UI can always tell the user whether a fact came
from an official document or from the clearly labelled demo corpus.
"""
from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, List, Optional

from sqlalchemy import (
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.db.types import JSONType


def _now() -> datetime:
    return datetime.utcnow()


class Standard(Base):
    __tablename__ = "standards"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    is_number: Mapped[str] = mapped_column(String(64), index=True)
    normalized_number: Mapped[str] = mapped_column(String(64), index=True)
    title: Mapped[str] = mapped_column(String(512))
    year: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    version: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    scope: Mapped[str] = mapped_column(Text, default="")
    plain_summary: Mapped[str] = mapped_column(Text, default="")
    product_category: Mapped[str] = mapped_column(String(128), index=True, default="")
    keywords: Mapped[List[str]] = mapped_column(JSONType, default=list)
    covered_areas: Mapped[List[str]] = mapped_column(JSONType, default=list)
    status: Mapped[str] = mapped_column(String(32), default="active")
    source_url: Mapped[str] = mapped_column(String(512), default="")
    source_type: Mapped[str] = mapped_column(String(32), default="demo")
    document_id: Mapped[str] = mapped_column(String(96), default="", index=True)
    document_type: Mapped[str] = mapped_column(String(48), default="standard")
    document_path: Mapped[str] = mapped_column(String(512), default="")
    retrieved_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    is_verified: Mapped[bool] = mapped_column(Boolean, default=False)
    #: True for the synthetic demonstration corpus. is_mock is kept as the
    #: legacy alias so existing rows and callers keep working.
    is_demo: Mapped[bool] = mapped_column(Boolean, default=True, index=True)
    is_mock: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_now)

    clauses: Mapped[List["StandardClause"]] = relationship(
        back_populates="standard", cascade="all, delete-orphan"
    )
    requirements: Mapped[List["ComplianceRequirement"]] = relationship(
        back_populates="standard", cascade="all, delete-orphan"
    )
    qcos: Mapped[List["QCO"]] = relationship(
        back_populates="standard", cascade="all, delete-orphan"
    )
    amendments: Mapped[List["Amendment"]] = relationship(
        back_populates="standard", cascade="all, delete-orphan"
    )


class StandardClause(Base):
    __tablename__ = "standard_clauses"
    __table_args__ = (Index("ix_clause_standard_clause", "standard_id", "clause_number"),)

    id: Mapped[str] = mapped_column(String(96), primary_key=True)
    standard_id: Mapped[str] = mapped_column(ForeignKey("standards.id"), index=True)
    section_number: Mapped[str] = mapped_column(String(32), default="")
    clause_number: Mapped[str] = mapped_column(String(32), default="")
    heading: Mapped[str] = mapped_column(String(512), default="")
    text: Mapped[str] = mapped_column(Text, default="")
    page_number: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    clause_type: Mapped[str] = mapped_column(String(48), default="requirement")
    chunk_id: Mapped[str] = mapped_column(String(96), unique=True, index=True)
    token_estimate: Mapped[int] = mapped_column(Integer, default=0)
    #: Structured table payload when this chunk came from a table, else empty.
    table_json: Mapped[Dict[str, Any]] = mapped_column(JSONType, default=dict)
    is_table: Mapped[bool] = mapped_column(Boolean, default=False)

    standard: Mapped[Standard] = relationship(back_populates="clauses")


class Product(Base):
    __tablename__ = "products"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    name: Mapped[str] = mapped_column(String(256))
    description: Mapped[str] = mapped_column(Text, default="")
    category: Mapped[str] = mapped_column(String(128), default="")
    attributes_json: Mapped[Dict[str, Any]] = mapped_column(JSONType, default=dict)
    missing_fields_json: Mapped[List[str]] = mapped_column(JSONType, default=list)
    profile_source: Mapped[str] = mapped_column(String(32), default="deterministic")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=_now, onupdate=_now)

    matches: Mapped[List["ProductStandardMatch"]] = relationship(
        back_populates="product", cascade="all, delete-orphan"
    )
    evidence: Mapped[List["ProductEvidence"]] = relationship(
        back_populates="product", cascade="all, delete-orphan"
    )
    results: Mapped[List["ComplianceResult"]] = relationship(
        back_populates="product", cascade="all, delete-orphan"
    )


class ProductStandardMatch(Base):
    __tablename__ = "product_standard_matches"
    __table_args__ = (
        UniqueConstraint("product_id", "standard_id", name="uq_product_standard"),
    )

    id: Mapped[str] = mapped_column(String(96), primary_key=True)
    product_id: Mapped[str] = mapped_column(ForeignKey("products.id"), index=True)
    standard_id: Mapped[str] = mapped_column(ForeignKey("standards.id"), index=True)
    relevance: Mapped[str] = mapped_column(String(32), default="NEEDS_VERIFICATION")
    score: Mapped[float] = mapped_column(Float, default=0.0)
    reason: Mapped[str] = mapped_column(Text, default="")
    matched_attributes_json: Mapped[List[Dict[str, Any]]] = mapped_column(
        JSONType, default=list
    )
    scope_evidence: Mapped[str] = mapped_column(Text, default="")
    evidence_chunk_ids: Mapped[List[str]] = mapped_column(JSONType, default=list)
    explanation_source: Mapped[str] = mapped_column(String(32), default="deterministic")
    #: Retrieval score breakdown (semantic/bm25/metadata + flags) behind
    #: `score`, kept so the "how was this ranked" visualisation survives a
    #: page reload instead of only appearing right after a live re-run.
    signals_json: Mapped[Dict[str, Any]] = mapped_column(JSONType, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_now)

    product: Mapped[Product] = relationship(back_populates="matches")
    standard: Mapped[Standard] = relationship()


class ComplianceRequirement(Base):
    __tablename__ = "compliance_requirements"

    id: Mapped[str] = mapped_column(String(96), primary_key=True)
    standard_id: Mapped[str] = mapped_column(ForeignKey("standards.id"), index=True)
    clause_id: Mapped[Optional[str]] = mapped_column(
        ForeignKey("standard_clauses.id"), nullable=True
    )
    requirement_code: Mapped[str] = mapped_column(String(64), default="")
    category: Mapped[str] = mapped_column(String(48), default="safety")
    requirement_text: Mapped[str] = mapped_column(Text, default="")
    evidence_type: Mapped[str] = mapped_column(String(48), default="document")
    severity: Mapped[str] = mapped_column(String(24), default="major")
    # Optional machine-checkable rule, e.g.
    # {"attribute": "voltage", "operator": "between", "value": [200, 250]}
    check_rule_json: Mapped[Dict[str, Any]] = mapped_column(JSONType, default=dict)
    applies_when_json: Mapped[Dict[str, Any]] = mapped_column(JSONType, default=dict)
    source_clause_number: Mapped[str] = mapped_column(String(32), default="")

    standard: Mapped[Standard] = relationship(back_populates="requirements")
    clause: Mapped[Optional[StandardClause]] = relationship()


class ProductEvidence(Base):
    __tablename__ = "product_evidence"

    id: Mapped[str] = mapped_column(String(96), primary_key=True)
    product_id: Mapped[str] = mapped_column(ForeignKey("products.id"), index=True)
    evidence_type: Mapped[str] = mapped_column(String(48), default="declared_value")
    name: Mapped[str] = mapped_column(String(256), default="")
    value: Mapped[str] = mapped_column(Text, default="")
    file_path: Mapped[str] = mapped_column(String(512), default="")
    original_filename: Mapped[str] = mapped_column(String(256), default="")
    content_type: Mapped[str] = mapped_column(String(128), default="")
    size_bytes: Mapped[int] = mapped_column(Integer, default=0)
    upload_category: Mapped[str] = mapped_column(String(48), default="other")
    #: Text extracted from an uploaded PDF/label, used for evidence matching.
    extracted_text: Mapped[str] = mapped_column(Text, default="")
    #: Structured values pulled out of the document (model, ratings, results).
    extracted_fields_json: Mapped[Dict[str, Any]] = mapped_column(JSONType, default=dict)
    extraction_status: Mapped[str] = mapped_column(String(32), default="none")
    metadata_json: Mapped[Dict[str, Any]] = mapped_column(JSONType, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_now)

    product: Mapped[Product] = relationship(back_populates="evidence")


class ComplianceResult(Base):
    __tablename__ = "compliance_results"
    __table_args__ = (
        UniqueConstraint("product_id", "requirement_id", name="uq_product_requirement"),
    )

    id: Mapped[str] = mapped_column(String(96), primary_key=True)
    product_id: Mapped[str] = mapped_column(ForeignKey("products.id"), index=True)
    requirement_id: Mapped[str] = mapped_column(
        ForeignKey("compliance_requirements.id"), index=True
    )
    status: Mapped[str] = mapped_column(String(48), default="UNKNOWN")
    reason: Mapped[str] = mapped_column(Text, default="")
    evidence_id: Mapped[Optional[str]] = mapped_column(
        ForeignKey("product_evidence.id"), nullable=True
    )
    confidence: Mapped[float] = mapped_column(Float, default=0.0)
    recommended_action: Mapped[str] = mapped_column(Text, default="")
    decided_by: Mapped[str] = mapped_column(String(32), default="rule_engine")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_now)

    product: Mapped[Product] = relationship(back_populates="results")
    requirement: Mapped[ComplianceRequirement] = relationship()
    evidence: Mapped[Optional[ProductEvidence]] = relationship()


class QCO(Base):
    """Quality Control Order / regulatory record.

    Regulatory status is answered from this table only - never from the LLM.
    """

    __tablename__ = "qcos"

    id: Mapped[str] = mapped_column(String(96), primary_key=True)
    standard_id: Mapped[str] = mapped_column(ForeignKey("standards.id"), index=True)
    product_name: Mapped[str] = mapped_column(String(256), default="")
    qco_name: Mapped[str] = mapped_column(String(512), default="")
    notification_number: Mapped[str] = mapped_column(String(128), default="")
    notification_date: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    effective_date: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    status: Mapped[str] = mapped_column(String(32), default="MANDATORY")
    scheme: Mapped[str] = mapped_column(String(256), default="")
    ministry: Mapped[str] = mapped_column(String(256), default="")
    source_url: Mapped[str] = mapped_column(String(512), default="")
    document_id: Mapped[str] = mapped_column(String(96), default="")
    retrieved_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    is_verified: Mapped[bool] = mapped_column(Boolean, default=False)
    is_demo: Mapped[bool] = mapped_column(Boolean, default=True)
    is_mock: Mapped[bool] = mapped_column(Boolean, default=True)

    standard: Mapped[Standard] = relationship(back_populates="qcos")


class Amendment(Base):
    __tablename__ = "amendments"

    id: Mapped[str] = mapped_column(String(96), primary_key=True)
    standard_id: Mapped[str] = mapped_column(ForeignKey("standards.id"), index=True)
    amendment_number: Mapped[str] = mapped_column(String(64), default="")
    publication_date: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    effective_date: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    affected_clause: Mapped[str] = mapped_column(String(64), default="")
    summary: Mapped[str] = mapped_column(Text, default="")
    old_text: Mapped[str] = mapped_column(Text, default="")
    new_text: Mapped[str] = mapped_column(Text, default="")
    source_url: Mapped[str] = mapped_column(String(512), default="")
    document_id: Mapped[str] = mapped_column(String(96), default="")
    retrieved_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    is_verified: Mapped[bool] = mapped_column(Boolean, default=False)
    is_demo: Mapped[bool] = mapped_column(Boolean, default=True)
    is_mock: Mapped[bool] = mapped_column(Boolean, default=True)

    standard: Mapped[Standard] = relationship(back_populates="amendments")


class StandardRelationship(Base):
    __tablename__ = "standard_relationships"

    id: Mapped[str] = mapped_column(String(96), primary_key=True)
    source_standard_id: Mapped[str] = mapped_column(ForeignKey("standards.id"), index=True)
    target_standard_id: Mapped[str] = mapped_column(ForeignKey("standards.id"), index=True)
    relationship_type: Mapped[str] = mapped_column(String(64), default="related")
    evidence: Mapped[str] = mapped_column(Text, default="")

    source_standard: Mapped[Standard] = relationship(foreign_keys=[source_standard_id])
    target_standard: Mapped[Standard] = relationship(foreign_keys=[target_standard_id])


class IngestionRun(Base):
    """Bookkeeping so the UI can show what is actually in the corpus."""

    __tablename__ = "ingestion_runs"

    id: Mapped[str] = mapped_column(String(96), primary_key=True)
    started_at: Mapped[datetime] = mapped_column(DateTime, default=_now)
    finished_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    documents: Mapped[int] = mapped_column(Integer, default=0)
    chunks: Mapped[int] = mapped_column(Integer, default=0)
    embedding_backend: Mapped[str] = mapped_column(String(64), default="")
    vector_backend: Mapped[str] = mapped_column(String(64), default="")
    notes: Mapped[str] = mapped_column(Text, default="")
