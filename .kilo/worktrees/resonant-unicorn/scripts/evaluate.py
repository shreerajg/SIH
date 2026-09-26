#!/usr/bin/env python
"""Retrieval and guardrail evaluation.

    python scripts/evaluate.py [--out data/evaluation/results.json]

Measures, against data/evaluation/evaluation_queries.json:

* standard discovery       - Recall@1, Recall@3, MRR, supporting-standard recall
* clause retrieval         - Recall@5, MRR
* consumer lookup          - exact-match accuracy including correct not-found behaviour
* consumer description search - ranked-suggestion accuracy for a typed product name
* regulatory               - accuracy against the structured records
* gap analysis             - the rule engine reaches the expected status for known evidence
* amendment impact         - an amendment maps to exactly the requirements its clause backs
* grounding                - citation validity and unsupported-claim rate

Nothing here is estimated. If a number cannot be computed it is reported as
null rather than filled in.
"""
from __future__ import annotations

import argparse
import json
from contextlib import contextmanager
import sys
import time
from pathlib import Path
from typing import Any, Dict, List, Sequence

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "backend"))

from app.db.base import session_scope  # noqa: E402
from app.llm.service import get_llm  # noqa: E402
from app.rag.service import RAGService  # noqa: E402
from app.search.embeddings import get_embedding_backend  # noqa: E402
from app.search.hybrid import get_retriever  # noqa: E402
from app.search.vector_store import get_vector_store  # noqa: E402
from app.services import corpus as corpus_service  # noqa: E402
from app.services.consumer import ConsumerService  # noqa: E402
from app.services.product_understanding import ProductUnderstandingService  # noqa: E402
from app.services.regulatory import resolve_regulatory_status  # noqa: E402
from app.services.taxonomy import CATEGORY_TO_CORPUS  # noqa: E402


@contextmanager
def corpus_mode(mode: str):
    """Evaluate a ground-truth set against the corpus it was written for.

    The demo ground truth in evaluation_queries.json was assigned by reading
    the synthetic documents, before any official document existed. Scoring it
    against a MIXED corpus measures something else entirely: an official BIS
    Product Manual outranking its synthetic stand-in for the same product is
    the system working, but it reads as a Recall@1 failure. The demo sections
    are therefore scored against the demo corpus, and the verified sections
    against the whole corpus, so each number means what it claims to.
    """
    previous = corpus_service.settings.corpus_mode
    corpus_service.settings.corpus_mode = mode
    try:
        yield
    finally:
        corpus_service.settings.corpus_mode = previous


def _reciprocal_rank(ranked: Sequence[str], target: str) -> float:
    for index, value in enumerate(ranked, start=1):
        if value == target:
            return 1.0 / index
    return 0.0


def _mean(values: Sequence[float]) -> float:
    return round(sum(values) / len(values), 4) if values else 0.0


def evaluate_standard_discovery(db, cases: List[Dict[str, Any]]) -> Dict[str, Any]:
    understanding = ProductUnderstandingService()
    retriever = get_retriever()
    hits_at_1, hits_at_3, rr, supporting_recall = [], [], [], []
    details = []

    for case in cases:
        profile = understanding._deterministic_profile(case["query"])  # noqa: SLF001
        query_text = " ".join(
            [profile["name"], case["query"], profile["category"]]
            + [f"{k} {v}" for k, v in profile["attributes"].items()]
        )
        candidates = retriever.discover_standards(
            db, query_text,
            category_hint=CATEGORY_TO_CORPUS.get(profile["category"], ""),
            limit=8,
        )
        ranked = [c.standard.id for c in candidates]
        expected = case["expected_primary"]

        hits_at_1.append(1.0 if ranked[:1] == [expected] else 0.0)
        hits_at_3.append(1.0 if expected in ranked[:3] else 0.0)
        rr.append(_reciprocal_rank(ranked, expected))

        supporting = case.get("expected_supporting") or []
        if supporting:
            found = sum(1 for s in supporting if s in ranked)
            supporting_recall.append(found / len(supporting))

        details.append(
            {
                "id": case["id"],
                "expected": expected,
                "ranked": ranked[:5],
                "hit_at_1": bool(hits_at_1[-1]),
                "hit_at_3": bool(hits_at_3[-1]),
            }
        )

    return {
        "cases": len(cases),
        "recall_at_1": _mean(hits_at_1),
        "recall_at_3": _mean(hits_at_3),
        "mrr": _mean(rr),
        "supporting_standard_recall": _mean(supporting_recall) if supporting_recall else None,
        "details": details,
    }


