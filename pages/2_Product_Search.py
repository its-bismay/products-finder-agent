"""
pages/2_Product_Search.py — Searchable Product Catalog with Deterministic Filters
Search and filter products using verified SQLite parameterized queries.
"""
from __future__ import annotations

import streamlit as st

st.set_page_config(
    page_title="Product Search — ShopSense AI",
    page_icon="🔍",
    layout="wide",
    initial_sidebar_state="expanded",
)

from shopsense.catalog.loader import (
    _get_connection,
    _row_to_product,
    get_distinct_categories,
)
from shopsense.schemas import Product
from shopsense.ui.components import (
    render_empty_state,
    render_product_card,
    render_section_heading,
)
from shopsense.ui.styles import brand_sidebar, inject_styles

inject_styles()
brand_sidebar()

if "compare_ids" not in st.session_state:
    st.session_state.compare_ids = set()

st.title("🔍 Product Search & Catalog")
st.caption("Deterministic search and filtering across our IKEA Home Decor collection.")

# Sidebar Filters
with st.sidebar:
    st.subheader("Filter Catalog")

    # Category filter
    all_categories = ["All Categories"] + get_distinct_categories()
    selected_category = st.selectbox("Category", all_categories, index=0)

    # Price range
    price_range = st.slider(
        "Price Range (₹)",
        min_value=0,
        max_value=15000,
        value=(0, 15000),
        step=100,
    )

    # Minimum Rating
    min_rating = st.slider(
        "Minimum Rating",
        min_value=0.0,
        max_value=5.0,
        value=0.0,
        step=0.5,
    )

    # Dimensions filter expander
    with st.expander("Dimensions (Optional)"):
        max_width = st.number_input("Max Width (cm)", min_value=0, max_value=200, value=0, step=5)
        max_height = st.number_input("Max Height (cm)", min_value=0, max_value=200, value=0, step=5)

    # Sort order
    sort_option = st.selectbox(
        "Sort By",
        [
            "Default (Name)",
            "Price: Low to High",
            "Price: High to Low",
            "Highest Rated",
        ],
    )

    if st.button("Reset All Filters", width="stretch"):
        st.rerun()

    st.divider()
    compare_count = len(st.session_state.compare_ids)
    st.write(f"Items in comparison tray: **{compare_count} / 4**")
    if compare_count > 0:
        if st.button("⚖️ Compare Selected Items", width="stretch"):
            st.switch_page("pages/3_Compare_Products.py")

# Main Search Input
col_search, col_sort_info = st.columns([3, 1])
with col_search:
    search_text = st.text_input("Search catalog keywords", placeholder="E.g., vase, mirror, velvet cushion, scented candle...")

# Construct Deterministic Parameterized SQL
where_clauses = ["1=1"]
params = []

if selected_category != "All Categories":
    where_clauses.append("(category_2 = ? OR category_3 = ?)")
    params.extend([selected_category, selected_category])

if price_range[0] > 0:
    where_clauses.append("price >= ?")
    params.append(price_range[0])
if price_range[1] < 15000:
    where_clauses.append("price <= ?")
    params.append(price_range[1])

if min_rating > 0.0:
    where_clauses.append("average_rating >= ?")
    params.append(min_rating)

if max_width > 0:
    where_clauses.append("width_cm IS NOT NULL AND width_cm <= ?")
    params.append(max_width)

if max_height > 0:
    where_clauses.append("height_cm IS NOT NULL AND height_cm <= ?")
    params.append(max_height)

if search_text.strip():
    tokens = search_text.strip().split()
    for token in tokens:
        where_clauses.append(
            "(product_name LIKE ? OR description LIKE ? OR summary LIKE ? OR features LIKE ?)"
        )
        like_arg = f"%{token}%"
        params.extend([like_arg, like_arg, like_arg, like_arg])

# Order By
order_by = "product_name ASC"
if sort_option == "Price: Low to High":
    order_by = "price ASC NULLS LAST"
elif sort_option == "Price: High to Low":
    order_by = "price DESC NULLS LAST"
elif sort_option == "Highest Rated":
    order_by = "average_rating DESC NULLS LAST, reviews_count DESC NULLS LAST"

query = f"SELECT * FROM products WHERE {' AND '.join(where_clauses)} ORDER BY {order_by} LIMIT 100;"

with _get_connection() as conn:
    rows = conn.execute(query, params).fetchall()
    matched_products = [_row_to_product(r) for r in rows]

# Display Results Count
st.markdown(f"**Showing {len(matched_products)} products** satisfying your criteria")

# Render Products
if matched_products:
    cols = 3
    for i in range(0, len(matched_products), cols):
        batch = matched_products[i : i + cols]
        grid_cols = st.columns(len(batch))
        for col, prod in zip(grid_cols, batch):
            with col:
                render_product_card(prod, show_add_to_compare=True)
else:
    render_empty_state(
        "No matching products found",
        "No items in the catalog match all of your active filters. Try broadening the price range or clearing keyword filters.",
    )
