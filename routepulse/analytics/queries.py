"""
RoutePulse — DuckDB Analytical Queries
All queries used by Streamlit pages, with caching via st.cache_data.
Each function returns a pandas DataFrame or scalar.
"""

import os
import logging

import duckdb
import pandas as pd
from dotenv import load_dotenv

load_dotenv()

log = logging.getLogger(__name__)

DUCKDB_PATH = os.getenv("DUCKDB_PATH", "/data/routepulse.duckdb")


def _conn() -> duckdb.DuckDBPyConnection:
    """Open a read-only DuckDB connection."""
    if not os.path.exists(DUCKDB_PATH):
        raise FileNotFoundError(
            f"DuckDB database not found at {DUCKDB_PATH}. "
            "Has the ETL pipeline run at least once?"
        )
    return duckdb.connect(DUCKDB_PATH, read_only=True)


def _safe_query(sql: str, params=None) -> pd.DataFrame:
    """Execute a query and return a DataFrame, or empty DataFrame on error."""
    conn = None
    try:
        conn = _conn()
        if params:
            return conn.execute(sql, params).df()
        return conn.execute(sql).df()
    except Exception as exc:
        log.warning("Query failed: %s — %s", exc, sql[:120])
        return pd.DataFrame()
    finally:
        if conn:
            conn.close()


# ---------------------------------------------------------------------------
# Overview page queries
# ---------------------------------------------------------------------------

def get_summary_metrics() -> dict:
    """Return top-level KPI scalars."""
    sql = """
        SELECT
            COUNT(*)                                                    AS total_orders,
            SUM(CASE WHEN status = 'Delivered' THEN 1 ELSE 0 END)      AS delivered_orders,
            SUM(CASE WHEN status = 'Delayed'   THEN 1 ELSE 0 END)      AS delayed_orders,
            SUM(CASE WHEN status = 'In Transit' THEN 1 ELSE 0 END)     AS in_transit_orders,
            SUM(CASE WHEN status = 'Pending'    THEN 1 ELSE 0 END)     AS pending_orders,
            ROUND(
                100.0 * SUM(CASE WHEN status = 'Delayed' THEN 1 ELSE 0 END)
                / NULLIF(COUNT(*), 0), 1
            )                                                           AS delay_pct,
            ROUND(AVG(CASE WHEN actual_days IS NOT NULL
                           THEN actual_days END), 1)                    AS avg_delivery_days
        FROM orders;
    """
    df = _safe_query(sql)
    if df.empty:
        return {
            "total_orders": 0, "delivered_orders": 0, "delayed_orders": 0,
            "in_transit_orders": 0, "pending_orders": 0,
            "delay_pct": 0.0, "avg_delivery_days": 0.0,
        }
    return df.iloc[0].to_dict()


def get_orders_at_risk() -> int:
    """Orders 'In Transit' whose promised delivery date is within 1 day or overdue."""
    sql = """
        SELECT COUNT(*) AS at_risk
        FROM orders
        WHERE status = 'In Transit'
          AND (
              DATE_DIFF('day', CAST(created_at AS DATE), CURRENT_DATE)
              >= promised_days - 1
          );
    """
    df = _safe_query(sql)
    if df.empty:
        return 0
    return int(df.iloc[0]["at_risk"])


def get_orders_over_time(days: int = 7) -> pd.DataFrame:
    """Daily order and delay counts for the last `days` days."""
    sql = """
        SELECT
            CAST(created_at AS DATE)                                   AS order_date,
            COUNT(*)                                                   AS total_orders,
            SUM(CASE WHEN status = 'Delayed'   THEN 1 ELSE 0 END)     AS delayed_orders,
            SUM(CASE WHEN status = 'Delivered' THEN 1 ELSE 0 END)     AS delivered_orders
        FROM orders
        WHERE created_at >= CURRENT_DATE - INTERVAL (?) DAY
        GROUP BY 1
        ORDER BY 1;
    """
    return _safe_query(sql, [days])


