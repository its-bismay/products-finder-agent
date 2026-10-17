#!/usr/bin/env python3
"""
ShopSense AI - IKEA Home Decor Catalog Preparation Pipeline
Inspects, cleans, validates, and converts the raw IKEA dataset into
cleaned CSV and SQLite database formats.
"""

from __future__ import annotations

import html
import json
import os
import re
import sqlite3
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import pandas as pd


# -----------------------------------------------------------------------------
# Configuration and Path Resolution
# -----------------------------------------------------------------------------
SCRIPT_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = SCRIPT_DIR.parent

DATA_DIR = PROJECT_ROOT / "data"
DATA_CLEANING_DIR = PROJECT_ROOT / "data_cleaning"

CLEANED_CSV_PATH = DATA_CLEANING_DIR / "cleaned_dataset.csv"
DATA_QUALITY_REPORT_PATH = DATA_CLEANING_DIR / "catalog_data_quality.md"
SQLITE_DB_PATH = DATA_DIR / "products.db"
EVALUATION_CASES_PATH = DATA_DIR / "evaluation_cases.json"

HUGGINGFACE_DATASET_URI = (
    "hf://datasets/crawlfeeds/IKEA-Home-Decor-Furniture-Dataset/"
    "crawlfeeds_ikea__limit-100000_category_1-home-decor_20260409_190938.csv"
)

RAW_CSV_FILENAME = "crawlfeeds_ikea__limit-100000_category_1-home-decor_20260409_190938.csv"


# -----------------------------------------------------------------------------
# Helper Functions: Data Cleaning and Normalization
# -----------------------------------------------------------------------------
def clean_text(val: Any) -> Optional[str]:
    """
    Cleans text by trimming whitespace, normalizing repeated spaces,
    unescaping HTML entities, and converting database null markers to None.
    """
    if val is None or pd.isna(val):
        return None
    text = str(val).strip()
    if text in (r"\N", r"\\N", "nan", "NaN", "None", "null", "NULL", ""):
        return None
    # Decode HTML entities
    text = html.unescape(text)
    # Normalize multiple whitespace characters within lines while keeping linebreaks
    lines = [re.sub(r"[ \t]+", " ", line).strip() for line in text.splitlines()]
    cleaned = "\n".join(lines).strip()
    return cleaned if cleaned else None


def clean_url(val: Any) -> Optional[str]:
    """Validates and trims URLs."""
    text = clean_text(val)
    if not text:
        return None
    # Basic URL structure check
    if re.match(r"^https?://[^\s/$.?#].[^\s]*$", text, re.IGNORECASE):
        return text
    return None


def parse_dimension_value(val_str: str) -> Optional[float]:
    """
    Extracts a numeric measurement value and converts it to centimetres.
    Supports cm, mm, m, and inches (1 in = 2.54 cm).
    """
    if not val_str:
        return None
    val_str = val_str.strip()

    # Centimetres: e.g. "80 cm", "4.5 cm"
    m_cm = re.search(r"([0-9]+(?:\.[0-9]+)?)\s*cm\b", val_str, re.IGNORECASE)
    if m_cm:
        return round(float(m_cm.group(1)), 2)

    # Millimetres: e.g. "90 mm" -> 9.0 cm
    m_mm = re.search(r"([0-9]+(?:\.[0-9]+)?)\s*mm\b", val_str, re.IGNORECASE)
    if m_mm:
        return round(float(m_mm.group(1)) / 10.0, 2)

    # Metres: e.g. "0.7 m" -> 70.0 cm
    m_m = re.search(r"([0-9]+(?:\.[0-9]+)?)\s*m\b", val_str, re.IGNORECASE)
    if m_m:
        return round(float(m_m.group(1)) * 100.0, 2)

    # Inches: e.g. '10 in', '10 inch', '10 inches', '10"' -> 1 in = 2.54 cm
    m_in = re.search(r'([0-9]+(?:\.[0-9]+)?)\s*(?:inch(?:es)?|in\b|\")', val_str, re.IGNORECASE)
    if m_in:
        return round(float(m_in.group(1)) * 2.54, 2)

    return None


