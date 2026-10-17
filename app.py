"""
app.py — ShopSense AI Home & Overview Page
Entry point for the Streamlit application.
"""
from __future__ import annotations

import streamlit as st

# Configure page layout
st.set_page_config(
    page_title="ShopSense AI — Home Shopping Assistant",
    page_icon="🏠",
    layout="wide",
    initial_sidebar_state="expanded",
)

from shopsense.catalog.loader import get_catalog_stats, load_all_products
from shopsense.ui.components import (
    render_metric_card,
    render_product_card,
    render_section_heading,
)
from shopsense.ui.styles import brand_sidebar, inject_styles

# Apply shared styles and brand sidebar
inject_styles()
brand_sidebar()

# Initialize session state for comparison and chat navigation
if "compare_ids" not in st.session_state:
    st.session_state.compare_ids = set()
if "messages" not in st.session_state:
    st.session_state.messages = []

# Hero Header
st.markdown(
    """
    <div style="padding: 24px 0 16px 0;">
      <span style="background: #F0EDFB; color: #5A4FB0; font-size: 0.85rem; font-weight: 600; padding: 4px 12px; border-radius: 12px;">AI-Powered Home Shopping</span>
      <h1 style="font-size: 2.4rem; font-weight: 700; color: #1A1A2E; margin-top: 12px; margin-bottom: 8px;">
        Find the right pieces for your home.
      </h1>
      <p style="font-size: 1.1rem; color: #555566; max-width: 720px; line-height: 1.6;">
        ShopSense AI uses catalog-grounded artificial intelligence to help you search,
        filter, and compare real home decor items from IKEA — with zero hallucinations and verified product specs.
      </p>
    </div>
    """,
    unsafe_allow_html=True,
)

# Call to Action Buttons
cta_col1, cta_col2, _ = st.columns([1.5, 1.5, 4])
with cta_col1:
    if st.button("💬 Start Shopping Assistant", type="primary", width="stretch"):
        st.switch_page("pages/1_Chat.py")
with cta_col2:
    if st.button("🔍 Browse Product Catalog", width="stretch"):
        st.switch_page("pages/2_Product_Search.py")

st.markdown("<div style='margin-top: 32px;'></div>", unsafe_allow_html=True)

# Overview Cards (Calculated directly from SQLite database)
render_section_heading("Catalog Overview")
stats = get_catalog_stats()

col1, col2, col3, col4 = st.columns(4)
with col1:
    render_metric_card("Total Products", f"{stats.get('total_products', 0):,}", "Verified catalog records")
with col2:
    render_metric_card("Categories", f"{stats.get('categories', 0)}", "Unique decor categories")
with col3:
    render_metric_card("With Product Images", f"{stats.get('with_images', 0):,}", "Visual showcase ready")
with col4:
    render_metric_card("With Price Info", f"{stats.get('with_price', 0):,}", "Available in INR (₹)")

st.markdown("<div style='margin-top: 32px;'></div>", unsafe_allow_html=True)

# Suggested Queries
render_section_heading("Try Asking ShopSense AI")
st.write("Click any sample query to test our catalog retrieval and guardrail pipeline:")

prompts = [
    ("💰 Budget Shopping", "Find minimalist home decor under ₹1,500"),
    ("🌿 Natural Scents", "Show me candles with a woodsy or sweet scent"),
    ("📐 Custom Dimensions", "Find artwork or frames around 30 × 40 cm"),
    ("⚖️ Compare Decor", "Compare vases by price and dimensions"),
]

prompt_cols = st.columns(len(prompts))
for idx, (title, query) in enumerate(prompts):
    with prompt_cols[idx]:
        with st.container():
            st.markdown(
                f"""
                <div style="background: #FFFFFF; border: 1px solid #E8E4DC; border-radius: 10px; padding: 14px; min-height: 105px;">
                  <div style="font-weight: 600; font-size: 0.9rem; color: #1A1A2E;">{title}</div>
                  <div style="font-size: 0.82rem; color: #666; margin-top: 6px;">"{query}"</div>
                </div>
                """,
                unsafe_allow_html=True,
            )
            if st.button("Try this query →", key=f"sq_{idx}", width="stretch"):
                st.session_state["pending_query"] = query
                st.switch_page("pages/1_Chat.py")

st.markdown("<div style='margin-top: 40px;'></div>", unsafe_allow_html=True)

# Featured Real Products
render_section_heading("Featured Catalog Items")
st.caption("A live preview of verified products loaded from the SQLite catalog.")

all_products = load_all_products()
# Select a diverse set of real products that have images and ratings
featured_candidates = [
    p for p in all_products if p.primary_image and p.average_rating and p.average_rating >= 4.0
]
if not featured_candidates:
    featured_candidates = [p for p in all_products if p.primary_image]
featured = featured_candidates[:3]

f_cols = st.columns(len(featured))
for col, prod in zip(f_cols, featured):
    with col:
        render_product_card(prod, show_add_to_compare=True)
