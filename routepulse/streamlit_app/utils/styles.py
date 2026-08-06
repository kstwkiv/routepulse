"""
RoutePulse — Shared Streamlit Styles & UI Helpers
"""

import streamlit as st

# ---------------------------------------------------------------------------
# Brand colours
# ---------------------------------------------------------------------------
COLOR_DELAYED    = "#FF4B4B"
COLOR_ON_TIME    = "#00CC88"
COLOR_IN_TRANSIT = "#FFD700"
COLOR_PENDING    = "#AAAAAA"
COLOR_PRIMARY    = "#1E88E5"
COLOR_BACKGROUND = "#0E1117"
COLOR_CARD       = "#1A1D23"
COLOR_BORDER     = "#2E3440"

# Plotly colour sequence consistent with brand
BRAND_COLORS = [
    COLOR_PRIMARY, COLOR_ON_TIME, COLOR_IN_TRANSIT,
    COLOR_DELAYED, "#AB47BC", "#FF7043", "#26C6DA",
]

STATUS_EMOJI = {
    "Delayed":    "🔴",
    "Delivered":  "🟢",
    "In Transit": "🟡",
    "Pending":    "⚪",
}

STATUS_COLOR = {
    "Delayed":    COLOR_DELAYED,
    "Delivered":  COLOR_ON_TIME,
    "In Transit": COLOR_IN_TRANSIT,
    "Pending":    COLOR_PENDING,
}


def inject_global_css():
    """Inject custom CSS for a polished dark-mode look."""
    st.markdown("""
        <style>
        /* Hide Streamlit default header chrome */
        #MainMenu { visibility: hidden; }
        footer     { visibility: hidden; }

        /* Card-like metric blocks */
        div[data-testid="metric-container"] {
            background-color: #1A1D23;
            border: 1px solid #2E3440;
            border-radius: 8px;
            padding: 16px 20px;
        }
        div[data-testid="metric-container"] label {
            color: #9AA3B0 !important;
            font-size: 0.82rem !important;
            text-transform: uppercase;
            letter-spacing: 0.05em;
        }
        div[data-testid="metric-container"] div[data-testid="stMetricValue"] {
            font-size: 2rem !important;
            font-weight: 700 !important;
        }

        /* Subtle divider */
        hr { border-color: #2E3440; }

        /* Table styling */
        .stDataFrame thead th {
            background-color: #1E2229 !important;
            color: #9AA3B0 !important;
            font-weight: 600;
            text-transform: uppercase;
            font-size: 0.78rem;
            letter-spacing: 0.04em;
        }

        /* Sidebar header */
        section[data-testid="stSidebar"] .block-container {
            padding-top: 1.5rem;
        }

        /* Page section headers */
        .section-header {
            font-size: 1.05rem;
            font-weight: 600;
            color: #E0E4ED;
            margin: 1.5rem 0 0.5rem;
            border-left: 3px solid #1E88E5;
            padding-left: 10px;
        }

        /* Status pill badges */
        .status-delayed    { color: #FF4B4B; font-weight: 600; }
        .status-delivered  { color: #00CC88; font-weight: 600; }
        .status-in-transit { color: #FFD700; font-weight: 600; }
        .status-pending    { color: #AAAAAA; font-weight: 600; }

        /* Summary stat card */
        .stat-card {
            background: #1A1D23;
            border: 1px solid #2E3440;
            border-radius: 8px;
            padding: 12px 18px;
            margin-bottom: 8px;
        }
        </style>
    """, unsafe_allow_html=True)


def page_header(title: str, subtitle: str = ""):
    """Render a branded page header."""
    st.markdown(f"""
        <div style="margin-bottom: 1.5rem;">
            <h2 style="margin: 0; color: #E0E4ED; font-weight: 700;">{title}</h2>
            {"<p style='color:#9AA3B0; margin:4px 0 0; font-size:0.9rem;'>" + subtitle + "</p>" if subtitle else ""}
        </div>
    """, unsafe_allow_html=True)


def section_header(text: str):
    st.markdown(f'<div class="section-header">{text}</div>', unsafe_allow_html=True)


def empty_state(message: str = "No data available yet. The pipeline may still be initialising."):
    """Friendly empty state component."""
    st.info(f"📭 {message}")


def status_badge(status: str) -> str:
    """Return an HTML badge for a delivery status."""
    emoji = STATUS_EMOJI.get(status, "❓")
    color = STATUS_COLOR.get(status, "#AAAAAA")
    return f'<span style="color:{color}; font-weight:600;">{emoji} {status}</span>'


def make_plotly_layout(title: str = "", height: int = 380) -> dict:
    """Return a dark-themed Plotly layout dict."""
    return dict(
        title=dict(text=title, font=dict(size=14, color="#E0E4ED")),
        height=height,
        paper_bgcolor="#0E1117",
        plot_bgcolor="#0E1117",
        font=dict(color="#9AA3B0", family="Inter, sans-serif"),
        xaxis=dict(gridcolor="#2E3440", linecolor="#2E3440", zerolinecolor="#2E3440"),
        yaxis=dict(gridcolor="#2E3440", linecolor="#2E3440", zerolinecolor="#2E3440"),
        legend=dict(bgcolor="rgba(0,0,0,0)", bordercolor="#2E3440"),
        margin=dict(l=40, r=20, t=50, b=40),
    )
