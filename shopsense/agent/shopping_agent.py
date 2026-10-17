"""
shopsense/agent/shopping_agent.py
Main orchestration: query understanding → retrieval → output validation → response.

Workflow (each step is visible and independently testable):
  1. Input validation          (guardrails/input_checks.py)
  2. Query understanding       (Stage A — ChatGoogleGenerativeAI + structured output)
  3. Product retrieval         (catalog/search.py)
  4. Output validation         (guardrails/output_checks.py)
  5. Response generation       (Stage B — free-text explanation from Gemini)
"""
from __future__ import annotations

import logging
import re
from typing import Dict, List, Optional, Tuple

from shopsense.catalog.loader import (
    get_catalog_stats,
    get_distinct_categories,
    get_products_by_ids,
)
from shopsense.catalog.search import search_products
from shopsense.config import GEMINI_AVAILABLE, GEMINI_MODEL, GOOGLE_API_KEY
from shopsense.guardrails.input_checks import check_input
from shopsense.guardrails.output_checks import validate_agent_response, verify_products_against_constraints
from shopsense.schemas import AgentResponse, Product, ShoppingIntent

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# LLM initialisation (lazy — only when API key is available)
# ---------------------------------------------------------------------------

def _get_chat_model():
    """Return a ChatGoogleGenerativeAI instance, or None if unavailable."""
    if not GEMINI_AVAILABLE:
        return None
    try:
        from langchain_google_genai import ChatGoogleGenerativeAI
        return ChatGoogleGenerativeAI(
            model=GEMINI_MODEL,
            google_api_key=GOOGLE_API_KEY,
            temperature=0.1,
            max_retries=2,
        )
    except Exception as e:
        logger.warning("Could not initialise Gemini model: %s", e)
        return None


# ---------------------------------------------------------------------------
# Stage A: Query Understanding
# ---------------------------------------------------------------------------

def understand_query(query: str) -> Optional[ShoppingIntent]:
    """
    Use Gemini + structured output to parse a shopping query into ShoppingIntent.
    Returns None if the model is unavailable or the response is invalid.
    """
    model = _get_chat_model()
    if model is None:
        return None

    from shopsense.agent.prompts import QUERY_UNDERSTANDING_PROMPT

    categories = ", ".join(get_distinct_categories())
    try:
        structured_model = model.with_structured_output(ShoppingIntent)
        chain = QUERY_UNDERSTANDING_PROMPT | structured_model
        intent = chain.invoke({"query": query, "categories": categories})
        if isinstance(intent, ShoppingIntent):
            return intent
        return None
    except Exception as e:
        logger.error("Query understanding failed: %s", e)
        return None


