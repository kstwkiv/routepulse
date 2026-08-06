"""
RoutePulse — Main Streamlit Entry Point
Sets page config, injects global styles, and renders the home/landing view.
Auto-refreshes every 5 minutes.
"""

import time
import streamlit as st
import sys
import os

# Make project modules importable from the app container
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from streamlit_app.utils.styles import inject_global_css, COLOR_PRIMARY, COLOR_ON_TIME, COLOR_DELAYED

st.set_page_config(
    page_title="RoutePulse",
    page_icon="🚚",
    layout="wide",
    initial_sidebar_state="expanded",
)

inject_global_css()

# ---------------------------------------------------------------------------
# Sidebar branding
# ---------------------------------------------------------------------------
with st.sidebar:
    st.markdown("""
        <div style="text-align:center; padding: 1rem 0 1.5rem;">
            <span style="font-size: 2.4rem;">🚚</span>
            <h2 style="margin: 0.3rem 0 0; color: #E0E4ED; font-size: 1.4rem; font-weight: 700;">
                RoutePulse
            </h2>
            <p style="color: #9AA3B0; font-size: 0.8rem; margin: 0;">
                Live Delivery Intelligence
            </p>
        </div>
        <hr style="border-color: #2E3440; margin-bottom: 1rem;" />
    """, unsafe_allow_html=True)

    st.markdown("""
        **Navigation**
        Use the pages above to explore:
        - 📊 **Overview** — KPIs & trends
        - 🚛 **Delivery Operations** — Order-level details
        - ⚠️ **Delay Analysis** — Root-cause insights
        - 🔧 **Pipeline Health** — ETL monitoring
    """)

    st.markdown("---")
    st.caption("Refreshes every 5 minutes automatically.")

# ---------------------------------------------------------------------------
# Home page content
# ---------------------------------------------------------------------------
st.markdown("""
    <div style="text-align: center; padding: 3rem 1rem 2rem;">
        <span style="font-size: 4rem;">🚚</span>
        <h1 style="color: #E0E4ED; font-size: 2.8rem; font-weight: 800; margin: 0.5rem 0 0.2rem;">
            RoutePulse
        </h1>
        <p style="color: #9AA3B0; font-size: 1.15rem; margin: 0 auto; max-width: 600px;">
            Live Delivery Intelligence Platform — powered by real-time synthetic
            data pipelines across India's top logistics hubs.
        </p>
    </div>
""", unsafe_allow_html=True)

col1, col2, col3, col4 = st.columns(4)

with col1:
    st.markdown(f"""
        <div style="background:#1A1D23; border:1px solid #2E3440; border-radius:10px;
                    padding:20px; text-align:center;">
            <div style="font-size:2rem;">📊</div>
            <div style="color:#E0E4ED; font-weight:700; margin-top:8px;">Overview</div>
            <div style="color:#9AA3B0; font-size:0.85rem; margin-top:4px;">
                KPIs, trends & city performance
            </div>
        </div>
    """, unsafe_allow_html=True)

with col2:
    st.markdown(f"""
        <div style="background:#1A1D23; border:1px solid #2E3440; border-radius:10px;
                    padding:20px; text-align:center;">
            <div style="font-size:2rem;">🚛</div>
            <div style="color:#E0E4ED; font-weight:700; margin-top:8px;">Operations</div>
            <div style="color:#9AA3B0; font-size:0.85rem; margin-top:4px;">
                Filter & explore individual orders
            </div>
        </div>
    """, unsafe_allow_html=True)

with col3:
    st.markdown(f"""
        <div style="background:#1A1D23; border:1px solid #2E3440; border-radius:10px;
                    padding:20px; text-align:center;">
            <div style="font-size:2rem;">⚠️</div>
            <div style="color:#E0E4ED; font-weight:700; margin-top:8px;">Delay Analysis</div>
            <div style="color:#9AA3B0; font-size:0.85rem; margin-top:4px;">
                Identify bottlenecks & risk factors
            </div>
        </div>
    """, unsafe_allow_html=True)

with col4:
    st.markdown(f"""
        <div style="background:#1A1D23; border:1px solid #2E3440; border-radius:10px;
                    padding:20px; text-align:center;">
            <div style="font-size:2rem;">🔧</div>
            <div style="color:#E0E4ED; font-weight:700; margin-top:8px;">Pipeline Health</div>
            <div style="color:#9AA3B0; font-size:0.85rem; margin-top:4px;">
                Monitor ETL status & data quality
            </div>
        </div>
    """, unsafe_allow_html=True)

st.markdown("<br>", unsafe_allow_html=True)
st.markdown("""
    <div style="text-align:center; color:#9AA3B0; font-size:0.85rem; padding: 1rem;">
        Data refreshes every 5 minutes via Airflow · PostgreSQL → DuckDB · 8 cities · 11 warehouses
    </div>
""", unsafe_allow_html=True)

# ---------------------------------------------------------------------------
# Auto-refresh every 5 minutes
# ---------------------------------------------------------------------------
REFRESH_INTERVAL_SEC = 300

if "last_refresh" not in st.session_state:
    st.session_state["last_refresh"] = time.time()

elapsed = time.time() - st.session_state["last_refresh"]
remaining = max(0, int(REFRESH_INTERVAL_SEC - elapsed))

if remaining == 0:
    st.session_state["last_refresh"] = time.time()
    st.rerun()

st.markdown(
    f'<div style="text-align:center; color:#555; font-size:0.75rem; margin-top:2rem;">'
    f'Next auto-refresh in {remaining // 60}m {remaining % 60}s</div>',
    unsafe_allow_html=True,
)
