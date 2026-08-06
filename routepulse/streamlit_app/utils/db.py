"""
RoutePulse — Database Connection Helpers for Streamlit
Provides connectivity checks and a convenience wrapper around DuckDB
that plays well with Streamlit's caching.
"""

import os
import logging

import duckdb
import pandas as pd
from dotenv import load_dotenv

try:
    import psycopg2
    _PSYCOPG2_AVAILABLE = True
except ImportError:
    _PSYCOPG2_AVAILABLE = False

load_dotenv()

log = logging.getLogger(__name__)

DUCKDB_PATH   = os.getenv("DUCKDB_PATH", "/data/routepulse.duckdb")
POSTGRES_HOST = os.getenv("POSTGRES_HOST", "postgres")
POSTGRES_PORT = int(os.getenv("POSTGRES_PORT", 5432))
POSTGRES_DB   = os.getenv("POSTGRES_DB", "routepulse")
POSTGRES_USER = os.getenv("POSTGRES_USER", "routepulse")
POSTGRES_PASS = os.getenv("POSTGRES_PASSWORD", "routepulse123")


def duckdb_exists() -> bool:
    """Return True if the DuckDB file is present on disk."""
    return os.path.exists(DUCKDB_PATH)


def check_duckdb() -> tuple:
    """
    Check DuckDB connectivity.
    Returns (is_connected: bool, message: str).
    """
    if not duckdb_exists():
        return False, f"File not found: {DUCKDB_PATH}"
    try:
        conn = duckdb.connect(DUCKDB_PATH, read_only=True)
        conn.execute("SELECT 1;")
        conn.close()
        return True, "Connected"
    except Exception as exc:
        return False, str(exc)


def check_postgres() -> tuple:
    """
    Check PostgreSQL connectivity.
    Returns (is_connected: bool, message: str).
    """
    if not _PSYCOPG2_AVAILABLE:
        return False, "psycopg2 not installed"
    try:
        conn = psycopg2.connect(
            host=POSTGRES_HOST, port=POSTGRES_PORT,
            dbname=POSTGRES_DB, user=POSTGRES_USER, password=POSTGRES_PASS,
            connect_timeout=3,
        )
        conn.close()
        return True, "Connected"
    except Exception as exc:
        return False, str(exc)


def run_duckdb_query(sql: str, params=None) -> pd.DataFrame:
    """
    Execute a SQL query against DuckDB and return a DataFrame.
    Raises FileNotFoundError if DuckDB doesn't exist yet.
    """
    if not duckdb_exists():
        raise FileNotFoundError(
            f"DuckDB database not found at {DUCKDB_PATH}. "
            "The ETL pipeline has not run yet."
        )
    conn = duckdb.connect(DUCKDB_PATH, read_only=True)
    try:
        if params:
            return conn.execute(sql, params).df()
        return conn.execute(sql).df()
    finally:
        conn.close()


def get_duckdb_table_counts() -> dict:
    """Return row counts for each analytical table."""
    tables = ["orders", "warehouse_metrics", "city_metrics", "pipeline_runs"]
    counts = {}
    for table in tables:
        try:
            df = run_duckdb_query(f"SELECT COUNT(*) AS cnt FROM {table};")
            counts[table] = int(df.iloc[0]["cnt"]) if not df.empty else 0
        except Exception:
            counts[table] = 0
    return counts
