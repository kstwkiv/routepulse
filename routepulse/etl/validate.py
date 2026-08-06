"""
RoutePulse — ETL Validation Layer
Reads unprocessed orders from PostgreSQL and validates them.
Returns a DataFrame of valid rows plus a report of invalid rows.
"""

import os
import logging

import pandas as pd
import psycopg2
from dotenv import load_dotenv

load_dotenv()

log = logging.getLogger(__name__)

VALID_SHIPPING_TYPES    = {"Standard", "Express", "Same-Day"}
VALID_PRODUCT_CATEGORIES = {"Electronics", "Clothing", "Food", "Furniture", "Books"}
VALID_STATUSES          = {"Delivered", "In Transit", "Delayed", "Pending"}
VALID_CITIES            = {
    "Mumbai", "Delhi", "Bangalore", "Hyderabad",
    "Chennai", "Kolkata", "Pune", "Ahmedabad",
}


def get_connection():
    return psycopg2.connect(
        host=os.getenv("POSTGRES_HOST", "postgres"),
        port=int(os.getenv("POSTGRES_PORT", 5432)),
        dbname=os.getenv("POSTGRES_DB", "routepulse"),
        user=os.getenv("POSTGRES_USER", "routepulse"),
        password=os.getenv("POSTGRES_PASSWORD", "routepulse123"),
    )


def fetch_orders(conn) -> pd.DataFrame:
    """Fetch all orders from PostgreSQL into a DataFrame."""
    query = """
        SELECT
            order_id, city, warehouse_id, shipping_type, product_category,
            distance_km, promised_days, actual_days, status,
            created_at, updated_at
        FROM raw_orders
        ORDER BY created_at DESC;
    """
    return pd.read_sql_query(query, conn)


def validate_orders(df: pd.DataFrame) -> tuple:
    """
    Validate a DataFrame of raw orders.

    Returns:
        (valid_df, invalid_df, report_dict)
    """
    if df.empty:
        log.warning("No orders to validate.")
        return df.copy(), pd.DataFrame(), {"total": 0, "valid": 0, "invalid": 0, "issues": []}

    issues = []
    invalid_mask = pd.Series(False, index=df.index)

    # ---- Required non-null columns ----
    required_cols = ["order_id", "city", "warehouse_id", "shipping_type",
                     "product_category", "distance_km", "promised_days", "status"]
    for col in required_cols:
        null_mask = df[col].isnull()
        if null_mask.any():
            count = null_mask.sum()
            issues.append(f"NULL in '{col}': {count} row(s)")
            invalid_mask |= null_mask

    # ---- Duplicate order_ids ----
    dup_mask = df.duplicated(subset="order_id", keep="first")
    if dup_mask.any():
        count = dup_mask.sum()
        issues.append(f"Duplicate order_id: {count} row(s)")
        invalid_mask |= dup_mask

    # ---- Enum validations ----
    bad_shipping = ~df["shipping_type"].isin(VALID_SHIPPING_TYPES)
    if bad_shipping.any():
        issues.append(f"Invalid shipping_type: {bad_shipping.sum()} row(s)")
        invalid_mask |= bad_shipping

    bad_category = ~df["product_category"].isin(VALID_PRODUCT_CATEGORIES)
    if bad_category.any():
        issues.append(f"Invalid product_category: {bad_category.sum()} row(s)")
        invalid_mask |= bad_category

    bad_status = ~df["status"].isin(VALID_STATUSES)
    if bad_status.any():
        issues.append(f"Invalid status: {bad_status.sum()} row(s)")
        invalid_mask |= bad_status

    bad_city = ~df["city"].isin(VALID_CITIES)
    if bad_city.any():
        issues.append(f"Invalid city: {bad_city.sum()} row(s)")
        invalid_mask |= bad_city

    # ---- Numeric range checks ----
    bad_distance = (df["distance_km"] <= 0) | (df["distance_km"] > 5000)
    if bad_distance.any():
        issues.append(f"Out-of-range distance_km: {bad_distance.sum()} row(s)")
        invalid_mask |= bad_distance

    bad_promised = (df["promised_days"] < 1) | (df["promised_days"] > 30)
    if bad_promised.any():
        issues.append(f"Out-of-range promised_days: {bad_promised.sum()} row(s)")
        invalid_mask |= bad_promised

    # actual_days allowed to be NULL (not yet delivered)
    delivered_mask = df["status"].isin({"Delivered", "Delayed"})
    missing_actual = delivered_mask & df["actual_days"].isnull()
    if missing_actual.any():
        issues.append(f"Missing actual_days for delivered/delayed orders: {missing_actual.sum()} row(s)")
        invalid_mask |= missing_actual

    valid_df   = df[~invalid_mask].copy()
    invalid_df = df[invalid_mask].copy()

    report = {
        "total":   len(df),
        "valid":   len(valid_df),
        "invalid": len(invalid_df),
        "issues":  issues,
    }

    if issues:
        log.warning("Validation issues found: %s", issues)
    else:
        log.info("All %d orders passed validation.", len(valid_df))

    return valid_df, invalid_df, report


def run_validation() -> tuple:
    """Connect to Postgres, fetch orders, validate. Returns (valid_df, report)."""
    conn = None
    try:
        conn = get_connection()
        df = fetch_orders(conn)
        log.info("Fetched %d orders from PostgreSQL.", len(df))
        valid_df, invalid_df, report = validate_orders(df)
        log.info(
            "Validation complete — valid: %d, invalid: %d",
            report["valid"], report["invalid"],
        )
        return valid_df, report
    except Exception as exc:
        log.error("Validation step failed: %s", exc)
        raise
    finally:
        if conn:
            conn.close()


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    valid_df, report = run_validation()
    print(report)