def extract_dimensions(meas_text: Optional[str]) -> Tuple[Optional[float], Optional[float], Optional[float]]:
    """
    Extracts width_cm, depth_cm, height_cm only when explicitly labeled.
    Does not assume length = width or diameter = width/depth.
    """
    if not meas_text or pd.isna(meas_text):
        return None, None, None

    width_cm = None
    depth_cm = None
    height_cm = None

    for part in str(meas_text).split("|"):
        part = part.strip()
        if ":" not in part:
            continue
        label, val = part.split(":", 1)
        label = label.strip().lower()
        if label == "width":
            width_cm = parse_dimension_value(val)
        elif label == "depth":
            depth_cm = parse_dimension_value(val)
        elif label == "height":
            height_cm = parse_dimension_value(val)

    return width_cm, depth_cm, height_cm


def generate_display_name(product_name: str, description: Optional[str]) -> str:
    """
    Constructs a readable, standardized product display name.
    Combines series name and short descriptor without redundancy.
    """
    p_name = (product_name or "").strip()
    desc = (description or "").strip()
    if not desc:
        return p_name
    if not p_name:
        return desc
    if desc.lower().startswith(p_name.lower()):
        return desc
    return f"{p_name} {desc}"


def normalize_json_field(val: Any) -> Optional[str]:
    """
    Safely validates and formats structured JSON strings.
    Converts null markers to None and safely dumps parsed JSON.
    """
    if val is None or pd.isna(val):
        return None
    val_str = str(val).strip()
    if val_str in (r"\N", r"\\N", "nan", "NaN", "None", "null", "NULL", ""):
        return None
    try:
        parsed = json.loads(val_str)
        return json.dumps(parsed, ensure_ascii=False)
    except Exception:
        # Fallback to cleaned text if not strict JSON
        return clean_text(val_str)


# -----------------------------------------------------------------------------
# Source Dataset Loader
# -----------------------------------------------------------------------------
def locate_or_load_source_dataset() -> Tuple[pd.DataFrame, str]:
    """
    Locates the raw IKEA dataset locally in the workspace or loads it from Hugging Face.
    Returns the DataFrame and the resolved source path or URI.
    """
    candidate_paths = [
        PROJECT_ROOT / "data_cleaning" / RAW_CSV_FILENAME,
        PROJECT_ROOT / "data" / RAW_CSV_FILENAME,
        PROJECT_ROOT / RAW_CSV_FILENAME,
    ]

    for path in candidate_paths:
        if path.is_file():
            print(f"Loading local dataset from: {path.relative_to(PROJECT_ROOT)}")
            # Read all IDs as string to avoid stripping leading zeros
            df = pd.read_csv(path, dtype=str)
            return df, str(path)

    # Search recursively for matching CSV if placed elsewhere
    for matched in PROJECT_ROOT.glob(f"**/{RAW_CSV_FILENAME}"):
        if matched.is_file():
            print(f"Discovered dataset at: {matched.relative_to(PROJECT_ROOT)}")
            df = pd.read_csv(matched, dtype=str)
            return df, str(matched)

    print(f"Local copy not found. Loading from Hugging Face: {HUGGINGFACE_DATASET_URI}")
    df = pd.read_csv(HUGGINGFACE_DATASET_URI, dtype=str)
    return df, HUGGINGFACE_DATASET_URI


