"""
RoutePulse — Delay Analysis Page
Root-cause insights: worst warehouses, cities, shipping types, distance, categories.
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
    COLOR_DELAYED, COLOR_ON_TIME, COLOR_IN_TRANSIT, make_plotly_layout, BRAND_COLORS,
)
from streamlit_app.utils.db import duckdb_exists

st.set_page_config(page_title="Delay Analysis — RoutePulse", page_icon="⚠️", layout="wide")
inject_global_css()

page_header("⚠️ Delay Analysis", "Identify bottlenecks, risk factors, and performance patterns")

if not duckdb_exists():
    empty_state("DuckDB database not found. The ETL pipeline may not have run yet.")
    st.stop()

from analytics.queries import (
    get_warehouse_delay_rates,
    get_city_delay_rates,
    get_delay_by_shipping_type,
    get_delay_by_distance,
    get_delay_by_category,
    get_summary_metrics,
)

# ---------------------------------------------------------------------------
# Cached queries
# ---------------------------------------------------------------------------
@st.cache_data(ttl=300)
def fetch_warehouse_delays():  return get_warehouse_delay_rates()
@st.cache_data(ttl=300)
def fetch_city_delays():       return get_city_delay_rates()
@st.cache_data(ttl=300)
def fetch_shipping_delays():   return get_delay_by_shipping_type()
@st.cache_data(ttl=300)
def fetch_distance_delays():   return get_delay_by_distance()
@st.cache_data(ttl=300)
def fetch_category_delays():   return get_delay_by_category()
@st.cache_data(ttl=300)
def fetch_summary():           return get_summary_metrics()

df_wh     = fetch_warehouse_delays()
df_city   = fetch_city_delays()
df_ship   = fetch_shipping_delays()
df_dist   = fetch_distance_delays()
df_cat    = fetch_category_delays()
metrics   = fetch_summary()

# ---------------------------------------------------------------------------
# Key insight callouts
# ---------------------------------------------------------------------------
section_header("🔑 Key Insights")

if not df_wh.empty:
    worst_wh      = df_wh.iloc[0]
    worst_city_r  = df_city.iloc[0] if not df_city.empty else None
    overall_delay = metrics.get("delay_pct", 0)

    ic1, ic2, ic3 = st.columns(3)

    with ic1:
        st.warning(
            f"**Worst Warehouse:** {worst_wh['warehouse_id']} ({worst_wh['city']}) "
            f"has a **{worst_wh['delay_rate_pct']:.1f}%** delay rate "
            f"({int(worst_wh['delayed_orders'])} of {int(worst_wh['total_orders'])} orders delayed)."
        )

    with ic2:
        if worst_city_r is not None:
            st.warning(
                f"**Worst City:** {worst_city_r['city']} has a "
                f"**{worst_city_r['delay_rate_pct']:.1f}%** delay rate, "
                f"averaging **{worst_city_r['avg_delivery_days']:.1f} days** per delivery."
            )

    with ic3:
        if overall_delay > 20:
            st.error(
                f"🚨 Platform-wide delay rate is **{overall_delay:.1f}%**. "
                "Operational intervention may be needed."
            )
        elif overall_delay > 12:
            st.warning(
                f"⚠️ Platform-wide delay rate is **{overall_delay:.1f}%**. "
                "Monitor closely for further deterioration."
            )
        else:
            st.info(
                f"✅ Platform-wide delay rate is **{overall_delay:.1f}%**. "
                "Operations are within acceptable thresholds."
            )

st.markdown("---")

# ---------------------------------------------------------------------------
# Row 1: Worst Warehouses | City Delays
# ---------------------------------------------------------------------------
section_header("🏭 Warehouse vs City Delay Rates")

col_wh, col_city = st.columns(2)

with col_wh:
    if df_wh.empty:
        empty_state("No warehouse data.")
    else:
        fig = px.bar(
            df_wh.head(11),
            x="warehouse_id",
            y="delay_rate_pct",
            title="Delay Rate by Warehouse (%)",
            labels={"delay_rate_pct": "Delay Rate %", "warehouse_id": "Warehouse"},
            color="delay_rate_pct",
            color_continuous_scale=["#00CC88", "#FFD700", "#FF4B4B"],
            text="delay_rate_pct",
        )
        fig.update_traces(texttemplate="%{text:.1f}%", textposition="outside")
        fig.update_layout(**make_plotly_layout(height=380))
        fig.update_layout(coloraxis_showscale=False)
        st.plotly_chart(fig, use_container_width=True)

with col_city:
    if df_city.empty:
        empty_state("No city data.")
    else:
        fig = px.bar(
            df_city.sort_values("delay_rate_pct", ascending=True),
            x="delay_rate_pct",
            y="city",
            orientation="h",
            title="Delay Rate by City (%) — Highest First",
            labels={"delay_rate_pct": "Delay Rate %", "city": "City"},
            color="delay_rate_pct",
            color_continuous_scale=["#00CC88", "#FFD700", "#FF4B4B"],
            text="delay_rate_pct",
        )
        fig.update_traces(texttemplate="%{text:.1f}%", textposition="outside")
        fig.update_layout(**make_plotly_layout(height=380))
        fig.update_layout(coloraxis_showscale=False)
        st.plotly_chart(fig, use_container_width=True)

st.markdown("---")

# ---------------------------------------------------------------------------
# Row 2: Shipping Type Delays | Distance Delays
# ---------------------------------------------------------------------------
section_header("📦 Delay by Shipping Type & Distance")

col_ship, col_dist = st.columns(2)

with col_ship:
    if df_ship.empty:
        empty_state("No shipping type data.")
    else:
        fig = go.Figure()
        fig.add_trace(go.Bar(
            name="On Time",
            x=df_ship["shipping_type"],
            y=df_ship["on_time_orders"],
            marker_color=COLOR_ON_TIME,
        ))
        fig.add_trace(go.Bar(
            name="Delayed",
            x=df_ship["shipping_type"],
            y=df_ship["delayed_orders"],
            marker_color=COLOR_DELAYED,
        ))
        layout = make_plotly_layout("Orders by Shipping Type")
        layout["barmode"] = "group"
        fig.update_layout(**layout)
        st.plotly_chart(fig, use_container_width=True)

        if not df_ship.empty:
            worst_ship = df_ship.iloc[0]
            st.info(
                f"💡 **{worst_ship['shipping_type']}** has the highest delay rate at "
                f"**{worst_ship['delay_rate_pct']:.1f}%**."
            )

with col_dist:
    if df_dist.empty:
        empty_state("No distance data.")
    else:
        fig = px.line(
            df_dist,
            x="distance_bucket",
            y="delay_rate_pct",
            title="Delay Rate by Distance Bucket (%)",
            labels={"delay_rate_pct": "Delay Rate %", "distance_bucket": "Distance"},
            markers=True,
            color_discrete_sequence=[COLOR_IN_TRANSIT],
        )
        fig.update_layout(**make_plotly_layout())
        st.plotly_chart(fig, use_container_width=True)

        # Add avg delay days as supplement
        fig2 = px.bar(
            df_dist,
            x="distance_bucket",
            y="avg_delay_days",
            title="Avg Delay Days by Distance Bucket",
            labels={"avg_delay_days": "Avg Delay Days", "distance_bucket": "Distance"},
            color_discrete_sequence=[COLOR_DELAYED],
        )
        fig2.update_layout(**make_plotly_layout(height=250))
        st.plotly_chart(fig2, use_container_width=True)

st.markdown("---")

# ---------------------------------------------------------------------------
# Row 3: Category Delays (donut)
# ---------------------------------------------------------------------------
section_header("🛍️ Delay Distribution by Product Category")

col_cat, col_cat_bar = st.columns(2)

with col_cat:
    if df_cat.empty:
        empty_state("No category data.")
    else:
        fig = px.pie(
            df_cat,
            names="product_category",
            values="delayed_orders",
            title="Share of Delayed Orders by Category",
            hole=0.5,
            color_discrete_sequence=BRAND_COLORS,
        )
        fig.update_layout(
            paper_bgcolor="#0E1117",
            plot_bgcolor="#0E1117",
            font=dict(color="#9AA3B0"),
            height=380,
            margin=dict(l=20, r=20, t=50, b=20),
        )
        st.plotly_chart(fig, use_container_width=True)

with col_cat_bar:
    if df_cat.empty:
        empty_state("No category data.")
    else:
        fig = px.bar(
            df_cat.sort_values("delay_rate_pct", ascending=True),
            x="delay_rate_pct",
            y="product_category",
            orientation="h",
            title="Delay Rate by Product Category (%)",
            labels={"delay_rate_pct": "Delay Rate %", "product_category": "Category"},
            color="delay_rate_pct",
            color_continuous_scale=["#00CC88", "#FFD700", "#FF4B4B"],
            text="delay_rate_pct",
        )
        fig.update_traces(texttemplate="%{text:.1f}%", textposition="outside")
        fig.update_layout(**make_plotly_layout(height=380))
        fig.update_layout(coloraxis_showscale=False)
        st.plotly_chart(fig, use_container_width=True)

        worst_cat = df_cat.iloc[0]
        st.warning(
            f"⚠️ **{worst_cat['product_category']}** has the highest delay rate "
            f"at **{worst_cat['delay_rate_pct']:.1f}%** "
            f"({int(worst_cat['delayed_orders'])} delayed orders)."
        )

st.caption("Auto-refresh every 5 minutes.")