def evaluate_clause_retrieval(db, cases: List[Dict[str, Any]], k: int = 5) -> Dict[str, Any]:
    retriever = get_retriever()
    recall, rr, details = [], [], []

    for case in cases:
        hits = retriever.retrieve_clauses(db, case["question"], case["standard_ids"], k=k)
        retrieved = [h.clause.clause_number for h in hits]
        expected = set(case["expected_clauses"])

        found = expected & set(retrieved)
        recall.append(len(found) / len(expected) if expected else 0.0)
        rr.append(max((_reciprocal_rank(retrieved, e) for e in expected), default=0.0))

        details.append(
            {
                "id": case["id"],
                "expected": sorted(expected),
                "retrieved": retrieved,
                "found": sorted(found),
            }
        )

    return {
        "cases": len(cases),
        "k": k,
        f"recall_at_{k}": _mean(recall),
        "mrr": _mean(rr),
        "details": details,
    }


def evaluate_consumer(db, cases: List[Dict[str, Any]]) -> Dict[str, Any]:
    service = ConsumerService()
    correct, details = [], []
    for case in cases:
        result = service.lookup(db, case["query"])
        ok = result.found == case["expect_found"] and (
            not case["expect_found"] or result.standard.id == case["expected_standard"]
        )
        correct.append(1.0 if ok else 0.0)
        details.append(
            {
                "id": case["id"],
                "query": case["query"],
                "expected": case["expected_standard"],
                "actual": result.standard.id if result.standard else None,
                "correct": ok,
            }
        )
    return {"cases": len(cases), "accuracy": _mean(correct), "details": details}


def evaluate_regulatory(db, cases: List[Dict[str, Any]]) -> Dict[str, Any]:
    correct, details, false_voluntary = [], [], 0
    for case in cases:
        status = resolve_regulatory_status(db, case["standard_id"])
        ok = status.status.value == case["expected_status"]
        correct.append(1.0 if ok else 0.0)
        if case["expected_status"] == "UNABLE_TO_VERIFY" and status.status.value == "VOLUNTARY":
            false_voluntary += 1
        details.append(
            {
                "id": case["id"],
                "standard_id": case["standard_id"],
                "expected": case["expected_status"],
                "actual": status.status.value,
                "correct": ok,
            }
        )
    return {
        "cases": len(cases),
        "accuracy": _mean(correct),
        "absence_reported_as_voluntary": false_voluntary,
        "details": details,
    }


def evaluate_consumer_description_search(db, cases: List[Dict[str, Any]]) -> Dict[str, Any]:
    """A consumer who types a product name, not a code (Priority 11): the top
    ranked suggestion must be the standard a human would pick."""
    service = ConsumerService()
    correct, details = [], []
    for case in cases:
        result = service.lookup(db, case["query"])
        top = result.suggestions[0].id if result.suggestions else None
        ok = top == case["expected_top_suggestion"]
        correct.append(1.0 if ok else 0.0)
        details.append(
            {
                "id": case["id"],
                "query": case["query"],
                "expected": case["expected_top_suggestion"],
                "actual": top,
                "correct": ok,
            }
        )
    return {"cases": len(cases), "accuracy": _mean(correct), "details": details}


