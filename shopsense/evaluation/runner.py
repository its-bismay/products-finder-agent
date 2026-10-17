"""
shopsense/evaluation/runner.py
Loads the evaluation benchmark, executes each case through the live
application workflow, and returns structured results.

- Does NOT overwrite data/evaluation_cases.json.
- Results are saved to reports/evaluation_results.json.
- One failed case does not stop the rest of the run.
"""
from __future__ import annotations

import json
import logging
import traceback
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

from shopsense.catalog.loader import verify_product_ids
from shopsense.config import EVALUATION_CASES_PATH, REPORTS_DIR
from shopsense.evaluation.metrics import aggregate_metrics, compute_result_metrics
from shopsense.guardrails.input_checks import check_input
from shopsense.schemas import EvaluationCase, EvaluationResult

logger = logging.getLogger(__name__)

RESULTS_PATH = REPORTS_DIR / "evaluation_results.json"


# ---------------------------------------------------------------------------
# Benchmark loading
# ---------------------------------------------------------------------------

def load_evaluation_cases() -> List[EvaluationCase]:
    """Load and validate evaluation_cases.json. Raises if file is missing."""
    if not EVALUATION_CASES_PATH.exists():
        raise FileNotFoundError(f"Evaluation cases not found at {EVALUATION_CASES_PATH}")
    with open(EVALUATION_CASES_PATH, encoding="utf-8") as f:
        raw = json.load(f)
    cases: List[EvaluationCase] = []
    for item in raw:
        try:
            cases.append(EvaluationCase(**item))
        except Exception as e:
            logger.warning("Skipping malformed evaluation case %s: %s", item.get("case_id"), e)
    return cases


# ---------------------------------------------------------------------------
# Individual case execution
# ---------------------------------------------------------------------------

def _run_retrieval_case(case: EvaluationCase) -> EvaluationResult:
    """Run a catalog-retrieval evaluation case through the full agent pipeline."""
    from shopsense.agent.shopping_agent import run_shopping_agent

    try:
        agent_response, retrieved_products = run_shopping_agent(case.user_query)
        actual_ids = agent_response.product_ids

        # Check whether expected IDs exist in the database
        expected_in_db = verify_product_ids(case.expected_product_ids)
        missing_from_db = [pid for pid in case.expected_product_ids if pid not in expected_in_db]

        if missing_from_db:
            failure_reason = f"Expected IDs not in database: {missing_from_db}"
            return EvaluationResult(
                case_id=case.case_id,
                category=case.category,
                user_query=case.user_query,
                expected_product_ids=case.expected_product_ids,
                actual_product_ids=actual_ids,
                passed=False,
                failure_reason=failure_reason,
                guardrail_triggered=False,
                guardrail_expected=False,
            )

        # Compute retrieval metrics
        m = compute_result_metrics(actual_ids, case.expected_product_ids)

        # "Passed" for retrieval: recall@5 >= 0.5 OR at least one expected ID retrieved
        recall = m.get("recall_at_5") or 0.0
        hit = any(pid in actual_ids for pid in case.expected_product_ids)
        passed = recall >= 0.5 or hit
        failure_reason = None if passed else f"recall@5={recall:.2f}, no expected ID retrieved"

        return EvaluationResult(
            case_id=case.case_id,
            category=case.category,
            user_query=case.user_query,
            expected_product_ids=case.expected_product_ids,
            actual_product_ids=actual_ids,
            passed=passed,
            failure_reason=failure_reason,
            guardrail_triggered=False,
            guardrail_expected=False,
            precision=m.get("precision_at_5"),
            recall=m.get("recall_at_5"),
        )

    except Exception as e:
        logger.error("Error running case %s: %s", case.case_id, traceback.format_exc())
        return EvaluationResult(
            case_id=case.case_id,
            category=case.category,
            user_query=case.user_query,
            expected_product_ids=case.expected_product_ids,
            actual_product_ids=[],
            passed=False,
            failure_reason="Exception during execution",
            error=str(e),
        )