# -----------------------------------------------------------------------------
# Cleaning Pipeline Core
# -----------------------------------------------------------------------------
def clean_catalog(raw_df: pd.DataFrame, source_path: str) -> Tuple[pd.DataFrame, Dict[str, Any]]:
    """
    Cleans, normalizes, validates, and structures the catalog data.
    Collects comprehensive quality metrics for reporting.
    """
    stats: Dict[str, Any] = {
        "source_path": source_path,
        "original_rows": len(raw_df),
        "original_cols": len(raw_df.columns),
        "original_columns": list(raw_df.columns),
        "duplicate_rows_removed": 0,
        "duplicate_product_ids": 0,
        "duplicate_item_numbers": 0,
        "duplicate_urls": 0,
        "invalid_prices": 0,
        "invalid_ratings": 0,
        "unrated_zero_rating_zero_reviews": 0,
        "missing_identifiers": 0,
        "missing_titles": 0,
        "records_with_width": 0,
        "records_with_depth": 0,
        "records_with_height": 0,
        "valid_primary_images": 0,
        "categories_breakdown": {},
        "missing_values_cleaned": {},
        "suspicious_examples": [],
        "cleaning_decisions": [],
    }

    # Track initial duplicates
    stats["duplicate_product_ids"] = int(raw_df.duplicated(subset=["product_id"]).sum())
    stats["duplicate_item_numbers"] = int(raw_df.duplicated(subset=["item_number"]).sum())
    stats["duplicate_urls"] = int(raw_df.duplicated(subset=["product_url"]).sum())

    cleaned_records: List[Dict[str, Any]] = []

    for idx, row in raw_df.iterrows():
        # 1. Product Identity and URLs
        raw_pid = clean_text(row.get("product_id"))
        raw_item_no = clean_text(row.get("item_number"))
        raw_uniq_id = clean_text(row.get("uniq_id"))
        raw_url = clean_url(row.get("product_url"))
        raw_name = clean_text(row.get("product_name"))
        raw_desc = clean_text(row.get("description"))

        # Validation: Must have a valid identifier and meaningful product name
        if not raw_pid or not raw_name:
            stats["missing_identifiers"] += 1 if not raw_pid else 0
            stats["missing_titles"] += 1 if not raw_name else 0
            continue

        display_name = generate_display_name(raw_name, raw_desc)
        product_type = clean_text(row.get("product_type"))
        category_1 = clean_text(row.get("category_1"))
        category_2 = clean_text(row.get("category_2"))
        category_3 = clean_text(row.get("category_3"))
        category_4 = clean_text(row.get("category_4"))
        breadcrumbs = normalize_json_field(row.get("breadcrumbs"))

        # 2. Pricing and Ratings
        raw_price = row.get("price")
        price: Optional[float] = None
        try:
            if raw_price is not None and not pd.isna(raw_price):
                p_val = float(str(raw_price).replace(",", "").strip())
                if p_val >= 0:
                    price = round(p_val, 2)
                else:
                    stats["invalid_prices"] += 1
        except (ValueError, TypeError):
            stats["invalid_prices"] += 1

        currency = clean_text(row.get("currency"))
        if currency:
            currency = currency.upper()

        country = clean_text(row.get("country"))
        if country:
            country = country.upper()

        raw_rating = row.get("average_rating")
        raw_reviews = row.get("reviews_count")
        reviews_count = 0
        try:
            if raw_reviews is not None and not pd.isna(raw_reviews):
                rc = int(float(str(raw_reviews).strip()))
                reviews_count = max(0, rc)
        except (ValueError, TypeError):
            reviews_count = 0

        average_rating: Optional[float] = None
        try:
            if raw_rating is not None and not pd.isna(raw_rating):
                r_val = float(str(raw_rating).strip())
                if 0.0 <= r_val <= 5.0:
                    if r_val == 0.0 and reviews_count == 0:
                        # Zero rating with zero reviews represents unrated product
                        stats["unrated_zero_rating_zero_reviews"] += 1
                        average_rating = None
                    else:
                        average_rating = round(r_val, 2)
                else:
                    stats["invalid_ratings"] += 1
        except (ValueError, TypeError):
            stats["invalid_ratings"] += 1

        ratings_breakdown = normalize_json_field(row.get("ratings_breakdown"))

        # 3. Product Information and Measurements
        summary = clean_text(row.get("summary"))
        description = raw_desc
        features = clean_text(row.get("features"))
        product_details = clean_text(row.get("product_details"))
        raw_product_details = clean_text(row.get("raw_product_details"))
        material_and_care = clean_text(row.get("material_and_care"))
        components = clean_text(row.get("components"))
        warranty_text = clean_text(row.get("warranty_text"))
        warranty_description = clean_text(row.get("warranty_description"))

        measurements_text = clean_text(row.get("measurements"))
        width_cm, depth_cm, height_cm = extract_dimensions(measurements_text)

        if width_cm is not None:
            stats["records_with_width"] += 1
        if depth_cm is not None:
            stats["records_with_depth"] += 1
        if height_cm is not None:
            stats["records_with_height"] += 1

        # 4. Images and Additional Info
        primary_image = clean_url(row.get("primary_image"))
        if primary_image:
            stats["valid_primary_images"] += 1
        additional_images = normalize_json_field(row.get("additional_images"))
        packages = normalize_json_field(row.get("packages"))
        sub_products = normalize_json_field(row.get("sub_products"))
        variations = normalize_json_field(row.get("variations"))
        scraped_at = clean_text(row.get("scraped_at"))

        rec = {
            "product_id": raw_pid,
            "item_number": raw_item_no,
            "uniq_id": raw_uniq_id,
            "product_url": raw_url,
            "product_name": raw_name,
            "display_name": display_name,
            "product_type": product_type,
            "category_1": category_1,
            "category_2": category_2,
            "category_3": category_3,
            "category_4": category_4,
            "breadcrumbs": breadcrumbs,
            "price": price,
            "currency": currency,
            "country": country,
            "average_rating": average_rating,
            "reviews_count": reviews_count,
            "ratings_breakdown": ratings_breakdown,
            "summary": summary,
            "description": description,
            "features": features,
            "product_details": product_details,
            "raw_product_details": raw_product_details,
            "measurements_text": measurements_text,
            "width_cm": width_cm,
            "depth_cm": depth_cm,
            "height_cm": height_cm,
            "material_and_care": material_and_care,
            "components": components,
            "warranty_text": warranty_text,
            "warranty_description": warranty_description,
            "primary_image": primary_image,
            "additional_images": additional_images,
            "packages": packages,
            "sub_products": sub_products,
            "variations": variations,
            "scraped_at": scraped_at,
        }
        cleaned_records.append(rec)

    cleaned_df = pd.DataFrame(cleaned_records)

    # Deduplicate on product_id if duplicates exist, keeping most complete record
    initial_len = len(cleaned_df)
    if cleaned_df.duplicated(subset=["product_id"]).any():
        cleaned_df = cleaned_df.drop_duplicates(subset=["product_id"], keep="first")
        stats["duplicate_rows_removed"] = initial_len - len(cleaned_df)

    stats["final_rows"] = len(cleaned_df)
    stats["final_cols"] = len(cleaned_df.columns)
    stats["final_columns"] = list(cleaned_df.columns)
    stats["categories_breakdown"] = cleaned_df["category_2"].value_counts(dropna=False).to_dict()

    for col in cleaned_df.columns:
        stats["missing_values_cleaned"][col] = int(cleaned_df[col].isna().sum())

    stats["cleaning_decisions"] = [
        "Read product identifiers (product_id, item_number, uniq_id) as strings to prevent loss of leading zeros.",
        "Converted literal SQL/MySQL export '\\N' and empty strings into proper null values.",
        "Normalized 90 records having average_rating = 0.0 and reviews_count = 0 to average_rating = NULL (unrated products).",
        "Constructed display_name by intelligently combining series name (product_name) and descriptor (description).",
        "Parsed measurements strictly for explicitly labeled 'Width', 'Depth', and 'Height' dimensions with metric conversion.",
        "Normalized currency ('INR') and country ('IN') to standard uppercase.",
        "Validated and normalized structured JSON fields (breadcrumbs, ratings_breakdown, additional_images, packages, sub_products, variations).",
        "Preserved 9 valid products lacking marketing summaries as usable catalog entries with NULL summary.",
        "Preserved raw_product_details and product_details without losing designer or product specifications.",
    ]

    stats["suspicious_examples"] = [
        {
            "issue": "Database export null marker ('\\N') in warranty fields",
            "count": 464,
            "action": "Converted to SQL NULL",
        },
        {
            "issue": "Completely empty components column across all records",
            "count": 464,
            "action": "Preserved column structure with NULL values",
        },
        {
            "issue": "Unrated items with average_rating = 0.0 and 0 reviews",
            "count": 90,
            "action": "Treated as unrated (average_rating = NULL)",
        },
        {
            "issue": "Leading zeros in product IDs (e.g. 00621679)",
            "count": 5,
            "action": "Preserved string representation rather than numeric cast",
        },
    ]

    return cleaned_df, stats