def evaluate_gap_analysis(db, cases: List[Dict[str, Any]]) -> Dict[str, Any]:
    """The compliance gap analyzer is a rule engine: given the same product and
    evidence, it must always reach the same status for the same requirement."""
    import uuid as uuid_module

    from app.compliance.gap_analyzer import ComplianceGapAnalyzer
    from app.models import ProductEvidence
    from app.services.standard_discovery import StandardDiscoveryService

    understanding = ProductUnderstandingService()
    discovery = StandardDiscoveryService()
    analyzer = ComplianceGapAnalyzer()

    correct, details = [], []
    for case in cases:
        profile = understanding.analyze(case["description"])
        product = understanding.persist(db, profile)
        discovery.discover(db, product)

        for item in case.get("evidence", []):
            db.add(
                ProductEvidence(
                    id=f"ev-{uuid_module.uuid4().hex[:12]}",
                    product_id=product.id,
                    evidence_type=item["evidence_type"],
                    name=item["name"],
                    value=item.get("value", ""),
                )
            )
        db.commit()

        raw = analyzer.analyze(db, product)
        actual = {r["requirement"].requirement_code: r["status"].value for r in raw["results"]}

        mismatches = {}
        for code, expected_status in case["expected_statuses"].items():
            got = actual.get(code)
            if got != expected_status:
                mismatches[code] = {"expected": expected_status, "actual": got}
        correct.append(1.0 if not mismatches else 0.0)
        details.append({"id": case["id"], "mismatches": mismatches, "correct": not mismatches})

    return {"cases": len(cases), "accuracy": _mean(correct), "details": details}


def evaluate_amendment_impact(db, cases: List[Dict[str, Any]]) -> Dict[str, Any]:
    """An amendment must map to the exact requirements its clause backs -
    never more (a fabricated relevance) and never fewer (a missed one)."""
    from app.services.amendments import AmendmentService

    service = AmendmentService()
    correct, details = [], []
    for case in cases:
        impacts = service.for_standards(db, [case["standard_id"]])
        match = next(
            (i for i in impacts if i.amendment.amendment_number == case["amendment_number"]),
            None,
        )
        actual = sorted(match.affected_requirements) if match else None
        expected = sorted(case["expected_affected_requirements"])
        ok = actual == expected
        correct.append(1.0 if ok else 0.0)
        details.append(
            {
                "id": case["id"],
                "standard_id": case["standard_id"],
                "expected": expected,
                "actual": actual,
                "correct": ok,
            }
        )
    return {"cases": len(cases), "accuracy": _mean(correct), "details": details}