def _fallback_intent(query: str) -> ShoppingIntent:
    """Create a structured intent using deterministic regex parsing when Gemini is unavailable."""
    clean_q = query.strip()
    max_price = None
    min_price = None
    max_w = None
    max_h = None

    # Price parsing: "under 1500", "below ₹800", "<= 500"
    p_under = re.search(r"(?:under|below|less than|max(?:imum)?|<=?)\s*(?:₹|inr|rs\.?)?\s*(\d+(?:\.\d+)?)", clean_q, re.I)
    if p_under:
        try:
            max_price = float(p_under.group(1))
        except ValueError:
            pass

    p_over = re.search(r"(?:above|over|more than|min(?:imum)?|>=?)\s*(?:₹|inr|rs\.?)?\s*(\d+(?:\.\d+)?)", clean_q, re.I)
    if p_over:
        try:
            min_price = float(p_over.group(1))
        except ValueError:
            pass

    # Dimensions: "width 30cm", "w: 30", "height 40cm"
    w_m = re.search(r"\b(?:width|w)\b\s*(?:is|of|around|about|:)?\s*(\d+(?:\.\d+)?)\s*(?:cm)?", clean_q, re.I)
    if w_m:
        try:
            max_w = float(w_m.group(1))
        except ValueError:
            pass

    h_m = re.search(r"\b(?:height|h)\b\s*(?:is|of|around|about|:)?\s*(\d+(?:\.\d+)?)\s*(?:cm)?", clean_q, re.I)
    if h_m:
        try:
            max_h = float(h_m.group(1))
        except ValueError:
            pass

    # "30x40" or "30 x 40 cm"
    dim_pair = re.search(r"(\d+)\s*[x×]\s*(\d+)\s*(?:cm)?", clean_q, re.I)
    if dim_pair and max_w is None and max_h is None:
        try:
            max_w = float(dim_pair.group(1))
            max_h = float(dim_pair.group(2))
        except ValueError:
            pass

    # Extract search terms by removing filler/stopwords and numbers
    stopwords = {
        "find", "show", "me", "looking", "for", "a", "an", "the", "with", "and", "or",
        "under", "below", "above", "over", "around", "about", "cm", "inr", "rs", "rupees",
        "price", "width", "height", "depth", "dimensions", "size", "is", "of", "to", "in"
    }
    raw_tokens = re.findall(r"[A-Za-z]+", clean_q.lower())
    search_terms = [t for t in raw_tokens if t not in stopwords and len(t) > 2]

    # Category matching against catalog
    cat_match = None
    all_cats = get_distinct_categories()
    for cat in all_cats:
        for word in cat.lower().split():
            if len(word) > 3 and word in clean_q.lower():
                cat_match = cat
                break
        if cat_match:
            break

    return ShoppingIntent(
        user_goal=clean_q,
        search_terms=search_terms if search_terms else clean_q.split(),
        category=cat_match,
        maximum_price=max_price,
        minimum_price=min_price,
        maximum_width_cm=max_w,
        maximum_height_cm=max_h,
        is_shopping_request=True,
    )


# ---------------------------------------------------------------------------
# Stage B: Response Generation
# ---------------------------------------------------------------------------

def _format_products_for_prompt(products: List[Product]) -> str:
    """Serialise product list into a prompt-friendly string."""
    if not products:
        return "No products found."
    lines: List[str] = []
    for p in products:
        dim_parts = []
        if p.width_cm:
            dim_parts.append(f"W{p.width_cm}cm")
        if p.depth_cm:
            dim_parts.append(f"D{p.depth_cm}cm")
        if p.height_cm:
            dim_parts.append(f"H{p.height_cm}cm")
        dim_str = " × ".join(dim_parts) or "Not specified"

        lines.append(
            f"- [{p.product_id}] {p.display_name} | "
            f"Price: {p.price_display} | "
            f"Category: {p.category_2 or 'N/A'} | "
            f"Rating: {p.rating_display} | "
            f"Dimensions: {dim_str} | "
            f"Material: {(p.material_and_care or 'N/A')[:80]}"
        )
    return "\n".join(lines)


def generate_response(
    intent: ShoppingIntent,
    products: List[Product],
    retrieval_method: str,
) -> str:
    """Generate a free-text explanation of the search results using Gemini."""
    model = _get_chat_model()
    if model is None:
        if not products:
            return (
                "No products match your criteria. "
                "Try broadening your search (e.g., higher price limit or different category)."
            )
        return (
            f"Found {len(products)} product(s) matching your request. "
            "AI-powered explanations are unavailable — please configure a Google API key."
        )

    from shopsense.agent.prompts import RESPONSE_GENERATION_PROMPT

    chain = RESPONSE_GENERATION_PROMPT | model
    try:
        result = chain.invoke({
            "products_context": _format_products_for_prompt(products),
            "user_goal": intent.user_goal,
            "product_count": len(products),
            "retrieval_method": retrieval_method,
        })
        return result.content.strip()
    except Exception as e:
        logger.error("Response generation failed: %s", e)
        return (
            f"Found {len(products)} product(s) matching your request. "
            "(AI explanation temporarily unavailable.)"
        )


def generate_comparison_summary(products: List[Product]) -> str:
    """Use Gemini to explain trade-offs between selected products."""
    model = _get_chat_model()
    if model is None or len(products) < 2:
        return ""

    from shopsense.agent.prompts import COMPARISON_PROMPT

    chain = COMPARISON_PROMPT | model
    try:
        result = chain.invoke({
            "products_context": _format_products_for_prompt(products),
            "count": len(products),
        })
        return result.content.strip()
    except Exception as e:
        logger.error("Comparison generation failed: %s", e)
        return ""


