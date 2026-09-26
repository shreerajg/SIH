"""Regression coverage for scripts/evaluate.py.

The evaluation script is the platform's honesty check against ground truth
that was assigned by *reading the source documents*, not by running the
system - see data/evaluation/evaluation_queries.json. These tests exercise
the fast, non-embedding eval functions directly (consumer description search,
gap analysis, amendment impact) so a regression in the scoring logic itself -
not just the underlying feature - is caught without paying for a full
sentence-transformers-backed run of the whole script.
"""
from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
DATASET = REPO_ROOT / "data" / "evaluation" / "evaluation_queries.json"


def _load_evaluate_module():
    spec = importlib.util.spec_from_file_location(
        "evaluate_script", REPO_ROOT / "scripts" / "evaluate.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def evaluate_module():
    return _load_evaluate_module()


@pytest.fixture(scope="module")
def dataset():
    return json.loads(DATASET.read_text(encoding="utf-8"))


def test_reciprocal_rank_and_mean_are_correct(evaluate_module):
    assert evaluate_module._reciprocal_rank(["A", "B", "C"], "B") == 0.5
    assert evaluate_module._reciprocal_rank(["A", "B", "C"], "Z") == 0.0
    assert evaluate_module._mean([1.0, 0.0, 1.0, 1.0]) == 0.75
    assert evaluate_module._mean([]) == 0.0


def test_evaluation_dataset_has_the_new_categories(dataset):
    for key in ("consumer_description_search", "gap_analysis", "amendment_impact"):
        assert key in dataset
        assert len(dataset[key]) > 0, f"{key} must not be an empty placeholder"


def test_consumer_description_search_eval_scores_real_matches(db, evaluate_module, dataset):
    result = evaluate_module.evaluate_consumer_description_search(
        db, dataset["consumer_description_search"]
    )
    assert result["cases"] == len(dataset["consumer_description_search"])
    assert result["accuracy"] == 1.0, result["details"]


def test_gap_analysis_eval_scores_the_rule_engine(db, evaluate_module, dataset):
    result = evaluate_module.evaluate_gap_analysis(db, dataset["gap_analysis"])
    assert result["cases"] == len(dataset["gap_analysis"])
    assert result["accuracy"] == 1.0, result["details"]


def test_amendment_impact_eval_scores_requirement_mapping(db, evaluate_module, dataset):
    result = evaluate_module.evaluate_amendment_impact(db, dataset["amendment_impact"])
    assert result["cases"] == len(dataset["amendment_impact"])
    assert result["accuracy"] == 1.0, result["details"]


def test_a_wrong_expectation_is_actually_caught(evaluate_module, db):
    """Prove the scorer fails a genuinely wrong case, not just passes everything."""
    bogus = [{"id": "X", "standard_id": "DEMO-STD-001", "amendment_number": "Amendment No. 1",
              "expected_affected_requirements": ["NOT-A-REAL-CODE"]}]
    result = evaluate_module.evaluate_amendment_impact(db, bogus)
    assert result["accuracy"] == 0.0
    assert result["details"][0]["correct"] is False