def evaluate_verified_discovery(db, cases: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Does the official BIS document for each golden scenario actually surface?

    Scored as "within top N" rather than Recall@1 on purpose: the corpus is
    MIXED, so a synthetic document legitimately competes for the top slot. What
    matters is that the real, verified document is present and findable.
    """
    from app.services.standard_discovery import StandardDiscoveryService

    understanding = ProductUnderstandingService()
    discovery = StandardDiscoveryService()
    hits, details = [], []
    for case in cases:
        product = understanding.persist(db, understanding.analyze(case["query"]))
        result = discovery.discover(db, product)
        ranked = [m["standard"].id for m in result["matches"]]
        top_n = case.get("within_top", 3)
        found = case["expected_document"] in ranked[:top_n]
        hits.append(1.0 if found else 0.0)
        details.append(
            {
                "id": case["id"],
                "expected": case["expected_document"],
                "within_top": top_n,
                "ranked": ranked[:top_n],
                "correct": found,
            }
        )
    return {"cases": len(cases), "accuracy": _mean(hits), "details": details}


def evaluate_verified_regulatory(db, cases: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Regulatory status for official documents, and the notification behind it.

    Also checks the rule that matters most: a document with no Quality Control
    Order must report UNABLE_TO_VERIFY, never VOLUNTARY.
    """
    correct, details, false_voluntary = [], [], 0
    for case in cases:
        status = resolve_regulatory_status(db, case["standard_id"])
        ok = status.status.value == case["expected_status"]
        expected_notification = case.get("expected_notification") or ""
        if ok and expected_notification:
            ok = (status.notification_number or "") == expected_notification
        if case["expected_status"] == "UNABLE_TO_VERIFY" and status.status.value == "VOLUNTARY":
            false_voluntary += 1
        correct.append(1.0 if ok else 0.0)
        details.append(
            {
                "id": case["id"],
                "standard_id": case["standard_id"],
                "expected": case["expected_status"],
                "actual": status.status.value,
                "expected_notification": expected_notification,
                "actual_notification": status.notification_number or "",
                "correct": ok,
            }
        )
    return {
        "cases": len(cases),
        "accuracy": _mean(correct),
        "absence_reported_as_voluntary": false_voluntary,
        "details": details,
    }


def evaluate_verified_consumer(db, cases: List[Dict[str, Any]]) -> Dict[str, Any]:
    """A consumer typing a real IS number must reach the official document."""
    service = ConsumerService()
    correct, details = [], []
    for case in cases:
        result = service.lookup(db, case["query"])
        ok = result.found == case["expect_found"] and (
            not case["expect_found"] or result.standard.id == case["expected_standard"]
        )
        correct.append(1.0 if ok else 0.0)
        details.append(
            {
                "id": case["id"],
                "query": case["query"],
                "expected": case["expected_standard"],
                "actual": result.standard.id if result.standard else None,
                "correct": ok,
            }
        )
    return {"cases": len(cases), "accuracy": _mean(correct), "details": details}


def evaluate_verified_document_typing(db, cases: List[Dict[str, Any]]) -> Dict[str, Any]:
    """No official document in this corpus is a full Indian Standard.

    If a Product Manual or a Quality Control Order were typed "standard", its
    text could be cited as standard clause text. This is the check that the
    distinction survives ingestion.
    """
    from app.models import Standard

    correct, details = [], []
    for case in cases:
        row = db.get(Standard, case["standard_id"])
        actual = row.document_type if row else None
        ok = actual == case["expected_document_type"]
        correct.append(1.0 if ok else 0.0)
        details.append(
            {
                "id": case["id"],
                "standard_id": case["standard_id"],
                "expected": case["expected_document_type"],
                "actual": actual,
                "correct": ok,
            }
        )
    return {"cases": len(cases), "accuracy": _mean(correct), "details": details}


def evaluate_grounding(db, cases: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Every displayed claim must cite retrieved evidence, LLM or not."""
    rag = RAGService()
    total_claims = 0
    invalid_citations = 0
    unsupported = 0
    answerable = 0
    details = []

    for case in cases:
        response = rag.answer(
            db, case["question"], standard_ids=case["standard_ids"]
        )
        retrieved = set(response.evidence_shield.retrieved_chunk_ids)
        bad = 0
        for claim in response.claims:
            total_claims += 1
            if not claim.source_chunk_ids:
                unsupported += 1
                continue
            outside = [c for c in claim.source_chunk_ids if c not in retrieved]
            if outside:
                invalid_citations += len(outside)
                bad += 1
        answerable += 1 if response.answerable else 0
        details.append(
            {
                "id": case["id"],
                "answerable": response.answerable,
                "claims": len(response.claims),
                "claims_with_invalid_citation": bad,
                "rejected_by_shield": len(response.evidence_shield.rejected_claims),
            }
        )

    return {
        "cases": len(cases),
        "total_displayed_claims": total_claims,
        "citation_validity": 1.0 if total_claims and invalid_citations == 0 else (
            round(1 - invalid_citations / total_claims, 4) if total_claims else None
        ),
        "unsupported_claim_rate": round(unsupported / total_claims, 4) if total_claims else None,
        "answerable_rate": _mean([1.0 if d["answerable"] else 0.0 for d in details]),
        "details": details,
    }


def _demo(db, func, cases):
    """Score a demo-corpus ground-truth set against the demo corpus only."""
    with corpus_mode("DEMO"):
        return func(db, cases)


def main() -> int:
    parser = argparse.ArgumentParser(description="Evaluate retrieval and guardrails")
    parser.add_argument("--queries", default=str(REPO_ROOT / "data" / "evaluation" / "evaluation_queries.json"))
    parser.add_argument("--out", default=str(REPO_ROOT / "data" / "evaluation" / "results.json"))
    args = parser.parse_args()

    payload = json.loads(Path(args.queries).read_text(encoding="utf-8"))
    started = time.time()

    db = session_scope()
    try:
        results = {
            "generated_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
            "corpus": payload.get("corpus", "demo"),
            "environment": {
                "embedding_backend": get_embedding_backend().name,
                "vector_backend": get_vector_store().name,
                "llm": get_llm().status(),
            },
            # Demo ground truth, scored against the demo corpus it describes.
            "standard_discovery": _demo(
                db, evaluate_standard_discovery, payload["standard_discovery"]
            ),
            "clause_retrieval": _demo(db, evaluate_clause_retrieval, payload["clause_retrieval"]),
            "consumer_lookup": evaluate_consumer(db, payload["consumer_lookup"]),
            "consumer_description_search": evaluate_consumer_description_search(
                db, payload.get("consumer_description_search", [])
            ),
            "regulatory": evaluate_regulatory(db, payload["regulatory"]),
            "gap_analysis": evaluate_gap_analysis(db, payload.get("gap_analysis", [])),
            "amendment_impact": evaluate_amendment_impact(db, payload.get("amendment_impact", [])),
            "grounding": evaluate_grounding(db, payload["clause_retrieval"]),
            "verified_discovery": evaluate_verified_discovery(
                db, payload.get("verified_discovery", [])
            ),
            "verified_regulatory": evaluate_verified_regulatory(
                db, payload.get("verified_regulatory", [])
            ),
            "verified_consumer_lookup": evaluate_verified_consumer(
                db, payload.get("verified_consumer_lookup", [])
            ),
            "verified_document_typing": evaluate_verified_document_typing(
                db, payload.get("verified_document_typing", [])
            ),
        }
    finally:
        db.close()

    results["duration_seconds"] = round(time.time() - started, 2)

    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(results, indent=2), encoding="utf-8")

    sd = results["standard_discovery"]
    cr = results["clause_retrieval"]
    print("\n=== SIH26107 evaluation =========================================")
    print("demo sections scored against the DEMO corpus; verified sections against the full corpus")
    print(f"corpus: {results['corpus']}   embeddings: {results['environment']['embedding_backend']}")
    print(f"llm: {'yes (' + results['environment']['llm']['provider'] + ')' if results['environment']['llm']['available'] else 'no (retrieval-only)'}")
    print("-----------------------------------------------------------------")
    print(f"Standard discovery  Recall@1 {sd['recall_at_1']:.2f}  Recall@3 {sd['recall_at_3']:.2f}  MRR {sd['mrr']:.2f}  ({sd['cases']} cases)")
    if sd["supporting_standard_recall"] is not None:
        print(f"                    supporting-standard recall {sd['supporting_standard_recall']:.2f}")
    print(f"Clause retrieval    Recall@{cr['k']} {cr['recall_at_' + str(cr['k'])]:.2f}  MRR {cr['mrr']:.2f}  ({cr['cases']} cases)")
    print(f"Consumer lookup     accuracy {results['consumer_lookup']['accuracy']:.2f}  ({results['consumer_lookup']['cases']} cases)")
    cds = results["consumer_description_search"]
    if cds["cases"]:
        print(f"Consumer desc. search accuracy {cds['accuracy']:.2f}  ({cds['cases']} cases)")
    print(f"Regulatory status   accuracy {results['regulatory']['accuracy']:.2f}  "
          f"absence-as-voluntary {results['regulatory']['absence_reported_as_voluntary']}")
    ga = results["gap_analysis"]
    if ga["cases"]:
        print(f"Gap analysis        accuracy {ga['accuracy']:.2f}  ({ga['cases']} cases)")
    ai = results["amendment_impact"]
    if ai["cases"]:
        print(f"Amendment impact    accuracy {ai['accuracy']:.2f}  ({ai['cases']} cases)")
    for key, label in [
        ("verified_discovery", "Verified discovery"),
        ("verified_regulatory", "Verified regulatory"),
        ("verified_consumer_lookup", "Verified consumer"),
        ("verified_document_typing", "Verified doc typing"),
    ]:
        section = results.get(key) or {}
        if section.get("cases"):
            print(f"{label:19} accuracy {section['accuracy']:.2f}  ({section['cases']} cases)")
    g = results["grounding"]
    print(f"Grounding           citation validity {g['citation_validity']}  "
          f"unsupported-claim rate {g['unsupported_claim_rate']}  ({g['total_displayed_claims']} claims)")
    print("-----------------------------------------------------------------")
    print(f"Written to {out}  ({results['duration_seconds']}s)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