def _describe_catalog_capabilities() -> str:
    """Return a helpful guide to catalog categories and search capabilities."""
    cats = get_distinct_categories()
    cat_bullets = "\n".join(f"- **{c}**" for c in cats)
    return (
        "You can search across our entire IKEA Home Decor collection! Here are the main categories available:\n\n"
        f"{cat_bullets}\n\n"
        "**Ways you can search:**\n"
        "- 💰 **By Budget**: *'Find mirrors under ₹2,000'* or *'vases under ₹800'*\n"
        "- 🌿 **By Scent & Style**: *'Show me candles with a woodsy or vanilla scent'* or *'minimalist wall art'*\n"
        "- 📐 **By Dimensions**: *'Find picture frames around 30 × 40 cm'* or *'mirrors with width under 50 cm'*\n"
        "- ⭐ **By Rating**: *'Show me top-rated wall clocks'* (rating 4.5+)\n"
        "- ⚖️ **By Product Comparison**: Add items to your tray or ask *'Compare two vases by price and dimensions'*\n\n"
        "What kind of home decor piece would you like to explore today?"
    )


# ---------------------------------------------------------------------------
# Main public entry point
# ---------------------------------------------------------------------------

def run_shopping_agent(
    user_query: str,
    chat_history: Optional[List[Dict]] = None,
) -> Tuple[AgentResponse, List[Product]]:
    """
    Full shopping agent pipeline.
    Returns (AgentResponse, verified_products).
    """
    # Step 1: Input validation
    check = check_input(user_query)
    if not check.allowed:
        response = AgentResponse(
            answer=check.user_message,
            product_ids=[],
            no_results=True,
            retrieval_method="none",
        )
        return response, []

    # Check if user is asking about capabilities or catalog categories
    q_lower = user_query.lower()
    is_asking_about_capabilities = any(
        phrase in q_lower
        for phrase in [
            "what kind of product",
            "what products",
            "what can i search",
            "what categories",
            "what do you have",
            "what items",
            "tell me what",
            "what are the categories",
            "how can you help",
            "what can you find",
        ]
    )

    # Step 2: Query understanding
    intent = understand_query(user_query)
    ai_available = intent is not None
    if intent is None:
        intent = _fallback_intent(user_query)

    # Handle capability queries or non-shopping requests
    if is_asking_about_capabilities or not intent.is_shopping_request:
        if is_asking_about_capabilities or not intent.clarification_question:
            answer = _describe_catalog_capabilities()
        else:
            answer = intent.clarification_question

        response = AgentResponse(
            answer=answer,
            product_ids=[],
            no_results=False,
            retrieval_method="none",
        )
        return response, []

    # Clarification needed
    if intent.requires_clarification and intent.clarification_question:
        response = AgentResponse(
            answer=intent.clarification_question,
            product_ids=[],
            no_results=False,
            retrieval_method="none",
        )
        return response, []

    # Step 3: Product retrieval
    products, retrieval_method = search_products(intent, use_semantic=ai_available)

    # Step 4: Output validation (constraint re-check)
    products, constraint_issues = verify_products_against_constraints(
        products,
        max_price=intent.maximum_price,
        min_rating=intent.minimum_rating,
        max_width_cm=intent.maximum_width_cm,
        max_height_cm=intent.maximum_height_cm,
    )

    # Step 5: Generate explanation
    answer = generate_response(intent, products, retrieval_method)

    product_ids = [p.product_id for p in products]

    raw_response = AgentResponse(
        answer=answer,
        product_ids=product_ids,
        no_results=len(products) == 0,
        retrieval_method=retrieval_method,
        limitations=(
            "AI query understanding unavailable — using keyword search." if not ai_available else None
        ),
    )

    # Validate response
    check_result = validate_agent_response(raw_response)
    verified_ids = check_result.verified_product_ids
    verified_products = get_products_by_ids(verified_ids)

    final_response = AgentResponse(
        answer=raw_response.answer,
        product_ids=verified_ids,
        no_results=len(verified_products) == 0,
        retrieval_method=retrieval_method,
        limitations=raw_response.limitations,
    )

    return final_response, verified_products
