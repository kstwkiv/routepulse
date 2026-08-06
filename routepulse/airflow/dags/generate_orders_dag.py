"""
RoutePulse — Generate Orders DAG
Runs every 5 minutes to produce synthetic delivery orders into PostgreSQL.
"""

import sys
import os
import uuid
import logging
from datetime import datetime, timedelta

from airflow import DAG
from airflow.operators.python import PythonOperator

# Ensure project root is on the path so generator module is importable
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

default_args = {
    "owner":            "routepulse",
    "depends_on_past":  False,
    "start_date":       datetime(2024, 1, 1),
    "retries":          2,
    "retry_delay":      timedelta(minutes=1),
    "email_on_failure": False,
    "email_on_retry":   False,
}

dag = DAG(
    dag_id="generate_orders",
    default_args=default_args,
    description="Generate synthetic delivery orders every 5 minutes",
    schedule_interval="*/5 * * * *",
    catchup=False,
    max_active_runs=1,
    tags=["routepulse", "ingestion"],
)


def _generate_orders(**context):
    """Call the order generator and push result to XCom."""
    try:
        from generator.order_generator import run_generator
        inserted = run_generator()
        logging.info("Generated and inserted %d orders.", inserted)
        context["ti"].xcom_push(key="orders_inserted", value=inserted)
        return inserted
    except Exception as exc:
        logging.error("Order generation failed: %s", exc)
        raise


def _record_run(**context):
    """Write generation result to PostgreSQL pipeline_runs table."""
    import psycopg2

    ti = context["ti"]
    inserted = ti.xcom_pull(task_ids="generate_orders_task", key="orders_inserted") or 0

    try:
        conn = psycopg2.connect(
            host=os.getenv("POSTGRES_HOST", "postgres"),
            port=int(os.getenv("POSTGRES_PORT", 5432)),
            dbname=os.getenv("POSTGRES_DB", "routepulse"),
            user=os.getenv("POSTGRES_USER", "routepulse"),
            password=os.getenv("POSTGRES_PASSWORD", "routepulse123"),
        )
        with conn.cursor() as cur:
            cur.execute("""
                INSERT INTO pipeline_runs
                    (dag_id, run_type, started_at, finished_at, status,
                     records_processed, records_failed, processing_time_sec)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
            """, (
                "generate_orders", "generate",
                context["data_interval_start"], datetime.utcnow(),
                "success", inserted, 0, 0.0,
            ))
        conn.commit()
        conn.close()
    except Exception as exc:
        logging.warning("Could not record pipeline run to Postgres: %s", exc)


generate_task = PythonOperator(
    task_id="generate_orders_task",
    python_callable=_generate_orders,
    dag=dag,
)

record_task = PythonOperator(
    task_id="record_run_task",
    python_callable=_record_run,
    dag=dag,
)

generate_task >> record_task
