"""
shopsense/ui/styles.py
Shared CSS injected into every Streamlit page via st.markdown.
"""
from __future__ import annotations

GLOBAL_CSS = """
<style>
/* ── Typography ── */
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700&display=swap');

html, body, [class*="css"] {
    font-family: 'Inter', sans-serif !important;
}

/* ── Page background ── */
.stApp {
    background-color: #F8F6F2;
}

/* ── Sidebar ── */
section[data-testid="stSidebar"] {
    background-color: #FFFFFF;
    border-right: 1px solid #E8E4DC;
}
section[data-testid="stSidebar"] .stMarkdown p {
    font-size: 0.85rem;
    color: #6B6B6B;
}

/* ── Product card ── */
.product-card {
    background: #FFFFFF;
    border: 1px solid #E8E4DC;
    border-radius: 12px;
    padding: 16px;
    margin-bottom: 16px;
    transition: box-shadow 0.2s ease, transform 0.15s ease;
    cursor: default;
}
.product-card:hover {
    box-shadow: 0 4px 16px rgba(0,0,0,0.08);
    transform: translateY(-2px);
}
.product-card h4 {
    margin: 0 0 6px 0;
    font-size: 0.92rem;
    font-weight: 600;
    color: #1A1A2E;
    line-height: 1.3;
}
.product-card .price-tag {
    font-size: 1.1rem;
    font-weight: 700;
    color: #7C6FCD;
}
.product-card .category-badge {
    display: inline-block;
    background: #F0EDFB;
    color: #5A4FB0;
    font-size: 0.72rem;
    font-weight: 500;
    border-radius: 20px;
    padding: 2px 10px;
    margin-top: 4px;
}
.product-card .rating-text {
    font-size: 0.78rem;
    color: #888;
    margin-top: 4px;
}

/* ── Metric card ── */
.metric-card {
    background: #FFFFFF;
    border: 1px solid #E8E4DC;
    border-radius: 12px;
    padding: 20px;
    text-align: center;
}
.metric-card .metric-value {
    font-size: 2rem;
    font-weight: 700;
    color: #7C6FCD;
}
.metric-card .metric-label {
    font-size: 0.82rem;
    color: #888;
    margin-top: 4px;
}

/* ── Hero section ── */
.hero-section {
    background: linear-gradient(135deg, #7C6FCD 0%, #9B8FDD 100%);
    border-radius: 16px;
    padding: 36px 32px;
    color: white;
    margin-bottom: 24px;
}
.hero-section h1 {
    font-size: 1.9rem;
    font-weight: 700;
    margin: 0 0 8px 0;
}
.hero-section p {
    font-size: 1rem;
    opacity: 0.9;
    margin: 0;
}

/* ── Section heading ── */
.section-heading {
    font-size: 1.1rem;
    font-weight: 600;
    color: #1A1A2E;
    margin: 24px 0 12px 0;
    padding-bottom: 6px;
    border-bottom: 2px solid #E8E4DC;
}

/* ── Empty state ── */
.empty-state {
    text-align: center;
    padding: 48px 24px;
    color: #888;
}
.empty-state .empty-icon {
    font-size: 3rem;
    margin-bottom: 12px;
}

/* ── Comparison table ── */
.compare-table {
    width: 100%;
    border-collapse: collapse;
    font-size: 0.88rem;
}
.compare-table th {
    background: #F0EDFB;
    color: #5A4FB0;
    padding: 10px 14px;
    text-align: left;
    font-weight: 600;
}
.compare-table td {
    padding: 10px 14px;
    border-bottom: 1px solid #F0EDFB;
    color: #333;
}
.compare-table tr:hover td {
    background: #FAFAFA;
}

/* ── Alert banner ── */
.info-banner {
    background: #EEF6FF;
    border-left: 4px solid #7C6FCD;
    padding: 12px 16px;
    border-radius: 0 8px 8px 0;
    font-size: 0.87rem;
    color: #333;
    margin: 12px 0;
}

/* ── Chat messages ── */
[data-testid="stChatMessageContent"] p {
    font-size: 0.93rem;
    line-height: 1.6;
}

/* ── Buttons ── */
.stButton>button {
    border-radius: 8px;
    font-weight: 500;
    transition: all 0.15s ease;
}
</style>
"""


def inject_styles() -> None:
    """Call this at the top of every Streamlit page to apply shared styles."""
    import streamlit as st
    st.markdown(GLOBAL_CSS, unsafe_allow_html=True)


def brand_sidebar() -> None:
    """Render the brand logo/name in the sidebar."""
    import streamlit as st
    st.sidebar.markdown(
        """
        <div style="padding:16px 0 8px 0;">
          <span style="font-size:1.3rem;font-weight:700;color:#7C6FCD;">🏠 ShopSense AI</span><br>
          <span style="font-size:0.75rem;color:#888;">IKEA Home Decor Assistant</span>
        </div>
        """,
        unsafe_allow_html=True,
    )
    st.sidebar.divider()
