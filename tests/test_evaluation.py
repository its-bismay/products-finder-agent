"""
tests/test_evaluation.py
Automated unit tests for benchmark loading, metric calculation, and report persistence.
"""
import json
import pytest

from shopsense.config import EVALUATION_CASES_PATH, REPORTS_DIR
from shopsense.evaluation.metrics import (
    aggregate_metrics,
    compute_result_metrics,
    precision_at_k,
    recall_at_k,
)
from shopsense.evaluation.runner import load_evaluation_cases, run_evaluation
from shopsense.schemas import EvaluationCase, EvaluationResult


def test_evaluation_benchmark_loads_unmodified():
    """Verify that data/evaluation_cases.json exists, contains 20 cases, and loads cleanly."""
    cases = load_evaluation_cases()
    assert len(cases) == 20, f"Expected 20 benchmark test cases, found {len(cases)}"
    for c in cases:
        assert isinstance(c, EvaluationCase)
        assert c.case_id, "Each case must have a case_id"
        assert c.category, "Each case must have a category"
        assert c.user_query, "Each case must have a user_query"


def test_precision_at_k_calculation():
    """Verify precision@k calculation behavior."""
    retrieved = ["P1", "P2", "P3", "P4", "P5"]
    expected = ["P2", "P5", "P8"]
    
    # 2 hits out of top 5 -> 2/5 = 0.4
    assert precision_at_k(retrieved, expected, 5) == 0.4
    # Empty retrieved -> 0.0
    assert precision_at_k([], expected, 5) == 0.0
    # Empty expected -> 0.0
    assert precision_at_k(retrieved, [], 5) == 0.0


def test_recall_at_k_calculation():
    """Verify recall@k calculation behavior."""
    retrieved = ["P1", "P2", "P3", "P4", "P5"]
    expected = ["P2", "P5"]
    
    # 2 hits out of 2 expected -> 2/2 = 1.0
    assert recall_at_k(retrieved, expected, 5) == 1.0
    # 1 hit out of 2 expected in top 2 -> 1/2 = 0.5
    assert recall_at_k(retrieved, expected, 2) == 0.5
    # Empty expected -> 1.0 (vacuously true)
    assert recall_at_k(retrieved, [], 5) == 1.0
    # Empty retrieved -> 0.0
    assert recall_at_k([], expected, 5) == 0.0


def test_compute_result_metrics_dictionary():
    """Verify compute_result_metrics structure."""
    retrieved = ["P1", "P2", "P3"]
    expected = ["P1", "P4"]
    res = compute_result_metrics(retrieved, expected)
    assert res["hit_at_1"] == 1.0
    assert res["recall_at_5"] == 0.5
    assert res["precision_at_5"] == 0.2


def test_aggregate_metrics_calculation():
    """Verify aggregate_metrics handles mixed results."""
    results = [
        EvaluationResult(
            case_id="C1",
            category="direct_search",
            user_query="candles",
            expected_product_ids=["P1"],
            actual_product_ids=["P1"],
            passed=True,
            recall=1.0,
            precision=1.0,
        ),
        EvaluationResult(
            case_id="C2",
            category="guardrails_safety",
            user_query="explosives",
            expected_product_ids=[],
            actual_product_ids=[],
            passed=True,
            guardrail_expected=True,
            guardrail_triggered=True,
        ),
        EvaluationResult(
            case_id="C3",
            category="budget_filter",
            user_query="rug under 10",
            expected_product_ids=[],
            actual_product_ids=["P9"],
            passed=False,
            failure_reason="Returned items over budget",
        ),
    ]
    summary = aggregate_metrics(results)
    assert summary["total"] == 3
    assert summary["passed"] == 2
    assert summary["failed"] == 1
    assert summary["guardrail_cases"] == 1
    assert summary["guardrail_pass_rate"] == 1.0


def test_benchmark_preserves_evaluation_cases_file():
    """Verify that running the evaluation does NOT overwrite data/evaluation_cases.json."""
    with open(EVALUATION_CASES_PATH, "r", encoding="utf-8") as f:
        original_content = f.read()

    # Run the evaluation suite
    output = run_evaluation()
    assert "summary" in output
    assert "results" in output

    with open(EVALUATION_CASES_PATH, "r", encoding="utf-8") as f:
        after_content = f.read()

    assert original_content == after_content, "data/evaluation_cases.json must NOT be modified!"
    
    # Verify results file was saved to reports/
    report_file = REPORTS_DIR / "evaluation_results.json"
    assert report_file.exists()