def get_city_performance() -> pd.DataFrame:
    """On-time % per city."""
    sql = """
        SELECT
            city,
            COUNT(*)                                                            AS total_orders,
            SUM(CASE WHEN status = 'Delivered' THEN 1 ELSE 0 END)              AS on_time_orders,
            SUM(CASE WHEN status = 'Delayed'   THEN 1 ELSE 0 END)              AS delayed_orders,
            ROUND(
                100.0 * SUM(CASE WHEN status = 'Delivered' THEN 1 ELSE 0 END)
                / NULLIF(COUNT(*), 0), 1
            )                                                                   AS on_time_pct
        FROM orders
        GROUP BY city
        ORDER BY on_time_pct DESC;
    """
    return _safe_query(sql)


# ---------------------------------------------------------------------------
# Delivery Operations page queries
# ---------------------------------------------------------------------------

def get_filtered_orders(
    cities=None,
    warehouses=None,
    shipping_types=None,
    statuses=None,
    date_from=None,
    date_to=None,
    limit: int = 5000,
) -> pd.DataFrame:
    """Filtered order list for the operations table."""
    conditions = ["1=1"]
    params = []

    if cities:
        placeholders = ", ".join(["?" for _ in cities])
        conditions.append(f"city IN ({placeholders})")
        params.extend(cities)

    if warehouses:
        placeholders = ", ".join(["?" for _ in warehouses])
        conditions.append(f"warehouse_id IN ({placeholders})")
        params.extend(warehouses)

    if shipping_types:
        placeholders = ", ".join(["?" for _ in shipping_types])
        conditions.append(f"shipping_type IN ({placeholders})")
        params.extend(shipping_types)

    if statuses:
        placeholders = ", ".join(["?" for _ in statuses])
        conditions.append(f"status IN ({placeholders})")
        params.extend(statuses)

    if date_from:
        conditions.append("CAST(created_at AS DATE) >= ?")
        params.append(str(date_from))

    if date_to:
        conditions.append("CAST(created_at AS DATE) <= ?")
        params.append(str(date_to))

    where = " AND ".join(conditions)
    sql = f"""
        SELECT
            order_id, city, warehouse_id, shipping_type, product_category,
            distance_km, promised_days, actual_days, status,
            delay_days, delay_flag, delivery_speed, created_at
        FROM orders
        WHERE {where}
        ORDER BY created_at DESC
        LIMIT {limit};
    """
    return _safe_query(sql, params if params else None)


def get_filter_options() -> dict:
    """Return distinct values for filter dropdowns."""
    queries = {
        "cities":         "SELECT DISTINCT city        FROM orders ORDER BY city;",
        "warehouses":     "SELECT DISTINCT warehouse_id FROM orders ORDER BY warehouse_id;",
        "shipping_types": "SELECT DISTINCT shipping_type FROM orders ORDER BY shipping_type;",
        "statuses":       "SELECT DISTINCT status       FROM orders ORDER BY status;",
    }
    options = {}
    for key, sql in queries.items():
        df = _safe_query(sql)
        options[key] = df.iloc[:, 0].tolist() if not df.empty else []
    return options


# ---------------------------------------------------------------------------
# Delay Analysis page queries
# ---------------------------------------------------------------------------

def get_warehouse_delay_rates() -> pd.DataFrame:
    """Delay rate per warehouse, sorted descending."""
    sql = """
        SELECT
            warehouse_id,
            city,
            total_orders,
            delayed_orders,
            ROUND(delay_rate * 100, 1) AS delay_rate_pct,
            ROUND(on_time_rate * 100, 1) AS on_time_rate_pct
        FROM warehouse_metrics
        ORDER BY delay_rate DESC;
    """
    return _safe_query(sql)


def get_city_delay_rates() -> pd.DataFrame:
    """Delay rate per city, sorted descending."""
    sql = """
        SELECT
            city,
            total_orders,
            delayed_orders,
            ROUND(delay_rate * 100, 1) AS delay_rate_pct,
            ROUND(avg_delivery_days, 1) AS avg_delivery_days
        FROM city_metrics
        ORDER BY delay_rate DESC;
    """
    return _safe_query(sql)


