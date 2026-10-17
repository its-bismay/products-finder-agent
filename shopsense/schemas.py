"""
shopsense/schemas.py
Pydantic data models used across the application.
"""
from __future__ import annotations

from typing import Any, List, Optional
from pydantic import BaseModel, Field, field_validator


# ---------------------------------------------------------------------------
# Canonical product record (output of catalog loader)
# ---------------------------------------------------------------------------
class Product(BaseModel):
    """A single product record loaded from the SQLite catalog."""

    product_id: str
    item_number: Optional[str] = None
    product_name: str
    display_name: str = ""
    description: Optional[str] = None
    summary: Optional[str] = None
    features: Optional[str] = None
    product_type: Optional[str] = None
    category_1: Optional[str] = None
    category_2: Optional[str] = None
    category_3: Optional[str] = None
    category_4: Optional[str] = None
    price: Optional[float] = None
    currency: Optional[str] = None
    average_rating: Optional[float] = None
    reviews_count: Optional[int] = None
    width_cm: Optional[float] = None
    depth_cm: Optional[float] = None
    height_cm: Optional[float] = None
    measurements_text: Optional[str] = None
    material_and_care: Optional[str] = None
    primary_image: Optional[str] = None
    product_url: Optional[str] = None
    product_details: Optional[str] = None

    @field_validator("product_id", mode="before")
    @classmethod
    def coerce_to_str(cls, v: Any) -> str:
        return str(v)

    @field_validator("display_name", mode="before")
    @classmethod
    def default_display_name(cls, v: Any, info: Any) -> str:
        if v:
            return str(v)
        # Fall back to product_name if available in data
        return str(info.data.get("product_name", "")) if hasattr(info, "data") else ""

    @property
    def price_display(self) -> str:
        if self.price is None:
            return "Price not available"
        sym = "₹" if self.currency == "INR" else (self.currency or "")
        return f"{sym}{self.price:,.0f}"

    @property
    def rating_display(self) -> str:
        if self.average_rating is None:
            return "Not rated"
        return f"{self.average_rating:.1f} ★ ({self.reviews_count or 0} reviews)"


# ---------------------------------------------------------------------------
# Structured shopping intent (output of Stage A — query understanding)
# ---------------------------------------------------------------------------
class ShoppingIntent(BaseModel):
    """Structured representation of what the customer wants."""

    user_goal: str = Field(default="", description="One-sentence summary of the customer's shopping goal")
    search_terms: List[str] = Field(default_factory=list, description="Key search terms")
    product_name: Optional[str] = Field(None, description="Specific IKEA product series name if mentioned")
    category: Optional[str] = Field(None, description="Top-level product category")
    subcategory: Optional[str] = Field(None, description="Product subcategory")
    minimum_price: Optional[float] = Field(None, description="Minimum price constraint")
    maximum_price: Optional[float] = Field(None, description="Maximum price constraint in INR")
    currency: Optional[str] = Field(None, description="Currency code if specified")
    minimum_rating: Optional[float] = Field(None, description="Minimum acceptable average rating (0-5)")
    maximum_width_cm: Optional[float] = Field(None, description="Maximum width in cm (hard constraint)")
    maximum_depth_cm: Optional[float] = Field(None, description="Maximum depth in cm (hard constraint)")
    maximum_height_cm: Optional[float] = Field(None, description="Maximum height in cm (hard constraint)")
    approximate_width_cm: Optional[float] = Field(None, description="Approximate desired width in cm (soft preference)")
    approximate_height_cm: Optional[float] = Field(None, description="Approximate desired height in cm (soft preference)")
    preferred_materials: List[str] = Field(default_factory=list, description="Preferred materials")
    preferred_colors: List[str] = Field(default_factory=list, description="Preferred colors")
    preferred_styles: List[str] = Field(default_factory=list, description="Style keywords like minimalist, modern, rustic")
    sort_by: Optional[str] = Field(None, description="Sorting preference: price_asc, price_desc, rating_desc, relevance")
    requires_clarification: bool = Field(False, description="True if the request is ambiguous and needs a follow-up")
    clarification_question: Optional[str] = Field(None, description="Single focused question to resolve ambiguity")
    is_shopping_request: bool = Field(True, description="False if the query is not a product-shopping request")


# ---------------------------------------------------------------------------
# Final agent response (output of Stage B)
# ---------------------------------------------------------------------------
class AgentResponse(BaseModel):
    """Structured response returned by the shopping agent."""

    answer: str = Field(description="Natural-language response to show the customer")
    product_ids: List[str] = Field(default_factory=list, description="Verified product IDs from the catalog")
    clarification_question: Optional[str] = Field(None)
    no_results: bool = Field(False)
    limitations: Optional[str] = Field(None, description="Notes about catalog limitations or caveats")
    retrieval_method: str = Field("keyword", description="'semantic' or 'keyword'")


# ---------------------------------------------------------------------------
# Evaluation structures
# ---------------------------------------------------------------------------
class EvaluationCase(BaseModel):
    """A single test case from evaluation_cases.json."""

    case_id: str
    category: str
    user_query: str
    intent: str
    expected_filters: Optional[dict] = None
    expected_product_ids: List[str] = Field(default_factory=list)
    expected_behavior: str
    guardrail_trigger: bool = False

    @field_validator("expected_product_ids", mode="before")
    @classmethod
    def coerce_ids_to_str(cls, v: Any) -> List[str]:
        return [str(x) for x in (v or [])]


class EvaluationResult(BaseModel):
    """Result for a single evaluation case."""

    case_id: str
    category: str
    user_query: str
    expected_product_ids: List[str]
    actual_product_ids: List[str]
    passed: bool
    failure_reason: Optional[str] = None
    guardrail_triggered: bool = False
    guardrail_expected: bool = False
    precision: Optional[float] = None
    recall: Optional[float] = None
    error: Optional[str] = None
