"""
shopsense/guardrails/input_checks.py
Deterministic input-side guardrails.
All checks run BEFORE the query reaches Gemini.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Optional

# ---------------------------------------------------------------------------
# Configuration constants
# ---------------------------------------------------------------------------
MAX_INPUT_LENGTH = 1_500  # characters

# Keywords that indicate prompt-injection attempts
_INJECTION_PATTERNS = [
    r"ignore\s+(all\s+)?(previous|prior|above|earlier)\s+(system\s+)?(instructions?|prompts?|rules?|directives?)",
    r"disregard\s+(all\s+)?(instructions?|prompts?|rules?)",
    r"you\s+are\s+now\s+(a\s+)?different",
    r"act\s+as\s+(if\s+you\s+are\s+|like\s+)?(?:a\s+)?(jailbreak|dan|evil|unrestricted)\b",
    r"reveal\s+(your\s+)?(secret\s+)?(system\s+prompt|api\s+key|secrets?|instructions?)",
    r"tell\s+me\s+(your\s+)?(secret\s+)?(system\s+prompt|api\s+key|hidden\s+(instructions?|prompt)|instructions?)",
    r"what\s+is\s+your\s+(secret\s+)?(system\s+)?(prompt|instructions?)",
    r"print\s+your\s+(secret\s+)?(system\s+)?(prompt|instructions?)",
    r"show\s+(me\s+)?(your\s+)?(secret\s+)?(system\s+prompt|api\s+key|secrets?|instructions?)",
    r"forget\s+(all\s+)?(previous\s+)?instructions?",
    r"do\s+anything\s+now",
    r"\bdan\s+mode\b",
]
_INJECTION_RE = [re.compile(p, re.IGNORECASE) for p in _INJECTION_PATTERNS]

# Patterns for clearly harmful / dangerous content
_HARM_PATTERNS = [
    r"\b(bomb|explosive|detonat|c4|tnt|improvised\s+explosive)\b",
    r"\b(make|build|create|construct)\s+(a\s+)?(weapon|explosive|bomb)\b",
    r"\b(synthesize|manufacture)\s+(drug|meth|heroin|fentanyl)\b",
    r"\b(how\s+to\s+kill|murder|assassinat)\b",
    r"\b(child\s+(porn|sexual|exploit|abuse))\b",
    r"\b(self.harm|suicide\s+method)\b",
]
_HARM_RE = [re.compile(p, re.IGNORECASE) for p in _HARM_PATTERNS]

# Domains clearly outside the IKEA Home Decor catalog
_OUT_OF_SCOPE_PATTERNS = [
    # Electronics
    r"\b(iphone|ipad|macbook|samsung|galaxy|pixel|android\s+phone|laptop|computer|tablet|smartwatch)\b",
    r"\b(headphone|earphone|airpod|speaker|monitor|printer|camera|drone)\b",
    r"\b(tv\b|television|refrigerator|washing\s+machine|dishwasher|microwave|oven\b|air\s+conditioner|AC\b)\b",
    # Clothing / Footwear
    r"\b(shirt|dress|jeans|trousers|shoes?|sneakers?|boots?|sandals?|jacket|coat|hoodie)\b",
    # Food / Groceries
    r"\b(grocery|food\s+(item|product)|restaurant|recipe\s+for|cooking\s+ingredients?)\b",
    # Furniture (large items not in this Home Decor slice)
    r"\b(sofas?|couch(es)?|recliners?|mattress(es)?|bed\s+frames?|dining\s+tables?|wardrobes?|almirahs?)\b",
    # Automotive
    r"\b(car|vehicle|motorcycle|bike\s+part|auto\s+part)\b",
    # Software / Digital
    r"\b(software|app(lication)?|saas|subscription|streaming|netflix|spotify)\b",
]
_OOS_RE = [re.compile(p, re.IGNORECASE) for p in _OUT_OF_SCOPE_PATTERNS]


# ---------------------------------------------------------------------------
# Result dataclass
# ---------------------------------------------------------------------------

@dataclass
class InputCheckResult:
    allowed: bool
    reason: str          # machine-readable code
    user_message: str    # human-readable message for the UI


# ---------------------------------------------------------------------------
# Public check function
# ---------------------------------------------------------------------------

def check_input(text: str) -> InputCheckResult:
    """
    Run all deterministic input checks.
    Returns InputCheckResult(allowed=True) if the input is safe.
    Returns InputCheckResult(allowed=False, ...) with a user-facing message otherwise.
    """
    if not text or not text.strip():
        return InputCheckResult(
            allowed=False,
            reason="empty_input",
            user_message="Please enter a shopping request.",
        )

    if len(text) > MAX_INPUT_LENGTH:
        return InputCheckResult(
            allowed=False,
            reason="input_too_long",
            user_message=f"Your message is too long (max {MAX_INPUT_LENGTH} characters). Please shorten it.",
        )

    # Prompt injection
    for pattern in _INJECTION_RE:
        if pattern.search(text):
            return InputCheckResult(
                allowed=False,
                reason="prompt_injection",
                user_message=(
                    "I'm ShopSense AI, a home-shopping assistant. "
                    "I can't help with that, but I'd love to help you find home decor products!"
                ),
            )

    # Harmful content
    for pattern in _HARM_RE:
        if pattern.search(text):
            return InputCheckResult(
                allowed=False,
                reason="harmful_content",
                user_message=(
                    "I'm not able to assist with that request. "
                    "I'm here to help you discover home decor products."
                ),
            )

    # Out-of-scope domain
    for pattern in _OOS_RE:
        if pattern.search(text):
            return InputCheckResult(
                allowed=False,
                reason="out_of_scope",
                user_message=(
                    "ShopSense AI specialises in IKEA Home Decor — candles, mirrors, "
                    "picture frames, vases, clocks, and wall art. "
                    "I couldn't find that category in our catalog. "
                    "Can I help you find a home decor item instead?"
                ),
            )

    return InputCheckResult(allowed=True, reason="ok", user_message="")
