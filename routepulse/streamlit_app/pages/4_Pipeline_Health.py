"""
RoutePulse — Pipeline Health Page
Real-time monitoring of ETL pipeline status, connectivity, and run history.
"""

import sys
import os
import time
from datetime import datetime, timezone, timedelta
import streamlit as st
import plotly.express as px
import plotly.graph_objects as go

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from streamlit_app.utils.styles import (
    inject_global_css, page_header, section_header, empty_state,
    COLOR_DELAYED, COLOR_ON_TIME, COLOR_IN_TRANSIT, COLOR_PRIMARY,
    make_plotly_layout,
)
from streamlit_app.utils.db import check_duckdb, check_postgres, duckdb_exists

st.set_page_config(page_title="Pipeline Health — RoutePulse", page_icon="🔧", layout="wide")
inject_global_css()

page_header("🔧 Pipeline Health", "Monitor ETL status, component connectivity, and run history")

# ---------------------------------------------------------------------------
# Connectivity checks
# ---------------------------------------------------------------------------
section_header("🔌 Component Status")

duck_ok,  duck_msg  = check_duckdb()
pg_ok,    pg_msg    = check_postgres()

def status_indicator(ok: bool, label: str, detail: str = "") -> str:
    icon  = "🟢" if ok else "🔴"
    color = "#00CC88" if ok else "#FF4B4B"
    text  = "Connected" if ok else f"Error: {detail}"
    return f"""
        <div style="display:flex; align-items:center; gap:12px;
                    background:#1A1D23; border:1px solid #2E3440;
                    border-radius:8px; padding:12px 16px; margin-bottom:8px;">
            <span style="font-size:1.3rem;">{icon}</span>
            <div>
                <div style="color:#E0E4ED; font-weight:600;">{label}</div>
                <div style="color:{color}; font-size:0.85rem;">{text}</div>
            </div>
        </div>
    """

col_comp1, col_comp2, col_comp3 = st.columns(3)

with col_comp1:
    st.markdown(status_indicator(pg_ok,   "PostgreSQL",    pg_msg),   unsafe_allow_html=True)

with col_comp2:
    st.markdown(status_indicator(duck_ok, "DuckDB",        duck_msg), unsafe_allow_html=True)

with col_comp3:
    # Airflow is considered running if we can at least load our modules (soft check)
    try:
        import importlib
        airflow_ok = importlib.util.find_spec("airflow") is not None
    except Exception:
        airflow_ok = False
    st.markdown(status_indicator(airflow_ok, "Airflow", "Module available" if airflow_ok else "Not found"), unsafe_allow_html=True)

st.markdown("---")

# ---------------------------------------------------------------------------
# Stop here if DuckDB not ready
# ---------------------------------------------------------------------------
if not duckdb_exists():
    empty_state("DuckDB database not found. The ETL pipeline has not run yet.")
    st.stop()

from analytics.queries import (
    get_pipeline_health_summary,
    get_total_records_in_duckdb,
    get_recent_pipeline_runs,
    get_processing_time_trend,
)

# ---------------------------------------------------------------------------
# Cached queries
# ---------------------------------------------------------------------------
@st.cache_data(ttl=60)
def fetch_health_summary():   return get_pipeline_health_summary()
@st.cache_data(ttl=60)
def fetch_total_records():    return get_total_records_in_duckdb()
@st.cache_data(ttl=60)
def fetch_recent_runs():      return get_recent_pipeline_runs(10)
@st.cache_data(ttl=60)
def fetch_time_trend():       return get_processing_time_trend(50)

summary     = fetch_health_summary()
total_recs  = fetch_total_records()
df_runs     = fetch_recent_runs()
df_trend    = fetch_time_trend()

# ---------------------------------------------------------------------------
# Pipeline summary cards
# ---------------------------------------------------------------------------
section_header("📊 Latest Pipeline Run")

last_run_status  = summary.get("status", "unknown")
finished_at      = summary.get("finished_at")
recs_processed   = summary.get("records_processed", 0)
recs_failed      = summary.get("records_failed", 0)
proc_time        = summary.get("processing_time_sec", 0)

# Warning if last run was > 15 minutes ago
stale_warning = False
if finished_at is not None:
    try:
        if hasattr(finished_at, "tzinfo") and finished_at.tzinfo is None:
            finished_at_aware = finished_at.replace(tzinfo=timezone.utc)
        else:
            finished_at_aware = finished_at
        minutes_ago = (datetime.now(timezone.utc) - finished_at_aware).total_seconds() / 60
        if minutes_ago > 15:
            stale_warning = True
            st.warning(
                f"⚠️ Last pipeline run was **{minutes_ago:.0f} minutes ago**. "
                "The pipeline may be stalled. Check Airflow scheduler."
            )
    except Exception:
        pass

# Status colour
status_color = {
    "success": COLOR_ON_TIME,
    "failed":  COLOR_DELAYED,
    "running": COLOR_IN_TRANSIT,
}.get(last_run_status, "#AAAAAA")

status_icon = {
    "success": "🟢", "failed": "🔴", "running": "🟡",
}.get(last_run_status, "⚪")

