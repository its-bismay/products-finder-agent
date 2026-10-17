"""
pages/4_Evaluation_Dashboard.py — ShopSense AI Benchmark & Quality Evaluation
Evaluates retrieval accuracy, guardrail enforcement, constraint satisfaction,
and factual grounding across the 20 benchmark test cases.
"""
from __future__ import annotations

import pandas as pd
import streamlit as st

st.set_page_config(
    page_title="Evaluation Dashboard — ShopSense AI",
    page_icon="📊",
    layout="wide",
    initial_sidebar_state="expanded",
)

from shopsense.evaluation.runner import (
    load_evaluation_cases,
    load_latest_results,
    run_evaluation,
)
from shopsense.ui.components import (
    render_empty_state,
    render_metric_card,
    render_section_heading,
)
from shopsense.ui.styles import brand_sidebar, inject_styles

inject_styles()
brand_sidebar()

st.title("📊 Evaluation Dashboard")
st.caption(
    "Live benchmark assessing catalog retrieval accuracy, deterministic constraint filtering, "
    "and input/output guardrail enforcement against 20 curated test cases."
)

# Benchmark metadata
cases = load_evaluation_cases()
total_cases = len(cases)
categories = sorted({c.category for c in cases})

# Top summary row
c1, c2, c3, c4 = st.columns(4)
with c1:
    render_metric_card("Benchmark Cases", total_cases, "From data/evaluation_cases.json")
with c2:
    render_metric_card("Test Categories", len(categories), "Covering search, bounds & safety")

# Check for saved run
latest_run = load_latest_results()

with c3:
    if latest_run:
        timestamp_str = latest_run.get("run_timestamp", "")[:19].replace("T", " ")
        render_metric_card("Latest Run", timestamp_str, "UTC timestamp")
    else:
        render_metric_card("Latest Run", "None", "No evaluation executed yet")

with c4:
    if latest_run and "summary" in latest_run:
        overall = latest_run["summary"].get("overall_pass_rate", 0.0)
        render_metric_card("Pass Rate", f"{overall * 100:.1f}%", f"{latest_run['summary'].get('passed', 0)} / {total_cases} passed")
    else:
        render_metric_card("Status", "Ready", "Click 'Run Evaluation' below")

st.markdown("<div style='margin-top: 24px;'></div>", unsafe_allow_html=True)

# Run Evaluation Controls
st.markdown(
    """
    <div style="background: #FFFFFF; border: 1px solid #E8E4DC; border-radius: 10px; padding: 18px; margin-bottom: 24px;">
      <h4 style="margin: 0 0 8px 0; color: #1A1A2E;">Run Live Evaluation Benchmark</h4>
      <p style="font-size: 0.9rem; color: #666; margin-bottom: 12px;">
        Executing this evaluation tests all 20 benchmark queries through our full pipeline
        (deterministic input guardrails, query understanding, SQL retrieval, output validation).
      </p>
    </div>
    """,
    unsafe_allow_html=True,
)

if st.button("🚀 Run Evaluation Suite Now", type="primary", width="content"):
    progress_bar = st.progress(0)
    status_text = st.empty()

    def update_progress(current: int, total: int, case_name: str):
        pct = current / total if total else 1.0
        progress_bar.progress(pct)
        status_text.text(f"Testing case {current}/{total}: {case_name}")

    with st.spinner("Running 20-case evaluation benchmark..."):
        latest_run = run_evaluation(progress_callback=update_progress)
        progress_bar.empty()
        status_text.empty()
        st.success("✅ Evaluation complete! Results saved to `reports/evaluation_results.json`.")
        st.rerun()

