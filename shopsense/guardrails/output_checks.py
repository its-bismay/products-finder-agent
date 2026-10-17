"""
shopsense/guardrails/output_checks.py
Output-side validation: verifies product IDs, fact consistency, and response schema.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

from shopsense.catalog.loader import get_products_by_ids, verify_product_ids
from shopsense.schemas import AgentResponse, Product

logger = logging.getLogger(__name__)


@dataclass
class OutputCheckResult:
    valid: bool
    verified_product_ids: List[str] = field(default_factory=list)
    unverified_ids: List[str] = field(default_factory=list)
    issues: List[str] = field(default_factory=list)


def validate_agent_response(response: AgentResponse) -> OutputCheckResult:
    """
    Validate an AgentResponse before sending it to the UI.
    Checks:
    - All returned product_ids exist in the database.
    - Response has a non-empty answer.
    - Schema is structurally valid (Pydantic already guarantees type safety).
    """
    issues: List[str] = []

    # Validate product IDs against the live database
    verified = verify_product_ids(response.product_ids)
    unverified = [pid for pid in response.product_ids if pid not in verified]

    if unverified:
        issues.append(f"Product IDs not found in catalog: {unverified}")
        logger.warning("Output guardrail: unverified product IDs: %s", unverified)

    if not response.answer:
        issues.append("Agent response has an empty answer field.")

    return OutputCheckResult(
        valid=len(issues) == 0,
        verified_product_ids=verified,
        unverified_ids=unverified,
        issues=issues,
    )


def verify_products_against_constraints(
    products: List[Product],
    max_price: Optional[float] = None,
    min_rating: Optional[float] = None,
    max_width_cm: Optional[float] = None,
    max_height_cm: Optional[float] = None,
) -> Tuple[List[Product], List[str]]:
    """
    Verify that displayed products satisfy hard constraints.
    Removes products that violate constraints and reports the issue.
    """
    passed: List[Product] = []
    issues: List[str] = []

    for p in products:
        violations: List[str] = []

        if max_price is not None and p.price is not None and p.price > max_price:
            violations.append(f"{p.product_id}: price {p.price} > max {max_price}")

        if min_rating is not None and p.average_rating is not None and p.average_rating < min_rating:
            violations.append(f"{p.product_id}: rating {p.average_rating} < min {min_rating}")

        if max_width_cm is not None and p.width_cm is not None and p.width_cm > max_width_cm:
            violations.append(f"{p.product_id}: width {p.width_cm} > max {max_width_cm}")

        if max_height_cm is not None and p.height_cm is not None and p.height_cm > max_height_cm:
            violations.append(f"{p.product_id}: height {p.height_cm} > max {max_height_cm}")

        if violations:
            issues.extend(violations)
            logger.warning("Output guardrail removed product due to constraint violations: %s", violations)
        else:
            passed.append(p)

    return passed, issues
