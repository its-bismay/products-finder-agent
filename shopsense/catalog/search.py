"""
shopsense/catalog/search.py
Product retrieval: hard filtering (deterministic SQL) + semantic / keyword search.

Architecture:
  1. apply_hard_filters()    — deterministic Python / parameterised SQL
  2. keyword_search()        — SQLite LIKE matching across text columns
  3. semantic_search()       — GoogleGenerativeAIEmbeddings with NPZ cache
  4. search_products()       — public orchestration function
"""
from __future__ import annotations

import hashlib
import logging
import sqlite3
from pathlib import Path
from typing import List, Optional, Tuple

import numpy as np
import pandas as pd

from shopsense.catalog.loader import (
    _get_connection,
    _row_to_product,
    get_catalog_hash,
    load_all_products_df,
)
from shopsense.config import (
    APPROX_DIMENSION_TOLERANCE_PCT,
    EMBEDDINGS_CACHE_PATH,
    GEMINI_AVAILABLE,
    GEMINI_EMBEDDING_MODEL,
    GOOGLE_API_KEY,
    MAX_RETRIEVAL_CANDIDATES,
)
from shopsense.schemas import Product, ShoppingIntent

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Hard filtering (deterministic, parameterised SQL)
# ---------------------------------------------------------------------------

def apply_hard_filters(intent: ShoppingIntent) -> Tuple[str, List]:
    """
    Build a WHERE clause from hard constraints in the ShoppingIntent.
    Returns (where_clause_str, params_list).
    No user text is interpolated into the SQL string.
    """
    clauses: List[str] = []
    params: List = []

    if intent.category:
        clauses.append("(category_2 LIKE ? OR category_3 LIKE ?)")
        params.extend([f"%{intent.category}%", f"%{intent.category}%"])

    if intent.minimum_price is not None:
        clauses.append("price >= ?")
        params.append(intent.minimum_price)

    if intent.maximum_price is not None:
        clauses.append("price <= ?")
        params.append(intent.maximum_price)

    if intent.minimum_rating is not None:
        clauses.append("average_rating >= ?")
        params.append(intent.minimum_rating)

    if intent.maximum_width_cm is not None:
        clauses.append("(width_cm IS NULL OR width_cm <= ?)")
        params.append(intent.maximum_width_cm)

    if intent.maximum_depth_cm is not None:
        clauses.append("(depth_cm IS NULL OR depth_cm <= ?)")
        params.append(intent.maximum_depth_cm)

    if intent.maximum_height_cm is not None:
        clauses.append("(height_cm IS NULL OR height_cm <= ?)")
        params.append(intent.maximum_height_cm)

    if intent.product_name:
        clauses.append("product_name LIKE ?")
        params.append(f"%{intent.product_name}%")

    where = "WHERE " + " AND ".join(clauses) if clauses else ""
    return where, params


def get_hard_filtered_ids(intent: ShoppingIntent) -> List[str]:
    """Return product_ids that pass all hard constraints."""
    where, params = apply_hard_filters(intent)
    sql = f"SELECT product_id FROM products {where};"
    with _get_connection() as conn:
        rows = conn.execute(sql, params).fetchall()
    return [r["product_id"] for r in rows]


# ---------------------------------------------------------------------------
# Keyword search (fallback / baseline)
# ---------------------------------------------------------------------------

_TEXT_COLUMNS = [
    "product_name", "display_name", "description", "summary",
    "features", "category_2", "category_3", "material_and_care",
]


