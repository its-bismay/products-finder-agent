"""
shopsense/config.py
Centralised configuration loader for ShopSense AI.

Priority order for secrets:
  1. Streamlit Secrets (st.secrets) — for cloud deployment
  2. .env file (python-dotenv) — for local development
  3. Defaults
"""
from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv

# Load .env from project root (no-op if file is absent)
_PROJECT_ROOT = Path(__file__).resolve().parent.parent
load_dotenv(_PROJECT_ROOT / ".env", override=False)


def _get_secret(key: str, default: str | None = None) -> str | None:
    """
    Try Streamlit Secrets first, then env vars, then the supplied default.
    Falls back gracefully if Streamlit is not imported yet.
    """
    try:
        import streamlit as st  # lazy import — avoids errors when running tests
        if hasattr(st, "secrets") and key in st.secrets:
            return str(st.secrets[key])
    except Exception:
        pass
    return os.environ.get(key, default)


# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
PROJECT_ROOT: Path = _PROJECT_ROOT
DATA_DIR: Path = PROJECT_ROOT / "data"
DB_PATH: Path = DATA_DIR / "products.db"
EMBEDDINGS_CACHE_PATH: Path = DATA_DIR / "product_embeddings.npz"
EVALUATION_CASES_PATH: Path = DATA_DIR / "evaluation_cases.json"
REPORTS_DIR: Path = PROJECT_ROOT / "reports"


# ---------------------------------------------------------------------------
# Google / Gemini
# ---------------------------------------------------------------------------
GOOGLE_API_KEY: str | None = _get_secret("GOOGLE_API_KEY")

GEMINI_MODEL: str = _get_secret("GEMINI_MODEL") or "gemini-3.1-flash-lite"
GEMINI_EMBEDDING_MODEL: str = (
    _get_secret("GEMINI_EMBEDDING_MODEL") or "models/gemini-embedding-001"
)

GEMINI_AVAILABLE: bool = bool(GOOGLE_API_KEY)


# ---------------------------------------------------------------------------
# Retrieval settings
# ---------------------------------------------------------------------------
SEMANTIC_RETRIEVAL_ENABLED: bool = GEMINI_AVAILABLE
# Tolerance (%) for approximate dimension matching
APPROX_DIMENSION_TOLERANCE_PCT: float = 0.20   # ±20 %
# Max candidates to return from retrieval before LLM ranking
MAX_RETRIEVAL_CANDIDATES: int = 12
# Max products to show per page
PRODUCTS_PER_PAGE: int = 12