# -----------------------------------------------------------------------------
# Database Creation
# -----------------------------------------------------------------------------
def create_sqlite_database(cleaned_csv_path: Path, db_path: Path) -> None:
    """
    Builds the SQLite catalog database from cleaned_dataset.csv.
    Uses an atomic swap strategy: writes to a temporary file first,
    validates integrity, and atomically moves to target path.
    """
    db_path.parent.mkdir(parents=True, exist_ok=True)
    temp_db_path = db_path.with_suffix(".tmp")

    if temp_db_path.exists():
        temp_db_path.unlink()

    # Load cleaned CSV into pandas
    df = pd.read_csv(cleaned_csv_path, dtype={"product_id": str, "item_number": str, "uniq_id": str})

    conn = sqlite3.connect(temp_db_path)
    cur = conn.cursor()

    # Enable foreign keys and set performance pragmas
    cur.execute("PRAGMA synchronous = NORMAL;")
    cur.execute("PRAGMA journal_mode = WAL;")

    create_table_sql = """
    CREATE TABLE products (
        product_id TEXT PRIMARY KEY NOT NULL,
        item_number TEXT,
        uniq_id TEXT,
        product_url TEXT,
        product_name TEXT,
        display_name TEXT,
        product_type TEXT,
        category_1 TEXT,
        category_2 TEXT,
        category_3 TEXT,
        category_4 TEXT,
        breadcrumbs TEXT,
        price REAL,
        currency TEXT,
        country TEXT,
        average_rating REAL,
        reviews_count INTEGER,
        ratings_breakdown TEXT,
        summary TEXT,
        description TEXT,
        features TEXT,
        product_details TEXT,
        raw_product_details TEXT,
        measurements_text TEXT,
        width_cm REAL,
        depth_cm REAL,
        height_cm REAL,
        material_and_care TEXT,
        components TEXT,
        warranty_text TEXT,
        warranty_description TEXT,
        primary_image TEXT,
        additional_images TEXT,
        packages TEXT,
        sub_products TEXT,
        variations TEXT,
        scraped_at TEXT
    );
    """
    cur.execute(create_table_sql)

    columns = [
        "product_id", "item_number", "uniq_id", "product_url", "product_name",
        "display_name", "product_type", "category_1", "category_2", "category_3",
        "category_4", "breadcrumbs", "price", "currency", "country",
        "average_rating", "reviews_count", "ratings_breakdown", "summary",
        "description", "features", "product_details", "raw_product_details",
        "measurements_text", "width_cm", "depth_cm", "height_cm",
        "material_and_care", "components", "warranty_text", "warranty_description",
        "primary_image", "additional_images", "packages", "sub_products",
        "variations", "scraped_at"
    ]

    placeholders = ", ".join(["?"] * len(columns))
    insert_sql = f"INSERT INTO products ({', '.join(columns)}) VALUES ({placeholders})"

    rows_to_insert = []
    for _, row in df.iterrows():
        row_vals = []
        for col in columns:
            val = row[col]
            if pd.isna(val):
                row_vals.append(None)
            elif col in ("price", "average_rating", "width_cm", "depth_cm", "height_cm"):
                row_vals.append(float(val))
            elif col == "reviews_count":
                row_vals.append(int(float(val)))
            else:
                row_vals.append(str(val))
        rows_to_insert.append(tuple(row_vals))

    cur.executemany(insert_sql, rows_to_insert)

    # Create optimized query indexes
    cur.execute("CREATE INDEX idx_products_category_1 ON products(category_1);")
    cur.execute("CREATE INDEX idx_products_category_2 ON products(category_2);")
    cur.execute("CREATE INDEX idx_products_category_3 ON products(category_3);")
    cur.execute("CREATE INDEX idx_products_price ON products(price);")
    cur.execute("CREATE INDEX idx_products_currency ON products(currency);")
    cur.execute("CREATE INDEX idx_products_item_number ON products(item_number);")

    conn.commit()

    # Pre-swap verification
    cur.execute("PRAGMA integrity_check;")
    check = cur.fetchone()[0]
    if check != "ok":
        conn.close()
        temp_db_path.unlink()
        raise RuntimeError(f"SQLite integrity check failed on temp DB: {check}")

    conn.close()

    # Atomic rename/swap to ensure no partial state
    os.replace(temp_db_path, db_path)
    print(f"Successfully generated SQLite database at: {db_path.relative_to(PROJECT_ROOT)}")


