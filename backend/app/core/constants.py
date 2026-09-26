"""Domain vocabularies shared by services, schemas and tests.

These are deliberately closed enumerations. The LLM is never allowed to invent
a status value: every generated status is validated against these sets before
it can reach the API surface.
"""
from __future__ import annotations

from enum import Enum


class Relevance(str, Enum):
    HIGH = "HIGH"
    MEDIUM = "MEDIUM"
    LOW = "LOW"
    NEEDS_VERIFICATION = "NEEDS_VERIFICATION"


class ComplianceStatus(str, Enum):
    SUPPORTED = "SUPPORTED"
    POTENTIAL_GAP = "POTENTIAL_GAP"
    TEST_REQUIRED = "TEST_REQUIRED"
    DOCUMENT_REQUIRED = "DOCUMENT_REQUIRED"
    UNKNOWN = "UNKNOWN"
    NOT_APPLICABLE = "NOT_APPLICABLE"
    OFFICIAL_VERIFICATION_REQUIRED = "OFFICIAL_VERIFICATION_REQUIRED"


#: Statuses that count towards the pre-compliance readiness denominator.
ASSESSABLE_STATUSES = {
    ComplianceStatus.SUPPORTED,
    ComplianceStatus.POTENTIAL_GAP,
    ComplianceStatus.TEST_REQUIRED,
    ComplianceStatus.DOCUMENT_REQUIRED,
    ComplianceStatus.UNKNOWN,
    ComplianceStatus.OFFICIAL_VERIFICATION_REQUIRED,
}


class RegulatoryStatus(str, Enum):
    MANDATORY = "MANDATORY"
    UPCOMING = "UPCOMING"          # notified, effective date still in the future
    WITHDRAWN = "WITHDRAWN"
    VOLUNTARY = "VOLUNTARY"        # only ever set from an explicit stored record
    UNABLE_TO_VERIFY = "UNABLE_TO_VERIFY"


class VerificationState(str, Enum):
    """How well a shown fact is backed by the ingested BIS corpus.

    Deliberately has no NOT_APPLICABLE or INVALID: the platform can show that a
    fact is supported, but absence of a source is not evidence that the fact is
    false, so the worst case is always "unable to verify".
    """

    VERIFIED = "VERIFIED"
    PARTIALLY_VERIFIED = "PARTIALLY_VERIFIED"
    UNABLE_TO_VERIFY = "UNABLE_TO_VERIFY"


class SchemeApplicability(str, Enum):
    """Closed vocabulary for certification-scheme applicability.

    There is deliberately no "NOT_APPLICABLE": a stored record can confirm that
    a scheme applies, but nothing in the corpus can prove a negative, so the
    absence of evidence is reported as UNABLE_TO_VERIFY.
    """

    APPLICABLE = "APPLICABLE"
    LIKELY = "LIKELY"
    UNABLE_TO_VERIFY = "UNABLE_TO_VERIFY"


class QueryType(str, Enum):
    STANDARD_DISCOVERY = "STANDARD_DISCOVERY"
    STANDARD_EXPLANATION = "STANDARD_EXPLANATION"
    CLAUSE_LOOKUP = "CLAUSE_LOOKUP"
    TEST_REQUIREMENT = "TEST_REQUIREMENT"
    MARKING_REQUIREMENT = "MARKING_REQUIREMENT"
    MANDATORY_STATUS = "MANDATORY_STATUS"
    CERTIFICATION_QUERY = "CERTIFICATION_QUERY"
    AMENDMENT_QUERY = "AMENDMENT_QUERY"
    PRODUCT_GAP_ANALYSIS = "PRODUCT_GAP_ANALYSIS"
    CONSUMER_LOOKUP = "CONSUMER_LOOKUP"
    #: Jewellery hallmarking (gold/silver purity, HUID, A&H centres).
    #: Distinct from CERTIFICATION_QUERY: hallmarking runs under the
    #: Hallmarking Regulations, not the Conformity Assessment schemes.
    HALLMARKING_QUERY = "HALLMARKING_QUERY"
    RELATED_STANDARD = "RELATED_STANDARD"
    GENERAL_STANDARD_QA = "GENERAL_STANDARD_QA"


