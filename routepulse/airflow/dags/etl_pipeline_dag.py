"""
RoutePulse — ETL Pipeline DAG
Runs every 5 minutes: validate → transform → load → update metrics.
Offset by 2 minutes from the generator DAG.
"""

import sys
import os
import uuid
import time
import logging
from datetime import datetime, timedelta

from airflow import DAG
from airflow.operators.python import PythonOperator

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

default_args = {
    "owner":            "routepulse",
    "depends_on_past":  False,
    "start_date":       datetime(2024, 1, 1),
    "retries":          1,
    "retry_delay":      timedelta(minutes=1),
    "email_on_failure": False,
    "email_on_retry":   False,
}

dag = DAG(
    dag_id="etl_pipeline",
    default_args=default_args,
    description="Validate, transform, and load orders into DuckDB every 5 minutes",
    schedule_interval="2-59/5 * * * *",  # offset by 2 minutes
    catchup=False,
    max_active_runs=1,
    tags=["routepulse", "etl"],
)


# ---------------------------------------------------------------------------
# Task 1: Validate
# ---------------------------------------------------------------------------
def _validate_data(**context):
    from etl.validate import run_validation

    start = time.time()
    try:
        valid_df, report = run_validation()
        elapsed = round(time.time() - start, 2)

        logging.info(
            "Validation: total=%d valid=%d invalid=%d",
            report["total"], report["valid"], report["invalid"],
        )

        # Serialise to JSON-safe dict for XCom (parquet bytes would be better for large data,
        # but for this scale JSON is fine)
        context["ti"].xcom_push(key="valid_count",   value=report["valid"])
        context["ti"].xcom_push(key="invalid_count", value=report["invalid"])
        context["ti"].xcom_push(key="validate_elapsed", value=elapsed)

        # Pass the DataFrame as a JSON string (< 1 MB for typical runs)
        context["ti"].xcom_push(
            key="valid_df_json",
            value=valid_df.to_json(orient="records", date_format="iso"),
        )
        return report
    except Exception as exc:
        logging.error("Validation task failed: %s", exc)
        raise


# ---------------------------------------------------------------------------
# Task 2: Transform
# ---------------------------------------------------------------------------
def _transform_data(**context):
    import json
    import pandas as pd
    from etl.transform import transform_orders, build_warehouse_metrics, build_city_metrics

    ti = context["ti"]
    valid_df_json = ti.xcom_pull(task_ids="validate_data", key="valid_df_json")

    if not valid_df_json:
        logging.warning("No valid orders to transform.")
        context["ti"].xcom_push(key="transformed_df_json", value="[]")
        context["ti"].xcom_push(key="warehouse_metrics_json", value="[]")
        context["ti"].xcom_push(key="city_metrics_json", value="[]")
        return

    df = pd.read_json(valid_df_json, orient="records")

    start = time.time()
    transformed_df      = transform_orders(df)
    warehouse_metrics   = build_warehouse_metrics(transformed_df)
    city_metrics        = build_city_metrics(transformed_df)
    elapsed = round(time.time() - start, 2)

    logging.info("Transform complete in %.2f sec — %d rows.", elapsed, len(transformed_df))

    ti.xcom_push(
        key="transformed_df_json",
        value=transformed_df.to_json(orient="records", date_format="iso"),
    )
    ti.xcom_push(
        key="warehouse_metrics_json",
        value=warehouse_metrics.to_json(orient="records", date_format="iso"),
    )
    ti.xcom_push(
        key="city_metrics_json",
        value=city_metrics.to_json(orient="records", date_format="iso"),
    )
    ti.xcom_push(key="transform_elapsed", value=elapsed)


# ---------------------------------------------------------------------------
# Task 3: Load to DuckDB
# ---------------------------------------------------------------------------
def _load_to_duckdb(**context):
    import pandas as pd
    from etl.load_duckdb import run_load

    ti = context["ti"]
    transformed_json     = ti.xcom_pull(task_ids="transform_data", key="transformed_df_json")
    warehouse_json       = ti.xcom_pull(task_ids="transform_data", key="warehouse_metrics_json")
    city_json            = ti.xcom_pull(task_ids="transform_data", key="city_metrics_json")

    if not transformed_json or transformed_json == "[]":
        logging.warning("No transformed data to load.")
        ti.xcom_push(key="load_result", value={"orders_loaded": 0, "elapsed_sec": 0})
        return

    transformed_df    = pd.read_json(transformed_json,  orient="records")
    warehouse_df      = pd.read_json(warehouse_json,     orient="records")
    city_df           = pd.read_json(city_json,          orient="records")

    result = run_load(transformed_df, warehouse_df, city_df)
    ti.xcom_push(key="load_result", value=result)
    logging.info("Load result: %s", result)


# ---------------------------------------------------------------------------
# Task 4: Update pipeline metrics
# ---------------------------------------------------------------------------
def _update_pipeline_metrics(**context):
    import pandas as pd
    from etl.load_duckdb import get_connection, record_pipeline_run

    ti          = context["ti"]
    run_id      = str(uuid.uuid4())
    started_at  = context["data_interval_start"]
    finished_at = datetime.utcnow()

    valid_count   = ti.xcom_pull(task_ids="validate_data",  key="valid_count")   or 0
    invalid_count = ti.xcom_pull(task_ids="validate_data",  key="invalid_count") or 0
    load_result   = ti.xcom_pull(task_ids="load_to_duckdb", key="load_result")   or {}

    orders_loaded = load_result.get("orders_loaded", 0)
    elapsed_sec   = load_result.get("elapsed_sec", 0.0)

    conn = None
    try:
        conn = get_connection()
        record_pipeline_run(
            conn       = conn,
            run_id     = run_id,
            dag_id     = "etl_pipeline",
            run_type   = "etl",
            started_at = started_at,
            finished_at= finished_at,
            status     = "success",
            records_processed = orders_loaded,
            records_failed    = invalid_count,
            processing_time_sec = elapsed_sec,
        )
    except Exception as exc:
        logging.error("Failed to record pipeline metrics: %s", exc)
    finally:
        if conn:
            conn.close()


# ---------------------------------------------------------------------------
# Wire up tasks
# ---------------------------------------------------------------------------
validate_task = PythonOperator(
    task_id="validate_data",
    python_callable=_validate_data,
    dag=dag,
)

transform_task = PythonOperator(
    task_id="transform_data",
    python_callable=_transform_data,
    dag=dag,
)

load_task = PythonOperator(
    task_id="load_to_duckdb",
    python_callable=_load_to_duckdb,
    dag=dag,
)

metrics_task = PythonOperator(
    task_id="update_pipeline_metrics",
    python_callable=_update_pipeline_metrics,
    dag=dag,
)

validate_task >> transform_task >> load_task >> metrics_task
