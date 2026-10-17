"""
shopsense/ui/components.py
Reusable Streamlit UI components for ShopSense AI.
Pure display functions — no SQL queries, no Gemini calls.
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional

import streamlit as st

from shopsense.schemas import Product


# ---------------------------------------------------------------------------
# Product card
# ---------------------------------------------------------------------------

def render_product_image(image_url: Optional[str], alt: str = "Product image") -> None:
    """Display a product image with graceful fallback."""
    if image_url and image_url.startswith("http"):
        st.image(image_url, width="stretch")
    else:
        st.markdown(
            "<div style='background:#F0EDFB;border-radius:8px;height:160px;"
            "display:flex;align-items:center;justify-content:center;"
            "color:#9B8FDD;font-size:2rem;'>🏠</div>",
            unsafe_allow_html=True,
        )


def render_product_card(product: Product, show_add_to_compare: bool = True) -> None:
    """Render a single product card inside a Streamlit container."""
    with st.container():
        st.markdown('<div class="product-card">', unsafe_allow_html=True)

        # Image
        render_product_image(product.primary_image, product.display_name)

        # Name
        st.markdown(f"**{product.display_name}**")

        # Price
        st.markdown(
            f'<span class="price-tag">{product.price_display}</span>',
            unsafe_allow_html=True,
        )

        # Category badge
        if product.category_2:
            st.markdown(
                f'<span class="category-badge">{product.category_2}</span>',
                unsafe_allow_html=True,
            )

        # Rating
        if product.average_rating:
            st.markdown(
                f'<span class="rating-text">{product.rating_display}</span>',
                unsafe_allow_html=True,
            )

        # Dimensions
        dim_parts = []
        if product.width_cm:
            dim_parts.append(f"W: {product.width_cm} cm")
        if product.depth_cm:
            dim_parts.append(f"D: {product.depth_cm} cm")
        if product.height_cm:
            dim_parts.append(f"H: {product.height_cm} cm")
        if dim_parts:
            st.caption(" · ".join(dim_parts))

        # Actions
        col_a, col_b = st.columns(2)
        with col_a:
            if product.product_url:
                st.markdown(
                    f'<a href="{product.product_url}" target="_blank" '
                    f'style="font-size:0.8rem;color:#7C6FCD;">🔗 View on IKEA</a>',
                    unsafe_allow_html=True,
                )
        with col_b:
            if show_add_to_compare:
                in_compare = product.product_id in st.session_state.get("compare_ids", set())
                btn_label = "✓ Added" if in_compare else "+ Compare"
                if st.button(btn_label, key=f"compare_{product.product_id}", width="stretch"):
                    if "compare_ids" not in st.session_state:
                        st.session_state.compare_ids = set()
                    if in_compare:
                        st.session_state.compare_ids.discard(product.product_id)
                    else:
                        if len(st.session_state.compare_ids) < 4:
                            st.session_state.compare_ids.add(product.product_id)
                        else:
                            st.warning("You can compare up to 4 products at once.")
                    st.rerun()

        st.markdown("</div>", unsafe_allow_html=True)


def render_product_grid(products: List[Product], cols: int = 3) -> None:
    """Render a responsive grid of product cards."""
    if not products:
        render_empty_state("No products found", "Try adjusting your search or filters.")
        return
    rows = [products[i : i + cols] for i in range(0, len(products), cols)]
    for row in rows:
        columns = st.columns(len(row))
        for col, product in zip(columns, row):
            with col:
                render_product_card(product)


# ---------------------------------------------------------------------------
# Metric card
# ---------------------------------------------------------------------------

def render_metric_card(label: str, value: Any, help_text: Optional[str] = None) -> None:
    """Render a styled metric card."""
    help_html = f'<div style="font-size:0.75rem;color:#aaa;margin-top:4px;">{help_text}</div>' if help_text else ""
    st.markdown(
        f"""
        <div class="metric-card">
          <div class="metric-value">{value}</div>
          <div class="metric-label">{label}</div>
          {help_html}
        </div>
        """,
        unsafe_allow_html=True,
    )


# ---------------------------------------------------------------------------
# Empty states and errors
# ---------------------------------------------------------------------------

def render_empty_state(title: str, message: str, icon: str = "🔍") -> None:
    st.markdown(
        f"""
        <div class="empty-state">
          <div class="empty-icon">{icon}</div>
          <h3 style="color:#555;margin:0 0 8px 0;">{title}</h3>
          <p style="margin:0;">{message}</p>
        </div>
        """,
        unsafe_allow_html=True,
    )


def render_error_message(message: str) -> None:
    st.markdown(
        f'<div class="info-banner" style="border-color:#E55;">⚠️ {message}</div>',
        unsafe_allow_html=True,
    )


def render_info_banner(message: str) -> None:
    st.markdown(
        f'<div class="info-banner">ℹ️ {message}</div>',
        unsafe_allow_html=True,
    )


def render_section_heading(text: str) -> None:
    st.markdown(f'<div class="section-heading">{text}</div>', unsafe_allow_html=True)


# ---------------------------------------------------------------------------
# Comparison table
# ---------------------------------------------------------------------------

def render_product_comparison(products: List[Product]) -> None:
    """Render a comparison table for 2–4 products."""
    if len(products) < 2:
        render_empty_state("Select products to compare", "Add 2–4 products from the catalog.")
        return

    fields = [
        ("Product", lambda p: p.display_name),
        ("Price", lambda p: p.price_display),
        ("Category", lambda p: p.category_2 or "—"),
        ("Rating", lambda p: p.rating_display if p.average_rating else "Not rated"),
        ("Width (cm)", lambda p: str(p.width_cm) if p.width_cm else "Not available"),
        ("Depth (cm)", lambda p: str(p.depth_cm) if p.depth_cm else "Not available"),
        ("Height (cm)", lambda p: str(p.height_cm) if p.height_cm else "Not available"),
        ("Material", lambda p: (p.material_and_care or "Not available")[:80]),
    ]

    header = "| Attribute | " + " | ".join(p.product_name for p in products) + " |"
    separator = "|---|" + "---|" * len(products)
    rows = [header, separator]
    for label, getter in fields:
        row_values = " | ".join(getter(p) for p in products)
        rows.append(f"| {label} | {row_values} |")

    st.markdown("\n".join(rows))