st.markdown(f"""
    <div style="background:#1A1D23; border:1px solid #2E3440; border-radius:10px;
                padding: 20px 24px; margin-bottom:1rem;">
        <div style="display:grid; grid-template-columns: repeat(5, 1fr); gap: 16px;">
            <div>
                <div style="color:#9AA3B0; font-size:0.78rem; text-transform:uppercase;
                            letter-spacing:0.05em;">Pipeline Status</div>
                <div style="color:{status_color}; font-size:1.6rem; font-weight:700; margin-top:4px;">
                    {status_icon} {last_run_status.title()}
                </div>
            </div>
            <div>
                <div style="color:#9AA3B0; font-size:0.78rem; text-transform:uppercase;
                            letter-spacing:0.05em;">Last Successful Run</div>
                <div style="color:#E0E4ED; font-size:1.1rem; font-weight:600; margin-top:4px;">
                    {finished_at.strftime('%H:%M %p') if finished_at else '—'}
                </div>
            </div>
            <div>
                <div style="color:#9AA3B0; font-size:0.78rem; text-transform:uppercase;
                            letter-spacing:0.05em;">Records Processed</div>
                <div style="color:#E0E4ED; font-size:1.6rem; font-weight:700; margin-top:4px;">
                    {int(recs_processed):,}
                </div>
            </div>
            <div>
                <div style="color:#9AA3B0; font-size:0.78rem; text-transform:uppercase;
                            letter-spacing:0.05em;">Records Failed</div>
                <div style="color:{'#FF4B4B' if recs_failed > 0 else '#E0E4ED'};
                            font-size:1.6rem; font-weight:700; margin-top:4px;">
                    {int(recs_failed):,}
                </div>
            </div>
            <div>
                <div style="color:#9AA3B0; font-size:0.78rem; text-transform:uppercase;
                            letter-spacing:0.05em;">Processing Time</div>
                <div style="color:#E0E4ED; font-size:1.6rem; font-weight:700; margin-top:4px;">
                    {float(proc_time):.1f}s
                </div>
            </div>
        </div>
    </div>
    <div style="background:#1A1D23; border:1px solid #2E3440; border-radius:8px;
                padding:14px 20px; display:inline-block; margin-bottom:1rem;">
        <span style="color:#9AA3B0; font-size:0.85rem;">Total records in DuckDB: </span>
        <span style="color:#1E88E5; font-weight:700; font-size:1rem;">{total_recs:,}</span>
    </div>
""", unsafe_allow_html=True)

st.markdown("---")

# ---------------------------------------------------------------------------
# Recent runs table
# ---------------------------------------------------------------------------
section_header("📋 Last 10 Pipeline Runs")

if df_runs.empty:
    empty_state("No pipeline run history found.")
else:
    def fmt_status(s):
        icons = {"success": "🟢 Success", "failed": "🔴 Failed", "running": "🟡 Running"}
        return icons.get(s, f"⚪ {s}")

    df_display = df_runs.copy()
    df_display["status"]     = df_display["status"].apply(fmt_status)
    df_display["run_id"]     = df_display["run_id"].str[:8] + "…"
    df_display.rename(columns={
        "run_id":              "Run ID",
        "dag_id":              "DAG",
        "run_type":            "Type",
        "started_at":          "Started",
        "finished_at":         "Finished",
        "status":              "Status",
        "records_processed":   "Processed",
        "records_failed":      "Failed",
        "processing_time_sec": "Time (s)",
    }, inplace=True)
    st.dataframe(df_display, use_container_width=True, hide_index=True)

st.markdown("---")

# ---------------------------------------------------------------------------
# Charts: Processing time trend & records over time
# ---------------------------------------------------------------------------
section_header("📈 Performance Trends")

if df_trend.empty:
    empty_state("No trend data available yet.")
else:
    c1, c2 = st.columns(2)

    with c1:
        fig_time = px.line(
            df_trend,
            x="finished_at",
            y="processing_time_sec",
            title="Processing Time per ETL Run (seconds)",
            labels={"processing_time_sec": "Seconds", "finished_at": "Time"},
            markers=True,
            color_discrete_sequence=[COLOR_PRIMARY],
        )
        fig_time.update_layout(**make_plotly_layout())
        st.plotly_chart(fig_time, use_container_width=True)

    with c2:
        fig_recs = px.bar(
            df_trend,
            x="finished_at",
            y="records_processed",
            title="Records Processed per ETL Run",
            labels={"records_processed": "Records", "finished_at": "Time"},
            color_discrete_sequence=[COLOR_ON_TIME],
        )
        fig_recs.update_layout(**make_plotly_layout())
        st.plotly_chart(fig_recs, use_container_width=True)

# ---------------------------------------------------------------------------
# Auto-refresh every 60 seconds on health page
# ---------------------------------------------------------------------------
REFRESH_INTERVAL_SEC = 60

if "last_refresh_health" not in st.session_state:
    st.session_state["last_refresh_health"] = time.time()

elapsed   = time.time() - st.session_state["last_refresh_health"]
remaining = max(0, int(REFRESH_INTERVAL_SEC - elapsed))

if remaining == 0:
    st.session_state["last_refresh_health"] = time.time()
    st.rerun()

st.caption(f"Page refreshes every {REFRESH_INTERVAL_SEC}s — next refresh in {remaining}s")