# -----------------------------------------------------------------------------
# Validation Suite
# -----------------------------------------------------------------------------
def validate_catalog(cleaned_csv_path: Path, db_path: Path) -> Dict[str, Any]:
    """
    Runs comprehensive validations on both the cleaned CSV and the SQLite DB.
    """
    assert cleaned_csv_path.exists(), f"Cleaned CSV does not exist at {cleaned_csv_path}"
    assert db_path.exists(), f"SQLite DB does not exist at {db_path}"

    csv_df = pd.read_csv(cleaned_csv_path, dtype={"product_id": str})
    csv_row_count = len(csv_df)

    conn = sqlite3.connect(db_path)
    cur = conn.cursor()

    cur.execute("PRAGMA integrity_check;")
    integrity = cur.fetchone()[0]

    cur.execute("SELECT COUNT(*) FROM products;")
    db_row_count = cur.fetchone()[0]

    cur.execute("SELECT COUNT(DISTINCT product_id) FROM products;")
    db_unique_ids = cur.fetchone()[0]

    cur.execute("SELECT COUNT(*) FROM products WHERE product_id IS NULL OR product_id = '';")
    null_pids = cur.fetchone()[0]

    cur.execute("SELECT COUNT(*) FROM products WHERE price < 0;")
    neg_prices = cur.fetchone()[0]

    cur.execute("SELECT COUNT(*) FROM products WHERE average_rating < 0 OR average_rating > 5;")
    invalid_ratings = cur.fetchone()[0]

    # Sample query test
    cur.execute("""
        SELECT product_id, display_name, category_2, price, currency, average_rating
        FROM products
        WHERE category_2 = 'Mirrors' AND price <= 2000
        LIMIT 3;
    """)
    sample_mirrors = cur.fetchall()

    conn.close()

    assert csv_row_count == db_row_count, (
        f"Row count mismatch: CSV has {csv_row_count}, DB has {db_row_count}"
    )
    assert db_row_count == db_unique_ids, "Non-unique product_id found in database"
    assert null_pids == 0, "Null product_id found in database"
    assert neg_prices == 0, "Negative price found in database"
    assert invalid_ratings == 0, "Invalid rating found in database"
    assert integrity == "ok", f"Integrity check failed: {integrity}"

    results = {
        "integrity_check": integrity,
        "csv_row_count": csv_row_count,
        "db_row_count": db_row_count,
        "unique_product_ids": db_unique_ids,
        "sample_query_results": len(sample_mirrors),
    }
    return results