def get_delay_by_shipping_type() -> pd.DataFrame:
    """Delay counts and rates per shipping type."""
    sql = """
        SELECT
            shipping_type,
            COUNT(*)                                                       AS total_orders,
            SUM(delay_flag)                                                AS delayed_orders,
            SUM(on_time_flag)                                              AS on_time_orders,
            ROUND(100.0 * SUM(delay_flag) / NULLIF(COUNT(*), 0), 1)       AS delay_rate_pct
        FROM orders
        GROUP BY shipping_type
        ORDER BY delay_rate_pct DESC;
    """
    return _safe_query(sql)


def get_delay_by_distance() -> pd.DataFrame:
    """Average delay days per distance bucket."""
    sql = """
        SELECT
            distance_bucket,
            COUNT(*)                                                      AS total_orders,
            ROUND(AVG(CASE WHEN delay_flag = 1 THEN delay_days END), 1)  AS avg_delay_days,
            ROUND(100.0 * SUM(delay_flag) / NULLIF(COUNT(*), 0), 1)      AS delay_rate_pct
        FROM orders
        WHERE distance_bucket IS NOT NULL
        GROUP BY distance_bucket
        ORDER BY
            CASE distance_bucket
                WHEN '0-250 km'    THEN 1
                WHEN '251-500 km'  THEN 2
                WHEN '501-1000 km' THEN 3
                WHEN '1001+ km'    THEN 4
                ELSE 5
            END;
    """
    return _safe_query(sql)


def get_delay_by_category() -> pd.DataFrame:
    """Delay rate per product category."""
    sql = """
        SELECT
            product_category,
            COUNT(*)                                                        AS total_orders,
            SUM(delay_flag)                                                 AS delayed_orders,
            ROUND(100.0 * SUM(delay_flag) / NULLIF(COUNT(*), 0), 1)        AS delay_rate_pct
        FROM orders
        GROUP BY product_category
        ORDER BY delay_rate_pct DESC;
    """
    return _safe_query(sql)


# ---------------------------------------------------------------------------
# Pipeline Health page queries
# ---------------------------------------------------------------------------

def get_pipeline_health_summary() -> dict:
    """Latest pipeline run stats."""
    sql = """
        SELECT
            status,
            finished_at,
            records_processed,
            records_failed,
            processing_time_sec
        FROM pipeline_runs
        ORDER BY finished_at DESC
        LIMIT 1;
    """
    df = _safe_query(sql)
    if df.empty:
        return {
            "status": "unknown", "finished_at": None,
            "records_processed": 0, "records_failed": 0,
            "processing_time_sec": 0,
        }
    return df.iloc[0].to_dict()


def get_total_records_in_duckdb() -> int:
    """Total order records in DuckDB orders table."""
    df = _safe_query("SELECT COUNT(*) AS cnt FROM orders;")
    return int(df.iloc[0]["cnt"]) if not df.empty else 0


def get_recent_pipeline_runs(limit: int = 10) -> pd.DataFrame:
    """Last `limit` pipeline runs."""
    sql = f"""
        SELECT
            run_id,
            dag_id,
            run_type,
            started_at,
            finished_at,
            status,
            records_processed,
            records_failed,
            ROUND(processing_time_sec, 2) AS processing_time_sec
        FROM pipeline_runs
        ORDER BY finished_at DESC
        LIMIT {limit};
    """
    return _safe_query(sql)


def get_processing_time_trend(limit: int = 50) -> pd.DataFrame:
    """Processing time trend for the last `limit` ETL runs."""
    sql = f"""
        SELECT
            finished_at,
            ROUND(processing_time_sec, 2) AS processing_time_sec,
            records_processed
        FROM pipeline_runs
        WHERE run_type = 'etl'
        ORDER BY finished_at DESC
        LIMIT {limit};
    """
    df = _safe_query(sql)
    if not df.empty:
        df = df.sort_values("finished_at")
    return df


def check_duckdb_connection() -> bool:
    """Return True if DuckDB is reachable."""
    try:
        conn = _conn()
        conn.execute("SELECT 1;")
        conn.close()
        return True
    except Exception:
        return False