def _run_guardrail_case(case: EvaluationCase) -> EvaluationResult:
    """Run a guardrail test case. Passes if the input guardrail fires."""
    try:
        check = check_input(case.user_query)
        guardrail_fired = not check.allowed
        passed = guardrail_fired  # guardrail should have triggered

        return EvaluationResult(
            case_id=case.case_id,
            category=case.category,
            user_query=case.user_query,
            expected_product_ids=[],
            actual_product_ids=[],
            passed=passed,
            failure_reason=None if passed else "Guardrail did not trigger when expected",
            guardrail_triggered=guardrail_fired,
            guardrail_expected=True,
        )
    except Exception as e:
        logger.error("Error running guardrail case %s: %s", case.case_id, e)
        return EvaluationResult(
            case_id=case.case_id,
            category=case.category,
            user_query=case.user_query,
            expected_product_ids=[],
            actual_product_ids=[],
            passed=False,
            failure_reason="Exception",
            error=str(e),
            guardrail_expected=True,
        )


def _run_no_results_case(case: EvaluationCase) -> EvaluationResult:
    """Run a no-results case. Passes if retrieved products list is empty."""
    from shopsense.agent.shopping_agent import run_shopping_agent

    try:
        agent_response, products = run_shopping_agent(case.user_query)
        passed = len(products) == 0
        return EvaluationResult(
            case_id=case.case_id,
            category=case.category,
            user_query=case.user_query,
            expected_product_ids=[],
            actual_product_ids=agent_response.product_ids,
            passed=passed,
            failure_reason=None if passed else f"Got {len(products)} products, expected 0",
        )
    except Exception as e:
        return EvaluationResult(
            case_id=case.case_id,
            category=case.category,
            user_query=case.user_query,
            expected_product_ids=[],
            actual_product_ids=[],
            passed=False,
            failure_reason="Exception",
            error=str(e),
        )


# ---------------------------------------------------------------------------
# Main runner
# ---------------------------------------------------------------------------

_GUARDRAIL_CATEGORIES = {
    "guardrails_out_of_scope",
    "guardrails_safety",
    "guardrails_prompt_injection",
}


def run_evaluation(
    progress_callback: Optional[Callable[[int, int, str], None]] = None,
) -> Dict[str, Any]:
    """
    Execute all evaluation cases. Returns a structured results dict.
    Never modifies evaluation_cases.json.
    """
    cases = load_evaluation_cases()
    results: List[EvaluationResult] = []

    for i, case in enumerate(cases):
        if progress_callback:
            progress_callback(i, len(cases), case.case_id)

        if case.guardrail_trigger or case.category in _GUARDRAIL_CATEGORIES:
            result = _run_guardrail_case(case)
        elif case.category == "no_results_handling":
            result = _run_no_results_case(case)
        else:
            result = _run_retrieval_case(case)

        results.append(result)

    if progress_callback:
        progress_callback(len(cases), len(cases), "done")

    aggregated = aggregate_metrics(results)
    timestamp = datetime.now(timezone.utc).isoformat()

    output = {
        "run_timestamp": timestamp,
        "summary": aggregated,
        "results": [r.model_dump() for r in results],
    }

    # Save to reports/ (NOT to evaluation_cases.json)
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    with open(RESULTS_PATH, "w", encoding="utf-8") as f:
        json.dump(output, f, indent=2, ensure_ascii=False)

    logger.info("Evaluation complete. Results saved to %s", RESULTS_PATH)
    return output


def load_latest_results() -> Optional[Dict[str, Any]]:
    """Load previously saved evaluation results, or None if unavailable."""
    if not RESULTS_PATH.exists():
        return None
    try:
        with open(RESULTS_PATH, encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        logger.warning("Could not load evaluation results: %s", e)
        return None
