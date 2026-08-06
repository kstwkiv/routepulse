"""
RoutePulse — Delivery Operations Page
Filterable, paginated order table with summary stats.
"""

import sys
import os
import math
import time
import streamlit as st
import pandas as pd

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from streamlit_app.utils.styles import (
    inject_global_css, page_header, section_header, empty_state,
    STATUS_EMOJI, COLOR_DELAYED, COLOR_ON_TIME, COLOR_IN_TRANSIT, COLOR_PENDING,
)
from streamlit_app.utils.db import duckdb_exists

st.set_page_config(page_title="Delivery Operations — RoutePulse", page_icon="🚛", layout="wide")
inject_global_css()

page_header("🚛 Delivery Operations", "Explore and filter individual delivery orders")

if not duckdb_exists():
    empty_state("DuckDB database not found. The ETL pipeline may not have run yet.")
    st.stop()

from analytics.queries import get_filtered_orders, get_filter_options

PAGE_SIZE = 50

# ---------------------------------------------------------------------------
# Sidebar filters
# ---------------------------------------------------------------------------
@st.cache_data(ttl=300)
def fetch_filter_options():
    return get_filter_options()

options = fetch_filter_options()

with st.sidebar:
    st.markdown("### 🔍 Filters")

    selected_cities = st.multiselect(
        "City",
        options=options.get("cities", []),
        default=[],
        placeholder="All cities",
    )

    selected_warehouses = st.multiselect(
        "Warehouse",
        options=options.get("warehouses", []),
        default=[],
        placeholder="All warehouses",
    )

    selected_shipping = st.multiselect(
        "Shipping Type",
        options=options.get("shipping_types", []),
        default=[],
        placeholder="All types",
    )

    selected_statuses = st.multiselect(
        "Status",
        options=options.get("statuses", []),
        default=[],
        placeholder="All statuses",
    )

    col_d1, col_d2 = st.columns(2)
    with col_d1:
        date_from = st.date_input("From Date", value=None, key="date_from")
    with col_d2:
        date_to   = st.date_input("To Date",   value=None, key="date_to")

    st.markdown("---")
    if st.button("🔄 Clear Filters"):
        st.rerun()

# ---------------------------------------------------------------------------
# Fetch filtered data
# ---------------------------------------------------------------------------
@st.cache_data(ttl=300)
def fetch_orders(cities, warehouses, shipping_types, statuses, date_from, date_to):
    return get_filtered_orders(
        cities        = cities        or None,
        warehouses    = warehouses    or None,
        shipping_types= shipping_types or None,
        statuses      = statuses      or None,
        date_from     = date_from,
        date_to       = date_to,
    )

df = fetch_orders(
    tuple(selected_cities),
    tuple(selected_warehouses),
    tuple(selected_shipping),
    tuple(selected_statuses),
    date_from,
    date_to,
)

# ---------------------------------------------------------------------------
# Summary stats
# ---------------------------------------------------------------------------
if df.empty:
    empty_state("No orders match the current filters.")
    st.stop()

total        = len(df)
delivered    = (df["status"] == "Delivered").sum()
delayed      = (df["status"] == "Delayed").sum()
in_transit   = (df["status"] == "In Transit").sum()
pending      = (df["status"] == "Pending").sum()
delay_pct    = round(delayed / total * 100, 1) if total > 0 else 0

section_header("📋 Summary")
s1, s2, s3, s4, s5 = st.columns(5)
s1.metric("Total Orders",    f"{total:,}")
s2.metric("Delivered",       f"{delivered:,}")
s3.metric("Delayed",         f"{delayed:,}", delta=f"{delay_pct}%", delta_color="inverse")
s4.metric("In Transit",      f"{in_transit:,}")
s5.metric("Pending",         f"{pending:,}")

st.markdown("---")

# ---------------------------------------------------------------------------
# Format display DataFrame
# ---------------------------------------------------------------------------
def format_status(status):
    emoji = STATUS_EMOJI.get(status, "❓")
    return f"{emoji} {status}"

display_df = df[[
    "order_id", "city", "warehouse_id", "shipping_type", "product_category",
    "distance_km", "promised_days", "actual_days", "status", "created_at",
]].copy()

display_df["status"] = display_df["status"].apply(format_status)
display_df["distance_km"] = display_df["distance_km"].round(1)
display_df.rename(columns={
    "order_id":         "Order ID",
    "city":             "City",
    "warehouse_id":     "Warehouse",
    "shipping_type":    "Shipping",
    "product_category": "Category",
    "distance_km":      "Distance (km)",
    "promised_days":    "Promised",
    "actual_days":      "Actual",
    "status":           "Status",
    "created_at":       "Created At",
}, inplace=True)

# ---------------------------------------------------------------------------
# Pagination
# ---------------------------------------------------------------------------
total_pages = max(1, math.ceil(total / PAGE_SIZE))

section_header(f"📦 Orders ({total:,} matching)")

col_pg_left, col_pg_right = st.columns([3, 1])
with col_pg_right:
    page = st.number_input(
        "Page", min_value=1, max_value=total_pages, value=1, step=1,
        label_visibility="collapsed",
    )

st.caption(f"Showing page {page} of {total_pages} ({PAGE_SIZE} per page)")

start_idx = (page - 1) * PAGE_SIZE
end_idx   = start_idx + PAGE_SIZE
page_df   = display_df.iloc[start_idx:end_idx]

st.dataframe(
    page_df,
    use_container_width=True,
    hide_index=True,
    height=600,
)

# ---------------------------------------------------------------------------
# Download
# ---------------------------------------------------------------------------
csv_data = df.to_csv(index=False).encode("utf-8")
st.download_button(
    label="📥 Download Filtered Orders (CSV)",
    data=csv_data,
    file_name="routepulse_orders.csv",
    mime="text/csv",
)

st.caption(f"Auto-refresh every 5 minutes.")