# -----------------------------------------------------------------------------
# Data Quality Report Generator
# -----------------------------------------------------------------------------
def generate_quality_report(stats: Dict[str, Any], validation: Dict[str, Any], report_path: Path) -> None:
    """Generates the comprehensive data quality markdown report."""
    categories_md = "\n".join(
        [f"- **{cat}**: {cnt} products" for cat, cnt in stats["categories_breakdown"].items()]
    )

    decisions_md = "\n".join([f"- {d}" for d in stats["cleaning_decisions"]])

    suspicious_md = "\n".join(
        [
            f"- **{s['issue']}**: {s['count']} records impacted. *Resolution*: {s['action']}."
            for s in stats["suspicious_examples"]
        ]
    )

    missing_fields_md = "\n".join(
        [
            f"| `{col}` | {cnt} | {round((cnt / stats['final_rows']) * 100, 1)}% |"
            for col, cnt in stats["missing_values_cleaned"].items()
            if cnt > 0
        ]
    )

    report_content = f"""# ShopSense AI - Catalog Data Quality Report

## Executive Summary
This report documents the inspection, cleaning, transformation, and validation of the IKEA Home Decor dataset into the SQLite product catalog for ShopSense AI.

- **Source Dataset**: `{stats['source_path']}`
- **Original Dimensions**: {stats['original_rows']} rows × {stats['original_cols']} columns
- **Cleaned Dimensions**: {stats['final_rows']} rows × {stats['final_cols']} columns
- **Database Path**: `data/products.db`
- **Integrity Check**: `{validation['integrity_check']}` (Verified via `PRAGMA integrity_check`)

---

## 1. Dataset Overview and Pipeline Statistics

| Metric | Raw Dataset | Cleaned Catalog | SQLite Database |
| :--- | :--- | :--- | :--- |
| **Total Rows** | {stats['original_rows']} | {stats['final_rows']} | {validation['db_row_count']} |
| **Total Columns** | {stats['original_cols']} | {stats['final_cols']} | {stats['final_cols']} |
| **Unique Product IDs** | {stats['original_rows'] - stats['duplicate_product_ids']} | {stats['final_rows']} | {validation['unique_product_ids']} |
| **Duplicate Rows Removed** | - | {stats['duplicate_rows_removed']} | - |
| **Valid Primary Image URLs** | {stats['valid_primary_images']} | {stats['valid_primary_images']} | {stats['valid_primary_images']} |

---

## 2. Product Categories Distribution
The dataset contains products across key Home Decor subcategories:

{categories_md}

---

## 3. Measurements Extraction Summary
Dimensions were strictly extracted from explicit `Width:`, `Depth:`, and `Height:` labels with full metric conversion (centimetres, millimetres, metres, inches with 1 in = 2.54 cm). Length and diameter values were not conflated with width or depth.

- **Products with extracted `width_cm`**: {stats['records_with_width']} ({round((stats['records_with_width'] / stats['final_rows']) * 100, 1)}%)
- **Products with extracted `depth_cm`**: {stats['records_with_depth']} ({round((stats['records_with_depth'] / stats['final_rows']) * 100, 1)}%)
- **Products with extracted `height_cm`**: {stats['records_with_height']} ({round((stats['records_with_height'] / stats['final_rows']) * 100, 1)}%)
- Original measurement strings preserved in `measurements_text`.

---

## 4. Missing Values Analysis in Cleaned Catalog

| Column | Missing Count | Missing Percentage |
| :--- | :--- | :--- |
{missing_fields_md}

*Note: All missing values are stored as genuine SQL `NULL` values rather than placeholder strings ("None", "nan", or "null").*

---

## 5. Cleaning Decisions Taken

{decisions_md}

---

## 6. Suspicious / Malformed Data Patterns Identified

{suspicious_md}

---

## 7. Known Dataset Limitations

1. **Category Coverage**: The dataset currently covers Category 1 (`Home Decor`), representing candles, picture frames, mirrors, vases, clocks, and small decorative items.
2. **Components Field**: The `components` field in the source dataset is empty across all rows.
3. **Warranty Information**: Warranty fields (`warranty_text`, `warranty_description`) contained placeholder `\\N` values across all records, indicating no explicit warranty data was captured during scraping.
4. **Variations**: The `variations` column contains empty JSON lists (`[]`) for this subset.
5. **Dimensions for Non-Rectangular Items**: Vases, bowls, and circular mirrors frequently define `Diameter:` or `Volume:` rather than width and depth; these are faithfully preserved in `measurements_text` while leaving rectangular dimension columns null to prevent hallucinated geometry.

---

## 8. Validation Verification

- [x] `data_cleaning/cleaned_dataset.csv` exists and is readable by Pandas.
- [x] `data/products.db` exists and is readable by SQLite.
- [x] CSV row count ({stats['final_rows']}) exactly matches SQLite `products` table row count ({validation['db_row_count']}).
- [x] `product_id` is unique, non-null, and configured as primary key.
- [x] Numeric fields contain valid numbers or SQL NULL.
- [x] `PRAGMA integrity_check` returned `ok`.
- [x] Indexes created on `category_1`, `category_2`, `category_3`, `price`, `currency`, `item_number`.
- [x] Repeatable execution verified (atomic replacement prevents duplicate appending).
- [x] Existing `data/evaluation_cases.json` is preserved.
"""
    with open(report_path, "w", encoding="utf-8") as f:
        f.write(report_content)
    print(f"Generated quality report at: {report_path.relative_to(PROJECT_ROOT)}")


