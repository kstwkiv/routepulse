"""
RoutePulse — Overview Page
Top-level KPIs, trends over time, and city-level performance.
"""

import sys
import os
import time
import streamlit as st
import plotly.express as px
import plotly.graph_objects as go

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from streamlit_app.utils.styles import (
    inject_global_css, page_header, section_header, empty_state,
    COLOR_DELAYED, COLOR_ON_TIME, COLOR_IN_TRANSIT, make_plotly_layout, BRAND_COLORS
)
from streamlit_app.utils.db import duckdb_exists

st.set_page_config(page_title="Overview — RoutePulse", page_icon="📊", layout="wide")
inject_global_css()

page_header("📊 Overview", "High-level metrics and trend analysis")

# ---------------------------------------------------------------------------
# Check if DuckDB exists
# ---------------------------------------------------------------------------
if not duckdb_exists():
    empty_state("DuckDB database not found. The ETL pipeline may not have run yet.")
    st.stop()

# ---------------------------------------------------------------------------
# Cached data fetching
# ---------------------------------------------------------------------------
from analytics.queries import (
    get_summary_metrics,
    get_orders_at_risk,
    get_orders_over_time,
    get_city_performance,
)

@st.cache_data(ttl=300)
def fetch_summary():
    return get_summary_metrics()

@st.cache_data(ttl=300)
def fetch_at_risk():
    return get_orders_at_risk()

@st.cache_data(ttl=300)
def fetch_orders_time(days):
    return get_orders_over_time(days)

@st.cache_data(ttl=300)
def fetch_city_perf():
    return get_city_performance()

# ---------------------------------------------------------------------------
# Top KPIs
# ---------------------------------------------------------------------------
metrics = fetch_summary()
at_risk = fetch_at_risk()

col1, col2, col3, col4, col5, col6 = st.columns(6)

with col1:
    st.metric("Total Orders", f"{metrics['total_orders']:,}")

with col2:
    st.metric("Delivered", f"{metrics['delivered_orders']:,}")

with col3:
    st.metric(
        "Delayed Orders",
        f"{metrics['delayed_orders']:,}",
        delta=f"{metrics['delay_pct']:.1f}% of total",
        delta_color="inverse",
    )

with col4:
    st.metric(
        "Delay %",
        f"{metrics['delay_pct']:.1f}%",
        delta_color="off",
    )

with col5:
    st.metric("Avg Delivery Days", f"{metrics['avg_delivery_days']:.1f}")

with col6:
    st.metric(
        "At Risk",
        f"{at_risk:,}",
        help="In Transit orders approaching promised delivery date",
    )

st.markdown("---")

# ---------------------------------------------------------------------------
# Trends over last 7 days
# ---------------------------------------------------------------------------
section_header("📈 Order & Delay Trends (Last 7 Days)")

df_time = fetch_orders_time(7)

if df_time.empty:
    empty_state("No time-series data available.")
else:
    col_left, col_right = st.columns(2)

    with col_left:
        fig_orders = px.line(
            df_time,
            x="order_date",
            y=["total_orders", "delivered_orders"],
            title="Orders Over Time",
            labels={"value": "Count", "order_date": "Date"},
            color_discrete_sequence=[BRAND_COLORS[0], COLOR_ON_TIME],
        )
        fig_orders.update_layout(**make_plotly_layout())
        st.plotly_chart(fig_orders, use_container_width=True)

    with col_right:
        fig_delays = px.line(
            df_time,
            x="order_date",
            y="delayed_orders",
            title="Delayed Orders Over Time",
            labels={"delayed_orders": "Delayed Count", "order_date": "Date"},
            color_discrete_sequence=[COLOR_DELAYED],
        )
        fig_delays.update_layout(**make_plotly_layout())
        st.plotly_chart(fig_delays, use_container_width=True)

st.markdown("---")

# ---------------------------------------------------------------------------
# City Performance
# ---------------------------------------------------------------------------
section_header("🏙️ Delivery Performance by City")

df_city = fetch_city_perf()

if df_city.empty:
    empty_state("No city-level data available.")
else:
    # Sort by on_time_pct descending for the chart
    df_city_sorted = df_city.sort_values("on_time_pct", ascending=True)

    fig_city = px.bar(
        df_city_sorted,
        x="on_time_pct",
        y="city",
        orientation="h",
        title="On-Time Delivery Rate by City (%)",
        labels={"on_time_pct": "On-Time %", "city": "City"},
        color="on_time_pct",
        color_continuous_scale=["#FF4B4B", "#FFD700", "#00CC88"],
        text="on_time_pct",
    )
    fig_city.update_traces(texttemplate="%{text:.1f}%", textposition="outside")
    fig_city.update_layout(**make_plotly_layout(height=400))
    fig_city.update_layout(coloraxis_showscale=False)
    st.plotly_chart(fig_city, use_container_width=True)

    # Show data table
    with st.expander("📄 View City Data Table"):
        display_cols = ["city", "total_orders", "on_time_orders", "delayed_orders", "on_time_pct"]
        st.dataframe(
            df_city[display_cols].sort_values("on_time_pct", ascending=False),
            use_container_width=True,
            hide_index=True,
        )

# ---------------------------------------------------------------------------
# Auto-refresh every 5 minutes
# ---------------------------------------------------------------------------
REFRESH_INTERVAL_SEC = 300

if "last_refresh_overview" not in st.session_state:
    st.session_state["last_refresh_overview"] = time.time()

elapsed = time.time() - st.session_state["last_refresh_overview"]
remaining = max(0, int(REFRESH_INTERVAL_SEC - elapsed))

if remaining == 0:
    st.session_state["last_refresh_overview"] = time.time()
    st.rerun()

st.caption(f"Auto-refresh in {remaining // 60}m {remaining % 60}s")
