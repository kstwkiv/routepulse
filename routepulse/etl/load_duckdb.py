"""
RoutePulse — DuckDB Loader
Upserts transformed orders and aggregated metrics into DuckDB.
Also maintains the pipeline_runs table for health monitoring.
"""

import os
import logging
import time
from datetime import datetime

import duckdb
import pandas as pd
from dotenv import load_dotenv

load_dotenv()

log = logging.getLogger(__name__)

DUCKDB_PATH = os.getenv("DUCKDB_PATH", "/data/routepulse.duckdb")


def get_connection() -> duckdb.DuckDBPyConnection:
    """Open (or create) the DuckDB file."""
    os.makedirs(os.path.dirname(DUCKDB_PATH), exist_ok=True)
    conn = duckdb.connect(DUCKDB_PATH)
    _ensure_schema(conn)
    return conn


def _ensure_schema(conn: duckdb.DuckDBPyConnection):
    """Create DuckDB tables if they don't exist."""
    conn.execute("""
        CREATE TABLE IF NOT EXISTS orders (
            order_id         VARCHAR PRIMARY KEY,
            city             VARCHAR,
            warehouse_id     VARCHAR,
            shipping_type    VARCHAR,
            product_category VARCHAR,
            distance_km      DOUBLE,
            promised_days    INTEGER,
            actual_days      DOUBLE,
            status           VARCHAR,
            created_at       TIMESTAMP,
            updated_at       TIMESTAMP,
            delay_days       DOUBLE,
            delay_flag       INTEGER,
            on_time_flag     INTEGER,
            delivery_speed   VARCHAR,
            distance_bucket  VARCHAR,
            processing_date  DATE
        );
    """)

    conn.execute("""
        CREATE TABLE IF NOT EXISTS warehouse_metrics (
            warehouse_id      VARCHAR PRIMARY KEY,
            city              VARCHAR,
            total_orders      INTEGER,
            delayed_orders    INTEGER,
            delivered_orders  INTEGER,
            avg_actual_days   DOUBLE,
            avg_promised_days DOUBLE,
            delay_rate        DOUBLE,
            on_time_rate      DOUBLE,
            updated_at        TIMESTAMP
        );
    """)

    conn.execute("""
        CREATE TABLE IF NOT EXISTS city_metrics (
            city              VARCHAR PRIMARY KEY,
            total_orders      INTEGER,
            delayed_orders    INTEGER,
            delivered_orders  INTEGER,
            avg_delivery_days DOUBLE,
            delay_rate        DOUBLE,
            on_time_rate      DOUBLE,
            updated_at        TIMESTAMP
        );
    """)

    conn.execute("""
        CREATE TABLE IF NOT EXISTS pipeline_runs (
            run_id              VARCHAR PRIMARY KEY,
            dag_id              VARCHAR,
            run_type            VARCHAR,
            started_at          TIMESTAMP,
            finished_at         TIMESTAMP,
            status              VARCHAR,
            records_processed   INTEGER,
            records_failed      INTEGER,
            processing_time_sec DOUBLE,
            error_message       VARCHAR
        );
    """)


def upsert_orders(conn: duckdb.DuckDBPyConnection, df: pd.DataFrame) -> int:
    """Upsert orders into DuckDB using DELETE + INSERT pattern."""
    if df.empty:
        return 0

    # Ensure proper types
    df = df.copy()
    df["delay_days"]   = pd.to_numeric(df["delay_days"],   errors="coerce")
    df["actual_days"]  = pd.to_numeric(df["actual_days"],  errors="coerce")
    df["delay_flag"]   = df["delay_flag"].fillna(0).astype(int)
    df["on_time_flag"] = df["on_time_flag"].fillna(0).astype(int)

    columns = [
        "order_id", "city", "warehouse_id", "shipping_type", "product_category",
        "distance_km", "promised_days", "actual_days", "status",
        "created_at", "updated_at",
        "delay_days", "delay_flag", "on_time_flag",
        "delivery_speed", "distance_bucket", "processing_date",
    ]
    # Keep only available columns
    available = [c for c in columns if c in df.columns]
    df_load = df[available]

    # Register as temp view for DuckDB
    conn.register("_orders_staging", df_load)

    # DELETE existing rows that will be replaced
    conn.execute("""
        DELETE FROM orders
        WHERE order_id IN (SELECT order_id FROM _orders_staging);
    """)

    # INSERT new data
    conn.execute(f"""
        INSERT INTO orders ({', '.join(available)})
        SELECT {', '.join(available)} FROM _orders_staging;
    """)

    conn.unregister("_orders_staging")
    log.info("Upserted %d orders into DuckDB.", len(df_load))
    return len(df_load)