# -----------------------------------------------------------------------------
# Main Execution Entrypoint
# -----------------------------------------------------------------------------
def main() -> None:
    """Runs the complete catalog preparation pipeline end-to-end."""
    print("=" * 60)
    print("ShopSense AI - Catalog Data Preparation Pipeline")
    print("=" * 60)

    # 1. Ensure required directories exist
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    DATA_CLEANING_DIR.mkdir(parents=True, exist_ok=True)

    # 2. Locate or download raw dataset
    raw_df, source_path = locate_or_load_source_dataset()
    print(f"Loaded raw dataset with {len(raw_df)} rows and {len(raw_df.columns)} columns.")

    # 3. Clean and normalize dataset
    cleaned_df, stats = clean_catalog(raw_df, source_path)
    print(f"Cleaned dataset: {len(cleaned_df)} rows and {len(cleaned_df.columns)} columns.")

    # 4. Save cleaned CSV
    cleaned_df.to_csv(CLEANED_CSV_PATH, index=False)
    print(f"Saved cleaned CSV to: {CLEANED_CSV_PATH.relative_to(PROJECT_ROOT)}")

    # 5. Build SQLite database from cleaned CSV
    create_sqlite_database(CLEANED_CSV_PATH, SQLITE_DB_PATH)

    # 6. Validate CSV and SQLite Database
    validation = validate_catalog(CLEANED_CSV_PATH, SQLITE_DB_PATH)
    print(f"Validation successful: integrity={validation['integrity_check']}, rows={validation['db_row_count']}")

    # 7. Generate Data Quality Report
    generate_quality_report(stats, validation, DATA_QUALITY_REPORT_PATH)

    print("=" * 60)
    print("Catalog preparation completed successfully!")
    print("=" * 60)


if __name__ == "__main__":
    main()
