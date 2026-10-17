"""
pages/3_Compare_Products.py — Product Comparison Workspace
Side-by-side comparison of 2-4 real products with attribute tables and AI-summarized trade-offs.
"""
from __future__ import annotations

import streamlit as st

st.set_page_config(
    page_title="Compare Products — ShopSense AI",
    page_icon="⚖️",
    layout="wide",
    initial_sidebar_state="expanded",
)

from shopsense.agent.prompts import COMPARISON_PROMPT
from shopsense.catalog.loader import get_product_by_id, get_products_by_ids, load_all_products
from shopsense.config import GEMINI_AVAILABLE, GEMINI_MODEL, GOOGLE_API_KEY
from shopsense.schemas import Product
from shopsense.ui.components import (
    render_empty_state,
    render_product_card,
    render_product_comparison,
    render_section_heading,
)
from shopsense.ui.styles import brand_sidebar, inject_styles

inject_styles()
brand_sidebar()

if "compare_ids" not in st.session_state:
    st.session_state.compare_ids = set()

st.title("⚖️ Compare Products")
st.caption("Side-by-side evaluation of specifications, dimensions, materials, and pricing from our verified catalog.")

# Helper to compute deterministic facts
def compute_comparison_facts(products: list[Product]) -> dict:
    prices = [(p.display_name, p.price) for p in products if p.price is not None]
    facts = {}
    if prices:
        cheapest = min(prices, key=lambda x: x[1])
        priciest = max(prices, key=lambda x: x[1])
        facts["cheapest"] = f"{cheapest[0]} (₹{cheapest[1]:,.0f})"
        facts["priciest"] = f"{priciest[0]} (₹{priciest[1]:,.0f})"
        if len(prices) > 1 and priciest[1] != cheapest[1]:
            diff = priciest[1] - cheapest[1]
            facts["price_diff"] = f"₹{diff:,.0f} difference between lowest and highest"
    
    widths = [(p.display_name, p.width_cm) for p in products if p.width_cm is not None]
    if widths and len(widths) > 1:
        smallest_w = min(widths, key=lambda x: x[1])
        largest_w = max(widths, key=lambda x: x[1])
        facts["width_diff"] = f"Width ranges from {smallest_w[1]} cm ({smallest_w[0]}) to {largest_w[1]} cm ({largest_w[0]})"

    return facts

# Add more products dropdown
all_catalog_items = load_all_products()
options_map = {f"{p.display_name} (₹{p.price:,.0f} | ID: {p.product_id})" if p.price else f"{p.display_name} (ID: {p.product_id})": p.product_id for p in all_catalog_items}

col_sel, col_btn = st.columns([3, 1])
with col_sel:
    add_selection = st.selectbox(
        "Add a product to comparison",
        ["Select a product to add..."] + list(options_map.keys()),
        index=0,
    )
with col_btn:
    st.write("") # spacing
    if st.button("+ Add to Tray", width="stretch"):
        if add_selection != "Select a product to add...":
            chosen_id = options_map[add_selection]
            if len(st.session_state.compare_ids) < 4:
                st.session_state.compare_ids.add(chosen_id)
                st.rerun()
            else:
                st.warning("You can compare up to 4 products at once.")

# Get currently selected products
current_ids = list(st.session_state.compare_ids)
selected_products = get_products_by_ids(current_ids)

# Check if fewer than 2 products
if len(selected_products) < 2:
    if len(selected_products) == 1:
        st.info(f"You have selected **1 product** ({selected_products[0].display_name}). Select at least one more product to view comparison.")
        render_product_card(selected_products[0], show_add_to_compare=True)
    else:
        render_empty_state(
            "No products selected for comparison",
            "Browse products from the Home or Search pages and click '+ Compare', or pick an item from the dropdown above.",
            icon="⚖️",
        )
else:
    # Action bar
    act_col1, act_col2 = st.columns([4, 1])
    with act_col2:
        if st.button("🗑️ Clear All Selections", width="stretch"):
            st.session_state.compare_ids = set()
            st.rerun()

    # Product Cards Row
    render_section_heading("Selected Items")
    card_cols = st.columns(len(selected_products))
    for col, prod in zip(card_cols, selected_products):
        with col:
            render_product_card(prod, show_add_to_compare=True)

    # Detailed Attribute Comparison Table
    render_section_heading("Side-by-Side Specifications")
    render_product_comparison(selected_products)

    # AI-Generated Comparison Summary
    render_section_heading("Comparison Summary & Trade-Offs")
    facts = compute_comparison_facts(selected_products)
    
    # Context formatted for LLM or deterministic fallback
    lines = []
    for p in selected_products:
        dim_str = f"W: {p.width_cm or 'N/A'}cm, D: {p.depth_cm or 'N/A'}cm, H: {p.height_cm or 'N/A'}cm"
        lines.append(
            f"- {p.display_name}: Price={p.price_display}, Category={p.category_2 or 'N/A'}, Dimensions={dim_str}, Rating={p.rating_display if p.average_rating else 'N/A'}, Material={p.material_and_care or 'Not specified'}"
        )
    for k, v in facts.items():
        lines.append(f"[Python Computed Fact] {k}: {v}")
    
    context_text = "\n".join(lines)

    summary_text = ""
    if GEMINI_AVAILABLE:
        try:
            from langchain_google_genai import ChatGoogleGenerativeAI
            llm = ChatGoogleGenerativeAI(
                model=GEMINI_MODEL,
                google_api_key=GOOGLE_API_KEY,
                temperature=0.2,
                max_retries=1,
            )
            chain = COMPARISON_PROMPT | llm
            res = chain.invoke({
                "products_context": context_text,
                "count": len(selected_products),
            })
            from shopsense.agent.shopping_agent import _extract_text_content
            summary_text = _extract_text_content(res.content)
        except Exception as e:
            # Fallback to deterministic summary
            pass

    if not summary_text:
        # Deterministic summary
        items_summary = []
        if "cheapest" in facts and "priciest" in facts and facts["cheapest"] != facts["priciest"]:
            items_summary.append(f"**Budget:** Lowest priced item is {facts['cheapest']}, while the highest priced is {facts['priciest']}.")
        if "width_diff" in facts:
            items_summary.append(f"**Dimensions:** {facts['width_diff']}.")
        ratings = [f"{p.display_name} ({p.average_rating}★)" for p in selected_products if p.average_rating]
        if ratings:
            items_summary.append(f"**Customer Feedback:** Recorded ratings include {', '.join(ratings)}.")
        
        summary_text = "\n\n".join(items_summary) if items_summary else "Review the attribute table above to evaluate pricing and dimension trade-offs."

    st.markdown(
        f"""
        <div style="background: #FFFFFF; border-left: 4px solid #7C6FCD; border-radius: 8px; padding: 16px; margin: 16px 0; border: 1px solid #E8E4DC; border-left-width: 4px;">
          <div style="font-weight: 600; color: #1A1A2E; margin-bottom: 8px;">Key Trade-Offs:</div>
          <div style="font-size: 0.95rem; color: #333344; line-height: 1.6;">{summary_text}</div>
        </div>
        """,
        unsafe_allow_html=True,
    )