def upsert_warehouse_metrics(conn: duckdb.DuckDBPyConnection, df: pd.DataFrame):
    """Replace warehouse_metrics with fresh aggregates."""
    if df.empty:
        return
    conn.register("_wh_staging", df)
    conn.execute("DELETE FROM warehouse_metrics;")
    conn.execute("""
        INSERT INTO warehouse_metrics
        SELECT
            warehouse_id, city, total_orders, delayed_orders, delivered_orders,
            avg_actual_days, avg_promised_days, delay_rate, on_time_rate, updated_at
        FROM _wh_staging;
    """)
    conn.unregister("_wh_staging")
    log.info("Upserted %d warehouse metric rows.", len(df))


def upsert_city_metrics(conn: duckdb.DuckDBPyConnection, df: pd.DataFrame):
    """Replace city_metrics with fresh aggregates."""
    if df.empty:
        return
    conn.register("_city_staging", df)
    conn.execute("DELETE FROM city_metrics;")
    conn.execute("""
        INSERT INTO city_metrics
        SELECT
            city, total_orders, delayed_orders, delivered_orders,
            avg_delivery_days, delay_rate, on_time_rate, updated_at
        FROM _city_staging;
    """)
    conn.unregister("_city_staging")
    log.info("Upserted %d city metric rows.", len(df))


def record_pipeline_run(
    conn: duckdb.DuckDBPyConnection,
    run_id: str,
    dag_id: str,
    run_type: str,
    started_at: datetime,
    finished_at: datetime,
    status: str,
    records_processed: int,
    records_failed: int,
    processing_time_sec: float,
    error_message: str = None,
):
    """Persist a pipeline run record."""
    conn.execute("DELETE FROM pipeline_runs WHERE run_id = ?;", [run_id])
    conn.execute("""
        INSERT INTO pipeline_runs
            (run_id, dag_id, run_type, started_at, finished_at, status,
             records_processed, records_failed, processing_time_sec, error_message)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?);
    """, [
        run_id, dag_id, run_type, started_at, finished_at, status,
        records_processed, records_failed, processing_time_sec,
        error_message or "",
    ])
    log.info("Recorded pipeline run %s — %s.", run_id, status)


def run_load(transformed_df: pd.DataFrame,
             warehouse_metrics_df: pd.DataFrame,
             city_metrics_df: pd.DataFrame) -> dict:
    """
    Full load step: upsert all tables.
    Returns a summary dict with counts.
    """
    start = time.time()
    conn = None
    try:
        conn = get_connection()
        orders_loaded = upsert_orders(conn, transformed_df)
        upsert_warehouse_metrics(conn, warehouse_metrics_df)
        upsert_city_metrics(conn, city_metrics_df)
        elapsed = round(time.time() - start, 2)
        log.info("DuckDB load complete in %.2f sec.", elapsed)
        return {"orders_loaded": orders_loaded, "elapsed_sec": elapsed, "status": "success"}
    except Exception as exc:
        log.error("DuckDB load failed: %s", exc)
        raise
    finally:
        if conn:
            conn.close()


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    # Quick connectivity test
    conn = get_connection()
    print("DuckDB tables:", conn.execute("SHOW TABLES;").fetchall())
    conn.close()