def keyword_search(
    terms: List[str],
    candidate_ids: Optional[List[str]] = None,
    limit: int = MAX_RETRIEVAL_CANDIDATES,
) -> List[str]:
    """
    Return product IDs ranked by how many search terms appear in text fields.
    If candidate_ids is given, search is restricted to that set.
    """
    if not terms:
        if candidate_ids is not None:
            return candidate_ids[:limit]
        with _get_connection() as conn:
            rows = conn.execute(
                f"SELECT product_id FROM products ORDER BY average_rating DESC NULLS LAST LIMIT ?;",
                (limit,),
            ).fetchall()
        return [r["product_id"] for r in rows]

    # Score each candidate by term frequency across text columns
    id_filter = ""
    id_params: List = []
    if candidate_ids is not None:
        placeholders = ",".join("?" * len(candidate_ids))
        id_filter = f"WHERE product_id IN ({placeholders})"
        id_params = list(candidate_ids)

    with _get_connection() as conn:
        rows = conn.execute(
            f"SELECT product_id, {', '.join(_TEXT_COLUMNS)} FROM products {id_filter};",
            id_params,
        ).fetchall()

    # Filter out short or generic stopwords from query terms
    common_stopwords = {"find", "show", "me", "the", "and", "with", "for", "have", "you", "what", "between", "under", "difference"}
    lower_terms = [t.lower() for t in terms if t.lower() not in common_stopwords and len(t) > 2]
    if not lower_terms:
        lower_terms = [t.lower() for t in terms if len(t) > 1]

    def score(row: sqlite3.Row) -> float:
        p_name = str(row["product_name"] or "").lower()
        d_name = str(row["display_name"] or "").lower()
        cat2 = str(row["category_2"] or "").lower()
        full_text = " ".join(str(row[c] or "") for c in _TEXT_COLUMNS).lower()
        
        pts = 0.0
        for t in lower_terms:
            if t == p_name or t in p_name.split():
                pts += 25.0
            elif t in d_name:
                pts += 10.0
            if t in cat2:
                pts += 5.0
            if t in full_text:
                pts += 1.0
        return pts

    scored = sorted(rows, key=score, reverse=True)
    return [r["product_id"] for r in scored[:limit]]


# ---------------------------------------------------------------------------
# Semantic search (embedding-based, optional)
# ---------------------------------------------------------------------------

def _build_product_text(row: pd.Series) -> str:
    """Create a single searchable text from product fields."""
    parts = [
        str(row.get("display_name") or ""),
        str(row.get("description") or ""),
        str(row.get("summary") or ""),
        str(row.get("features") or ""),
        str(row.get("category_2") or ""),
        str(row.get("category_3") or ""),
        str(row.get("material_and_care") or ""),
    ]
    return " ".join(p for p in parts if p and p != "nan").strip()


def _get_embedding_model():
    """Lazily initialise the embedding model (returns None if unavailable)."""
    if not GEMINI_AVAILABLE:
        return None
    try:
        from langchain_google_genai import GoogleGenerativeAIEmbeddings
        return GoogleGenerativeAIEmbeddings(
            model=GEMINI_EMBEDDING_MODEL,
            google_api_key=GOOGLE_API_KEY,
        )
    except Exception as e:
        logger.warning("Could not initialise embedding model: %s", e)
        return None


def _cache_fingerprint(model_name: str, catalog_hash: str) -> str:
    return hashlib.md5(f"{model_name}:{catalog_hash}".encode()).hexdigest()[:12]


def _load_embedding_cache() -> Optional[Tuple[np.ndarray, List[str], str]]:
    """Load (embeddings, product_ids, fingerprint) from NPZ cache, or None."""
    if not EMBEDDINGS_CACHE_PATH.exists():
        return None
    try:
        data = np.load(EMBEDDINGS_CACHE_PATH, allow_pickle=True)
        embeddings = data["embeddings"]
        product_ids = list(data["product_ids"])
        fingerprint = str(data["fingerprint"])
        return embeddings, product_ids, fingerprint
    except Exception as e:
        logger.warning("Could not load embedding cache: %s", e)
        return None


def _save_embedding_cache(
    embeddings: np.ndarray, product_ids: List[str], fingerprint: str
) -> None:
    EMBEDDINGS_CACHE_PATH.parent.mkdir(parents=True, exist_ok=True)
    np.savez_compressed(
        EMBEDDINGS_CACHE_PATH,
        embeddings=embeddings,
        product_ids=np.array(product_ids, dtype=object),
        fingerprint=fingerprint,
    )


