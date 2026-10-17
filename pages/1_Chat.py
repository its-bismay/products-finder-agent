"""
pages/1_Chat.py — ShopSense AI Conversational Shopping Assistant
Catalog-grounded multi-turn conversational shopping assistant.
"""
from __future__ import annotations

import streamlit as st

st.set_page_config(
    page_title="AI Shopping Assistant — ShopSense AI",
    page_icon="💬",
    layout="wide",
    initial_sidebar_state="expanded",
)

from shopsense.agent.shopping_agent import run_shopping_agent
from shopsense.catalog.loader import get_products_by_ids
from shopsense.config import GEMINI_AVAILABLE
from shopsense.ui.components import (
    render_empty_state,
    render_info_banner,
    render_product_card,
    render_section_heading,
)
from shopsense.ui.styles import brand_sidebar, inject_styles

inject_styles()
brand_sidebar()

# Initialize session states
if "messages" not in st.session_state:
    st.session_state.messages = []
if "compare_ids" not in st.session_state:
    st.session_state.compare_ids = set()

# Header
st.title("💬 ShopSense AI Shopping Assistant")
st.caption("Ask in plain English — all recommendations are strictly verified against our IKEA Home Decor catalog.")

# Status badge for API key
if not GEMINI_AVAILABLE:
    st.warning(
        "⚠️ Google Gemini API key not detected. ShopSense AI is running in deterministic catalog fallback mode "
        "(keyword matching & parameterised SQL filters). Add `GOOGLE_API_KEY` to `.env` or Streamlit Secrets for full AI understanding."
    )

# Sidebar controls
with st.sidebar:
    st.subheader("Assistant Controls")
    if st.button("🧹 Clear Conversation", width="stretch"):
        st.session_state.messages = []
        if "pending_query" in st.session_state:
            del st.session_state["pending_query"]
        st.rerun()

    st.divider()
    st.markdown("**Comparison Tray**")
    compare_count = len(st.session_state.compare_ids)
    st.write(f"Items in comparison: **{compare_count} / 4**")
    if compare_count > 0:
        if st.button("⚖️ Go to Comparison Table", width="stretch"):
            st.switch_page("pages/3_Compare_Products.py")
        if st.button("Empty Tray", width="stretch"):
            st.session_state.compare_ids = set()
            st.rerun()

# Render existing chat history
for msg in st.session_state.messages:
    with st.chat_message(msg["role"]):
        st.markdown(msg["content"])
        if msg.get("products"):
            # Load and render verified products
            products = get_products_by_ids(msg["products"])
            if products:
                st.markdown("<div style='margin-top: 12px;'></div>", unsafe_allow_html=True)
                cols = st.columns(min(len(products), 3))
                for i, prod in enumerate(products):
                    with cols[i % len(cols)]:
                        render_product_card(prod, show_add_to_compare=True)
        if msg.get("method_badge"):
            st.caption(f"Search mode: {msg['method_badge']}")

# Check if a pending query was passed from the Home page
pending_query = st.session_state.pop("pending_query", None)
user_query = st.chat_input("E.g., Find minimalist vases under ₹1,000, or frames around 30x40 cm...")

# Determine which query to run (user typing takes priority, or pending query)
active_query = user_query if user_query else pending_query

if active_query:
    # 1. Add user message
    st.session_state.messages.append({"role": "user", "content": active_query})
    with st.chat_message("user"):
        st.markdown(active_query)

    # 2. Run agent pipeline
    with st.chat_message("assistant"):
        with st.spinner("Searching catalog and verifying specifications..."):
            response, verified_products = run_shopping_agent(
                active_query,
                chat_history=st.session_state.messages[:-1],
            )

        # 3. Display response explanation
        st.markdown(response.answer)

        # 4. Display products or empty state
        if verified_products:
            st.markdown("<div style='margin-top: 12px;'></div>", unsafe_allow_html=True)
            cols = st.columns(min(len(verified_products), 3))
            for i, prod in enumerate(verified_products):
                with cols[i % len(cols)]:
                    render_product_card(prod, show_add_to_compare=True)
        elif response.no_results:
            render_empty_state(
                "No matching products found",
                "None of the products in the catalog satisfied all your criteria. Try loosening budget or dimension constraints.",
            )

        # Save to chat history
        st.session_state.messages.append({
            "role": "assistant",
            "content": response.answer,
            "products": [p.product_id for p in verified_products],
            "method_badge": response.retrieval_method,
        })
