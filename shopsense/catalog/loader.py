"""
shopsense/catalog/loader.py
Handles SQLite connection, schema inspection, and product loading.
All queries are parameterised — no SQL construction from user input or LLM output.
"""
from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Any, Dict, List, Optional

import pandas as pd

from shopsense.config import DB_PATH
from shopsense.schemas import Product


# ---------------------------------------------------------------------------
# Database connection helpers
# ---------------------------------------------------------------------------

def _get_connection(path: Path = DB_PATH) -> sqlite3.Connection:
    """Open a read-only SQLite connection. Raises FileNotFoundError if missing."""
    if not path.exists():
        raise FileNotFoundError(
            f"Product database not found at: {path}\n"
            "Run data_cleaning/prepare_catalog.py to create it."
        )
    # uri=True allows mode=ro for read-only access
    conn = sqlite3.connect(
        f"file:{path}?mode=ro", uri=True, check_same_thread=False
    )
    conn.row_factory = sqlite3.Row
    return conn


def get_available_columns() -> List[str]:
    """Return column names that actually exist in the products table."""
    with _get_connection() as conn:
        cur = conn.execute("PRAGMA table_info(products);")
        return [row["name"] for row in cur.fetchall()]


# ---------------------------------------------------------------------------
# Catalog statistics (cached at Streamlit level when used in UI)
# ---------------------------------------------------------------------------

def get_catalog_stats() -> Dict[str, Any]:
    """Return high-level catalog statistics from the live database."""
    with _get_connection() as conn:
        stats: Dict[str, Any] = {}
        stats["total_products"] = conn.execute("SELECT COUNT(*) FROM products;").fetchone()[0]
        stats["categories"] = conn.execute(
            "SELECT COUNT(DISTINCT category_2) FROM products WHERE category_2 IS NOT NULL;"
        ).fetchone()[0]
        stats["with_images"] = conn.execute(
            "SELECT COUNT(*) FROM products WHERE primary_image IS NOT NULL AND primary_image != '';"
        ).fetchone()[0]
        stats["with_price"] = conn.execute(
            "SELECT COUNT(*) FROM products WHERE price IS NOT NULL;"
        ).fetchone()[0]
        stats["with_rating"] = conn.execute(
            "SELECT COUNT(*) FROM products WHERE average_rating IS NOT NULL;"
        ).fetchone()[0]
        return stats


# ---------------------------------------------------------------------------
# Row → Product mapping
# ---------------------------------------------------------------------------

def _row_to_product(row: sqlite3.Row) -> Product:
    """Convert a SQLite Row to a typed Product model."""
    keys = row.keys()
    d = dict(row)

    def _opt_str(k: str) -> Optional[str]:
        v = d.get(k)
        return str(v).strip() if v else None

    def _opt_float(k: str) -> Optional[float]:
        v = d.get(k)
        try:
            return float(v) if v is not None else None
        except (TypeError, ValueError):
            return None

    def _opt_int(k: str) -> Optional[int]:
        v = d.get(k)
        try:
            return int(v) if v is not None else None
        except (TypeError, ValueError):
            return None

    return Product(
        product_id=str(d["product_id"]),
        item_number=_opt_str("item_number"),
        product_name=d.get("product_name") or "",
        display_name=d.get("display_name") or d.get("product_name") or "",
        description=_opt_str("description"),
        summary=_opt_str("summary"),
        features=_opt_str("features"),
        product_type=_opt_str("product_type"),
        category_1=_opt_str("category_1"),
        category_2=_opt_str("category_2"),
        category_3=_opt_str("category_3"),
        category_4=_opt_str("category_4"),
        price=_opt_float("price"),
        currency=_opt_str("currency"),
        average_rating=_opt_float("average_rating"),
        reviews_count=_opt_int("reviews_count"),
        width_cm=_opt_float("width_cm"),
        depth_cm=_opt_float("depth_cm"),
        height_cm=_opt_float("height_cm"),
        measurements_text=_opt_str("measurements_text"),
        material_and_care=_opt_str("material_and_care"),
        primary_image=_opt_str("primary_image"),
        product_url=_opt_str("product_url"),
        product_details=_opt_str("product_details"),
    )


# ---------------------------------------------------------------------------
# Core loading functions
# ---------------------------------------------------------------------------

def load_all_products() -> List[Product]:
    """Load all products from the database."""
    with _get_connection() as conn:
        rows = conn.execute("SELECT * FROM products ORDER BY product_name;").fetchall()
    return [_row_to_product(r) for r in rows]


def load_all_products_df() -> pd.DataFrame:
    """Load all products as a DataFrame (useful for embedding cache logic)."""
    with _get_connection() as conn:
        return pd.read_sql_query("SELECT * FROM products;", conn)


def get_product_by_id(product_id: str) -> Optional[Product]:
    """Fetch a single product by its ID. Returns None if not found."""
    with _get_connection() as conn:
        row = conn.execute(
            "SELECT * FROM products WHERE product_id = ?;", (str(product_id),)
        ).fetchone()
    return _row_to_product(row) if row else None


def get_products_by_ids(product_ids: List[str]) -> List[Product]:
    """Fetch multiple products by ID, preserving order. Missing IDs are skipped."""
    if not product_ids:
        return []
    str_ids = [str(pid) for pid in product_ids]
    placeholders = ",".join("?" * len(str_ids))
    with _get_connection() as conn:
        rows = conn.execute(
            f"SELECT * FROM products WHERE product_id IN ({placeholders});", str_ids
        ).fetchall()
    id_to_product = {_row_to_product(r).product_id: _row_to_product(r) for r in rows}
    return [id_to_product[pid] for pid in str_ids if pid in id_to_product]


def verify_product_ids(product_ids: List[str]) -> List[str]:
    """Return only IDs that actually exist in the database."""
    if not product_ids:
        return []
    str_ids = [str(pid) for pid in product_ids]
    placeholders = ",".join("?" * len(str_ids))
    with _get_connection() as conn:
        rows = conn.execute(
            f"SELECT product_id FROM products WHERE product_id IN ({placeholders});", str_ids
        ).fetchall()
    existing = {r["product_id"] for r in rows}
    return [pid for pid in str_ids if pid in existing]


def get_distinct_categories() -> List[str]:
    """Return distinct category_2 values in alphabetical order."""
    with _get_connection() as conn:
        rows = conn.execute(
            "SELECT DISTINCT category_2 FROM products WHERE category_2 IS NOT NULL ORDER BY category_2;"
        ).fetchall()
    return [r["category_2"] for r in rows]


def get_catalog_hash() -> str:
    """Return a fingerprint of the catalog for embedding-cache invalidation."""
    with _get_connection() as conn:
        row = conn.execute(
            "SELECT COUNT(*) as n, SUM(CAST(REPLACE(product_id,'','') as INTEGER)) as s FROM products;"
        ).fetchone()
    return f"{row['n']}_{row['s']}"