# Display Results
if latest_run and "summary" in latest_run:
    summary = latest_run["summary"]
    results_list = latest_run.get("results", [])

    render_section_heading("Benchmark Performance Overview")
    m1, m2, m3, m4 = st.columns(4)
    with m1:
        pass_rate = summary.get("overall_pass_rate", 0) * 100
        render_metric_card("Overall Pass Rate", f"{pass_rate:.1f}%", f"{summary.get('passed', 0)} of {summary.get('total', 0)} cases")
    with m2:
        g_rate = summary.get("guardrail_pass_rate")
        g_val = f"{g_rate * 100:.1f}%" if g_rate is not None else "N/A"
        render_metric_card("Guardrail Accuracy", g_val, f"{summary.get('guardrail_cases', 0)} safety & prompt injection cases")
    with m3:
        recall = summary.get("avg_recall_at_5")
        r_val = f"{recall * 100:.1f}%" if recall is not None else "N/A"
        render_metric_card("Avg Recall@5", r_val, "For catalog product retrieval")
    with m4:
        precision = summary.get("avg_precision_at_5")
        p_val = f"{precision * 100:.1f}%" if precision is not None else "N/A"
        render_metric_card("Avg Precision@5", p_val, "Top-5 relevance density")

    # Category Breakdown Chart
    render_section_heading("Pass Rate by Category")
    by_cat = summary.get("by_category", {})
    if by_cat:
        chart_data = []
        for cat, stats in by_cat.items():
            tot = stats["total"]
            ps = stats["passed"]
            pct = (ps / tot * 100) if tot else 0
            chart_data.append({
                "Category": cat.replace("_", " ").title(),
                "Pass Rate (%)": pct,
                "Passed": ps,
                "Total": tot,
            })
        chart_df = pd.DataFrame(chart_data).set_index("Category")
        st.bar_chart(chart_df["Pass Rate (%)"])

    # Detailed Results Table
    render_section_heading("Detailed Test Case Outcomes")
    table_rows = []
    for r in results_list:
        table_rows.append({
            "Case ID": r.get("case_id"),
            "Category": r.get("category"),
            "Query": r.get("user_query"),
            "Passed": "✅ PASS" if r.get("passed") else "❌ FAIL",
            "Expected IDs": ", ".join(r.get("expected_product_ids", [])) or "—",
            "Retrieved IDs": ", ".join(r.get("actual_product_ids", [])) or "—",
            "Failure Reason": r.get("failure_reason") or "None",
        })
    df_table = pd.DataFrame(table_rows)
    st.dataframe(df_table, width="stretch")

    # Failed Cases Expander
    failed_cases = [r for r in results_list if not r.get("passed")]
    if failed_cases:
        with st.expander(f"⚠️ View Failed Cases ({len(failed_cases)})", expanded=True):
            for fc in failed_cases:
                st.markdown(
                    f"""
                    **Case `{fc.get('case_id')}`** — *{fc.get('category')}*  
                    - **Query:** "{fc.get('user_query')}"  
                    - **Failure Reason:** `{fc.get('failure_reason')}`  
                    - **Expected IDs:** `{fc.get('expected_product_ids')}`  
                    - **Actual IDs:** `{fc.get('actual_product_ids')}`  
                    ---
                    """
                )
    else:
        st.success("🎉 All benchmark test cases passed successfully!")

    # Known Limitations & Methodology
    with st.expander("ℹ️ Benchmark Methodology & Known Limitations"):
        st.markdown(
            """
            - **Deterministic Scoring:** All precision, recall, and constraint validation checks are computed directly in Python from catalog database records. No LLM judge is used to evaluate the LLM.
            - **Catalog Coverage:** Queries with `expected_product_ids` verify that the specific ground truth products appear in the top-5 retrieved results.
            - **Keyword vs Semantic Embeddings:** When a Google Gemini API key is configured, embeddings from `text-embedding-004` (cached locally in `data/embeddings_cache.npz`) enable semantic search. In offline or fallback mode, tokenized SQLite `LIKE` matching is used.
            - **No Results Handling:** Queries seeking non-existent products (e.g., items over ₹100,000) are evaluated on whether they honestly report zero exact matches rather than hallucinating products.
            - **Guardrails:** Tests verify that out-of-scope requests (e.g. electronics), dangerous instructions (e.g. explosives), and prompt injections are intercepted deterministically before any LLM processing.
            """
        )
else:
    render_empty_state(
        "No evaluation run recorded yet",
        "Click the 'Run Evaluation Suite Now' button above to execute the 20 benchmark test cases and view real accuracy, precision, and recall metrics.",
        icon="📊",
    )
