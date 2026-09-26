"""Typed collection helpers.

A thin layer over PyMongo that converts between raw documents and the
dataclasses in :mod:`app.models.documents`. It is not an ORM and does not try
to be one: there is no identity map, no unit of work and no lazy loading. A
call here is one call to MongoDB.

Callers hold a ``Database`` handle (the old code held a SQLAlchemy ``Session``)
and reach a collection through the module-level accessors at the bottom::

    standard = standards(db).get("DEMO-STD-001")
    rows = clauses(db).find({"standard_id": standard.id}, sort=[("clause_number", 1)])
    products(db).save(product)
"""
from __future__ import annotations

from typing import Any, Dict, Generic, Iterable, List, Optional, Sequence, Tuple, Type, TypeVar

from pymongo.database import Database

from app.models.documents import (
    Amendment,
    CertificationProcess,
    CertificationScheme,
    ComplianceRequirement,
    Document,
    HallmarkingCentre,
    HallmarkingKnowledge,
    IngestionRun,
    Product,
    ProductEvidence,
    QCO,
    SchemeProductEntry,
    Standard,
    StandardClause,
    StandardRelationship,
)

T = TypeVar("T", bound=Document)

# Collection names. Kept identical to the old table names so the mapping stays
# obvious and the migration script can be read side by side with the schema.
STANDARDS = "standards"
STANDARD_CLAUSES = "standard_clauses"
COMPLIANCE_REQUIREMENTS = "compliance_requirements"
QCOS = "qcos"
AMENDMENTS = "amendments"
STANDARD_RELATIONSHIPS = "standard_relationships"
PRODUCTS = "products"
PRODUCT_EVIDENCE = "product_evidence"
INGESTION_RUNS = "ingestion_runs"
CERTIFICATION_SCHEMES = "certification_schemes"
SCHEME_PRODUCT_INDEX = "scheme_product_index"
CERTIFICATION_PROCESSES = "certification_processes"
HALLMARKING_KNOWLEDGE = "hallmarking_knowledge"
HALLMARKING_CENTRES = "hallmarking_centres"


class Repository(Generic[T]):
    def __init__(self, db: Database, name: str, model: Type[T]) -> None:
        self.collection = db[name]
        self.model = model

    # -- reads -----------------------------------------------------------
    def get(self, _id: Optional[str]) -> Optional[T]:
        if not _id:
            return None
        return self.model.from_doc(self.collection.find_one({"_id": _id}))

    def find_one(self, filt: Dict[str, Any]) -> Optional[T]:
        return self.model.from_doc(self.collection.find_one(filt))

    def find(
        self,
        filt: Optional[Dict[str, Any]] = None,
        *,
        sort: Optional[Sequence[Tuple[str, int]]] = None,
        limit: int = 0,
    ) -> List[T]:
        cursor = self.collection.find(filt or {})
        if sort:
            cursor = cursor.sort(list(sort))
        if limit:
            cursor = cursor.limit(limit)
        return [self.model.from_doc(doc) for doc in cursor]

    def project(
        self,
        fields: Sequence[str],
        filt: Optional[Dict[str, Any]] = None,
    ) -> List[Dict[str, Any]]:
        """Raw documents with only ``fields`` - for index building, where
        materialising full dataclasses would be wasteful."""
        projection = {f: 1 for f in fields}
        return list(self.collection.find(filt or {}, projection))

    def count(self, filt: Optional[Dict[str, Any]] = None) -> int:
        return self.collection.count_documents(filt or {})

    def distinct(self, field: str, filt: Optional[Dict[str, Any]] = None) -> List[Any]:
        return self.collection.distinct(field, filt or {})

    def exists(self, _id: str) -> bool:
        return self.collection.count_documents({"_id": _id}, limit=1) > 0

    # -- writes ----------------------------------------------------------
    def save(self, obj: T) -> T:
        """Insert or replace one document, keyed by its existing string id."""
        doc = obj.to_doc()
        self.collection.replace_one({"_id": doc["_id"]}, doc, upsert=True)
        return obj

    def save_many(self, objs: Iterable[T]) -> int:
        docs = [o.to_doc() for o in objs]
        if not docs:
            return 0
        self.collection.insert_many(docs)
        return len(docs)

    def update_fields(self, _id: str, values: Dict[str, Any]) -> None:
        self.collection.update_one({"_id": _id}, {"$set": values})

    def delete_many(self, filt: Dict[str, Any]) -> int:
        return self.collection.delete_many(filt).deleted_count

    def delete_one(self, _id: str) -> int:
        return self.collection.delete_one({"_id": _id}).deleted_count


# -- accessors ----------------------------------------------------------------

def standards(db: Database) -> Repository[Standard]:
    return Repository(db, STANDARDS, Standard)


def clauses(db: Database) -> Repository[StandardClause]:
    return Repository(db, STANDARD_CLAUSES, StandardClause)


def requirements(db: Database) -> Repository[ComplianceRequirement]:
    return Repository(db, COMPLIANCE_REQUIREMENTS, ComplianceRequirement)


def qcos(db: Database) -> Repository[QCO]:
    return Repository(db, QCOS, QCO)


def amendments(db: Database) -> Repository[Amendment]:
    return Repository(db, AMENDMENTS, Amendment)


def relationships(db: Database) -> Repository[StandardRelationship]:
    return Repository(db, STANDARD_RELATIONSHIPS, StandardRelationship)


def products(db: Database) -> Repository[Product]:
    return Repository(db, PRODUCTS, Product)


def evidence(db: Database) -> Repository[ProductEvidence]:
    return Repository(db, PRODUCT_EVIDENCE, ProductEvidence)


def ingestion_runs(db: Database) -> Repository[IngestionRun]:
    return Repository(db, INGESTION_RUNS, IngestionRun)


def schemes(db: Database) -> Repository[CertificationScheme]:
    return Repository(db, CERTIFICATION_SCHEMES, CertificationScheme)


def scheme_products(db: Database) -> Repository[SchemeProductEntry]:
    return Repository(db, SCHEME_PRODUCT_INDEX, SchemeProductEntry)


def processes(db: Database) -> Repository[CertificationProcess]:
    return Repository(db, CERTIFICATION_PROCESSES, CertificationProcess)


def hallmarking(db: Database) -> Repository[HallmarkingKnowledge]:
    return Repository(db, HALLMARKING_KNOWLEDGE, HallmarkingKnowledge)


def hallmarking_centres(db: Database) -> Repository[HallmarkingCentre]:
    return Repository(db, HALLMARKING_CENTRES, HallmarkingCentre)