def build_embedding_cache(force: bool = False) -> bool:
    """
    Build and persist the product embedding cache.
    Returns True on success, False if embedding is unavailable.
    """
    model = _get_embedding_model()
    if model is None:
        return False

    catalog_hash = get_catalog_hash()
    fingerprint = _cache_fingerprint(GEMINI_EMBEDDING_MODEL, catalog_hash)

    cached = _load_embedding_cache()
    if cached and cached[2] == fingerprint and not force:
        logger.info("Embedding cache is up-to-date.")
        return True

    logger.info("Building embedding cache …")
    df = load_all_products_df()
    texts = df.apply(_build_product_text, axis=1).tolist()
    product_ids = df["product_id"].astype(str).tolist()

    batch_size = 50
    all_embeddings: List[List[float]] = []
    for i in range(0, len(texts), batch_size):
        batch = texts[i : i + batch_size]
        try:
            vecs = model.embed_documents(batch)
            all_embeddings.extend(vecs)
        except Exception as e:
            logger.error("Embedding batch %d failed: %s", i // batch_size, e)
            return False

    matrix = np.array(all_embeddings, dtype=np.float32)
    _save_embedding_cache(matrix, product_ids, fingerprint)
    logger.info("Saved %d product embeddings.", len(product_ids))
    return True


def _cosine_similarity(query_vec: np.ndarray, matrix: np.ndarray) -> np.ndarray:
    """Vectorised cosine similarity between query and all rows of matrix."""
    query_norm = query_vec / (np.linalg.norm(query_vec) + 1e-9)
    row_norms = np.linalg.norm(matrix, axis=1, keepdims=True) + 1e-9
    normed = matrix / row_norms
    return normed @ query_norm


def semantic_search(
    query: str,
    candidate_ids: Optional[List[str]] = None,
    limit: int = MAX_RETRIEVAL_CANDIDATES,
) -> Tuple[List[str], bool]:
    """
    Semantic product search using cached embeddings.
    Returns (ranked_ids, used_semantic: bool).
    Falls back to keyword search if embeddings are unavailable.
    """
    model = _get_embedding_model()
    if model is None:
        ids = keyword_search(query.split(), candidate_ids, limit)
        return ids, False

    catalog_hash = get_catalog_hash()
    fingerprint = _cache_fingerprint(GEMINI_EMBEDDING_MODEL, catalog_hash)
    cached = _load_embedding_cache()

    if cached is None or cached[2] != fingerprint:
        success = build_embedding_cache()
        if not success:
            ids = keyword_search(query.split(), candidate_ids, limit)
            return ids, False
        cached = _load_embedding_cache()

    if cached is None:
        ids = keyword_search(query.split(), candidate_ids, limit)
        return ids, False

    embeddings, all_ids, _ = cached

    # Restrict to candidate IDs if given
    if candidate_ids is not None:
        candidate_set = set(candidate_ids)
        mask = np.array([pid in candidate_set for pid in all_ids])
        if not mask.any():
            return [], True
        embeddings = embeddings[mask]
        all_ids = [pid for pid, m in zip(all_ids, mask) if m]

    try:
        query_vec = np.array(model.embed_query(query), dtype=np.float32)
    except Exception as e:
        logger.warning("Query embedding failed: %s", e)
        ids = keyword_search(query.split(), candidate_ids, limit)
        return ids, False

    scores = _cosine_similarity(query_vec, embeddings)
    top_indices = np.argsort(scores)[::-1][:limit]
    return [all_ids[i] for i in top_indices], True


# ---------------------------------------------------------------------------
# Public search orchestration
# ---------------------------------------------------------------------------

def search_products(
    intent: ShoppingIntent,
    limit: int = MAX_RETRIEVAL_CANDIDATES,
    use_semantic: bool = True,
) -> Tuple[List[Product], str]:
    """
    Full retrieval pipeline.
    1. Apply hard filters (deterministic SQL).
    2. Semantic or keyword search within filtered candidates.
    3. Return (ranked_products, retrieval_method).
    """
    from shopsense.catalog.loader import get_products_by_ids  # avoid circular at module level

    # Step 1: hard filters
    where_sql, _ = apply_hard_filters(intent)
    has_hard_filters = bool(where_sql)
    candidate_ids = get_hard_filtered_ids(intent) if has_hard_filters else None

    if has_hard_filters and not candidate_ids:
        # Zero products passed hard filters — honest empty result
        return [], "keyword"

    query_text = " ".join(
        intent.search_terms
        + intent.preferred_styles
        + intent.preferred_colors
        + intent.preferred_materials
        + ([intent.user_goal] if intent.user_goal and not intent.search_terms else [])
    ).strip()

    retrieval_method = "keyword"

    if not query_text and candidate_ids is None:
        # No constraints at all — return top-rated products
        with _get_connection() as conn:
            rows = conn.execute(
                "SELECT product_id FROM products ORDER BY average_rating DESC NULLS LAST LIMIT ?;",
                (limit,),
            ).fetchall()
        ids = [r["product_id"] for r in rows]
    elif not query_text and candidate_ids is not None:
        # Only hard filters, no text query
        ids = candidate_ids[:limit]
    elif use_semantic and GEMINI_AVAILABLE:
        ranked_ids, used_semantic = semantic_search(
            query_text, candidate_ids, limit
        )
        ids = ranked_ids
        retrieval_method = "semantic" if used_semantic else "keyword"
    else:
        ids = keyword_search(
            intent.search_terms + intent.preferred_styles + intent.preferred_colors,
            candidate_ids,
            limit,
        )

    products = get_products_by_ids(ids)
    return products, retrieval_method
