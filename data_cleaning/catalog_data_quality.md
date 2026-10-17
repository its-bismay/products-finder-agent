# ShopSense AI - Catalog Data Quality Report

## Executive Summary
This report documents the inspection, cleaning, transformation, and validation of the IKEA Home Decor dataset into the SQLite product catalog for ShopSense AI.

- **Source Dataset**: `data_cleaning/crawlfeeds_ikea__limit-100000_category_1-home-decor_20260409_190938.csv`
- **Original Dimensions**: 464 rows × 35 columns
- **Cleaned Dimensions**: 464 rows × 37 columns
- **Database Path**: `data/products.db`
- **Integrity Check**: `ok` (Verified via `PRAGMA integrity_check`)

---

## 1. Dataset Overview and Pipeline Statistics

| Metric | Raw Dataset | Cleaned Catalog | SQLite Database |
| :--- | :--- | :--- | :--- |
| **Total Rows** | 464 | 464 | 464 |
| **Total Columns** | 35 | 37 | 37 |
| **Unique Product IDs** | 464 | 464 | 464 |
| **Duplicate Rows Removed** | - | 0 | - |
| **Valid Primary Image URLs** | 464 | 464 | 464 |

---

## 2. Product Categories Distribution
The dataset contains products across key Home Decor subcategories:

- **Wall decor**: 131 products
- **Candle holders & candles**: 99 products
- **Mirrors**: 91 products
- **Vases & bowls**: 71 products
- **Clocks**: 35 products
- **Decorative accessories**: 16 products
- **Stationery, wrapping paper, gift bags & accessories**: 9 products
- **Home fragrance**: 6 products
- **Christmas decoration**: 6 products

---

## 3. Measurements Extraction Summary
Dimensions were strictly extracted from explicit `Width:`, `Depth:`, and `Height:` labels with full metric conversion (centimetres, millimetres, metres, inches with 1 in = 2.54 cm). Length and diameter values were not conflated with width or depth.

- **Products with extracted `width_cm`**: 134 (28.9%)
- **Products with extracted `depth_cm`**: 77 (16.6%)
- **Products with extracted `height_cm`**: 266 (57.3%)
- Original measurement strings preserved in `measurements_text`.

---

## 4. Missing Values Analysis in Cleaned Catalog

| Column | Missing Count | Missing Percentage |
| :--- | :--- | :--- |
| `category_4` | 26 | 5.6% |
| `average_rating` | 90 | 19.4% |
| `summary` | 9 | 1.9% |
| `measurements_text` | 13 | 2.8% |
| `width_cm` | 330 | 71.1% |
| `depth_cm` | 387 | 83.4% |
| `height_cm` | 198 | 42.7% |
| `components` | 464 | 100.0% |
| `warranty_text` | 464 | 100.0% |
| `warranty_description` | 464 | 100.0% |

*Note: All missing values are stored as genuine SQL `NULL` values rather than placeholder strings ("None", "nan", or "null").*

---

## 5. Cleaning Decisions Taken

- Read product identifiers (product_id, item_number, uniq_id) as strings to prevent loss of leading zeros.
- Converted literal SQL/MySQL export '\N' and empty strings into proper null values.
- Normalized 90 records having average_rating = 0.0 and reviews_count = 0 to average_rating = NULL (unrated products).
- Constructed display_name by intelligently combining series name (product_name) and descriptor (description).
- Parsed measurements strictly for explicitly labeled 'Width', 'Depth', and 'Height' dimensions with metric conversion.
- Normalized currency ('INR') and country ('IN') to standard uppercase.
- Validated and normalized structured JSON fields (breadcrumbs, ratings_breakdown, additional_images, packages, sub_products, variations).
- Preserved 9 valid products lacking marketing summaries as usable catalog entries with NULL summary.
- Preserved raw_product_details and product_details without losing designer or product specifications.

---

## 6. Suspicious / Malformed Data Patterns Identified

- **Database export null marker ('\N') in warranty fields**: 464 records impacted. *Resolution*: Converted to SQL NULL.
- **Completely empty components column across all records**: 464 records impacted. *Resolution*: Preserved column structure with NULL values.
- **Unrated items with average_rating = 0.0 and 0 reviews**: 90 records impacted. *Resolution*: Treated as unrated (average_rating = NULL).
- **Leading zeros in product IDs (e.g. 00621679)**: 5 records impacted. *Resolution*: Preserved string representation rather than numeric cast.

---

## 7. Known Dataset Limitations

1. **Category Coverage**: The dataset currently covers Category 1 (`Home Decor`), representing candles, picture frames, mirrors, vases, clocks, and small decorative items.
2. **Components Field**: The `components` field in the source dataset is empty across all rows.
3. **Warranty Information**: Warranty fields (`warranty_text`, `warranty_description`) contained placeholder `\N` values across all records, indicating no explicit warranty data was captured during scraping.
4. **Variations**: The `variations` column contains empty JSON lists (`[]`) for this subset.
5. **Dimensions for Non-Rectangular Items**: Vases, bowls, and circular mirrors frequently define `Diameter:` or `Volume:` rather than width and depth; these are faithfully preserved in `measurements_text` while leaving rectangular dimension columns null to prevent hallucinated geometry.

---

## 8. Validation Verification

- [x] `data_cleaning/cleaned_dataset.csv` exists and is readable by Pandas.
- [x] `data/products.db` exists and is readable by SQLite.
- [x] CSV row count (464) exactly matches SQLite `products` table row count (464).
- [x] `product_id` is unique, non-null, and configured as primary key.
- [x] Numeric fields contain valid numbers or SQL NULL.
- [x] `PRAGMA integrity_check` returned `ok`.
- [x] Indexes created on `category_1`, `category_2`, `category_3`, `price`, `currency`, `item_number`.
- [x] Repeatable execution verified (atomic replacement prevents duplicate appending).
- [x] Existing `data/evaluation_cases.json` is preserved.