class RequirementCategory(str, Enum):
    SAFETY = "safety"
    TESTING = "testing"
    MARKING = "marking"
    MATERIAL = "material"
    PERFORMANCE = "performance"
    CONSTRUCTION = "construction"
    DOCUMENTATION = "documentation"


class EvidenceType(str, Enum):
    TEST_REPORT = "test_report"
    DECLARED_VALUE = "declared_value"
    DOCUMENT = "document"
    MARKING_ARTWORK = "marking_artwork"
    MATERIAL_CERTIFICATE = "material_certificate"
    INSPECTION = "inspection"


class SourceType(str, Enum):
    OFFICIAL = "official"          # retrieved from bis.gov.in / gazette
    DEMO = "demo"                  # synthetic corpus authored for this prototype
    USER_UPLOAD = "user_upload"


class DatasetStatus(str, Enum):
    VERIFIED = "verified"
    DEMO = "demo"


class CorpusMode(str, Enum):
    """Which documents the platform is allowed to answer from.

    DEMO     - only the labelled synthetic corpus (DEMO-STD-nnn).
    VERIFIED - only official documents with is_verified=true. If none are
               loaded, the platform answers nothing rather than silently
               falling back to synthetic data.
    MIXED    - both, with verified records preferred in ranking and demo
               records labelled everywhere they appear.
    """

    DEMO = "DEMO"
    VERIFIED = "VERIFIED"
    MIXED = "MIXED"


class DocumentType(str, Enum):
    STANDARD = "standard"
    AMENDMENT = "amendment"
    QCO = "qco"
    GAZETTE = "gazette"
    PRODUCT_MANUAL = "product_manual"
    SIT = "scheme_of_inspection_and_testing"
    REGULATORY = "regulatory"
    #: Official BIS hallmarking material (scheme brief, FAQs, jeweller and
    #: A&H centre guidance). Distinct from a product standard: it governs
    #: precious-metal articles under the Hallmarking Regulations, not a QCO.
    HALLMARKING = "hallmarking"
    OTHER = "other"


class AmendmentRelevance(str, Enum):
    """How an amendment relates to one specific product. Deliberately cautious:
    the platform never concludes that a product has become non-compliant."""

    LIKELY_RELEVANT = "LIKELY_RELEVANT"
    REQUIRES_REVIEW = "REQUIRES_REVIEW"
    NO_DIRECT_MATCH_FOUND = "NO_DIRECT_MATCH_FOUND"
    UNABLE_TO_VERIFY = "UNABLE_TO_VERIFY"


class UploadCategory(str, Enum):
    DATASHEET = "datasheet"
    TEST_REPORT = "test_report"
    PRODUCT_LABEL = "product_label"
    TECHNICAL_DOCUMENT = "technical_document"
    CERTIFICATE = "certificate"
    OTHER = "other"


class ProtectionArea(str, Enum):
    """Consumer-facing 'what does this protect me from' categories."""

    ELECTRICAL_SAFETY = "Electrical Safety"
    MECHANICAL_SAFETY = "Mechanical Safety"
    THERMAL_SAFETY = "Thermal Safety"
    FIRE_OVERHEATING = "Fire / Overheating"
    MATERIAL_SAFETY = "Material Safety"
    MARKING_INSTRUCTIONS = "Marking / Instructions"
    PERFORMANCE = "Performance"


class CoverageStatus(str, Enum):
    COVERED = "COVERED"
    NOT_FOUND = "NOT_FOUND"
    NOT_APPLICABLE = "NOT_APPLICABLE"
    UNABLE_TO_VERIFY = "UNABLE_TO_VERIFY"


#: Phrase used everywhere the platform cannot substantiate a claim.
UNVERIFIED_MESSAGE = "Unable to verify from the currently available documents."

DISCLAIMER = (
    "This platform provides standards intelligence and pre-compliance assistance. "
    "It does not issue BIS certification or replace official conformity assessment."
)
