"""
shopsense/evaluation/metrics.py
Metric calculations for the evaluation dashboard.
All metrics are deterministic — no second LLM judge.
"""
from __future__ import annotations

from typing import Dict, List, Optional
from shopsense.schemas import EvaluationResult


def precision_at_k(retrieved: List[str], expected: List[str], k: int) -> float:
    """Fraction of top-k retrieved IDs that are in expected."""
    if not expected or not retrieved:
        return 0.0
    top_k = retrieved[:k]
    hits = sum(1 for pid in top_k if pid in expected)
    return hits / k if k > 0 else 0.0


def recall_at_k(retrieved: List[str], expected: List[str], k: int) -> float:
    """Fraction of expected IDs found in top-k retrieved."""
    if not expected:
        return 1.0   # vacuously true — nothing was expected
    top_k = retrieved[:k]
    hits = sum(1 for pid in expected if pid in top_k)
    return hits / len(expected)


def compute_result_metrics(
    retrieved: List[str],
    expected: List[str],
) -> Dict[str, Optional[float]]:
    """Return precision@5, recall@5, recall@10, and hit@1."""
    if not expected:
        return {"precision_at_5": None, "recall_at_5": None, "recall_at_10": None, "hit_at_1": None}

    return {
        "precision_at_5": round(precision_at_k(retrieved, expected, 5), 4),
        "recall_at_5": round(recall_at_k(retrieved, expected, 5), 4),
        "recall_at_10": round(recall_at_k(retrieved, expected, 10), 4),
        "hit_at_1": 1.0 if (retrieved and retrieved[0] in expected) else 0.0,
    }


def aggregate_metrics(results: List[EvaluationResult]) -> Dict:
    """Compute aggregate metrics over all evaluation results."""
    total = len(results)
    if total == 0:
        return {"total": 0}

    passed = sum(1 for r in results if r.passed)
    guardrail_cases = [r for r in results if r.guardrail_expected]
    retrieval_cases = [r for r in results if not r.guardrail_expected and r.expected_product_ids]

    # Recall@5 for retrieval cases
    recall_vals = [r.recall for r in retrieval_cases if r.recall is not None]
    avg_recall = sum(recall_vals) / len(recall_vals) if recall_vals else None

    # Precision@5 for retrieval cases
    prec_vals = [r.precision for r in retrieval_cases if r.precision is not None]
    avg_precision = sum(prec_vals) / len(prec_vals) if prec_vals else None

    # Guardrail accuracy
    guardrail_passed = sum(1 for r in guardrail_cases if r.passed)

    # By category
    by_category: Dict[str, Dict] = {}
    for r in results:
        cat = r.category
        if cat not in by_category:
            by_category[cat] = {"total": 0, "passed": 0}
        by_category[cat]["total"] += 1
        if r.passed:
            by_category[cat]["passed"] += 1

    return {
        "total": total,
        "passed": passed,
        "failed": total - passed,
        "overall_pass_rate": round(passed / total, 4) if total else 0.0,
        "retrieval_cases": len(retrieval_cases),
        "avg_recall_at_5": round(avg_recall, 4) if avg_recall is not None else None,
        "avg_precision_at_5": round(avg_precision, 4) if avg_precision is not None else None,
        "guardrail_cases": len(guardrail_cases),
        "guardrail_pass_rate": round(guardrail_passed / len(guardrail_cases), 4) if guardrail_cases else None,
        "by_category": by_category,
    }
