"""
RoutePulse — ETL Transformation Layer
Takes validated orders DataFrame and enriches it with derived columns
needed by the analytical layer.
"""

import logging
import numpy as np
import pandas as pd

log = logging.getLogger(__name__)


def transform_orders(df: pd.DataFrame) -> pd.DataFrame:
    """
    Add derived/enriched columns to the validated orders DataFrame.

    New columns:
        delay_days        — actual_days - promised_days (0 for on-time / null for undelivered)
        delay_flag        — 1 if delayed, 0 otherwise
        on_time_flag      — 1 if delivered on time, 0 otherwise
        delivery_speed    — 'Early', 'On Time', 'Delayed', 'Undelivered'
        distance_bucket   — '0-250 km', '251-500 km', '501-1000 km', '1001+ km'
        processing_date   — date portion of created_at (for partitioning)
    """
    if df.empty:
        log.warning("Empty DataFrame passed to transform — nothing to do.")
        return df.copy()

    out = df.copy()

    # ------------------------------------------------------------------
    # Delay metrics
    # ------------------------------------------------------------------
    out["delay_days"] = np.where(
        out["actual_days"].notnull(),
        out["actual_days"] - out["promised_days"],
        np.nan,
    )
    out["delay_days"] = out["delay_days"].astype("float")

    out["delay_flag"] = np.where(
        (out["actual_days"].notnull()) & (out["actual_days"] > out["promised_days"]),
        1, 0,
    ).astype(int)

    out["on_time_flag"] = np.where(
        (out["status"] == "Delivered") & (out["delay_flag"] == 0),
        1, 0,
    ).astype(int)

    # ------------------------------------------------------------------
    # Delivery speed category
    # ------------------------------------------------------------------
    def classify_speed(row):
        if row["status"] in ("In Transit", "Pending"):
            return "Undelivered"
        if row["actual_days"] is None or pd.isnull(row["actual_days"]):
            return "Undelivered"
        diff = int(row["actual_days"]) - int(row["promised_days"])
        if diff < 0:
            return "Early"
        elif diff == 0:
            return "On Time"
        else:
            return "Delayed"

    out["delivery_speed"] = out.apply(classify_speed, axis=1)

    # ------------------------------------------------------------------
    # Distance bucket
    # ------------------------------------------------------------------
    bins   = [0, 250, 500, 1000, 5001]
    labels = ["0-250 km", "251-500 km", "501-1000 km", "1001+ km"]
    out["distance_bucket"] = pd.cut(
        out["distance_km"], bins=bins, labels=labels, right=True
    ).astype(str)

    # ------------------------------------------------------------------
    # Processing date
    # ------------------------------------------------------------------
    out["processing_date"] = pd.to_datetime(out["created_at"]).dt.date

    # ------------------------------------------------------------------
    # Ensure correct types
    # ------------------------------------------------------------------
    out["promised_days"] = out["promised_days"].astype(int)
    out["actual_days"]   = pd.to_numeric(out["actual_days"], errors="coerce")

    log.info(
        "Transformation complete — %d rows, delay rate %.1f%%",
        len(out),
        out["delay_flag"].mean() * 100 if len(out) > 0 else 0,
    )

    return out


def build_warehouse_metrics(df: pd.DataFrame) -> pd.DataFrame:
    """
    Aggregate per-warehouse metrics.
    """
    if df.empty:
        return pd.DataFrame()

    delivered = df[df["status"].isin(["Delivered", "Delayed"])].copy()

    agg = (
        df.groupby("warehouse_id")
        .agg(
            city=("city", "first"),
            total_orders=("order_id", "count"),
            delayed_orders=("delay_flag", "sum"),
            delivered_orders=("on_time_flag", "sum"),
        )
        .reset_index()
    )

    avg_delay = (
        delivered.groupby("warehouse_id")["actual_days"]
        .mean()
        .reset_index()
        .rename(columns={"actual_days": "avg_actual_days"})
    )

    avg_promised = (
        delivered.groupby("warehouse_id")["promised_days"]
        .mean()
        .reset_index()
        .rename(columns={"promised_days": "avg_promised_days"})
    )

    agg = agg.merge(avg_delay, on="warehouse_id", how="left")
    agg = agg.merge(avg_promised, on="warehouse_id", how="left")

    agg["delay_rate"]  = (agg["delayed_orders"] / agg["total_orders"].replace(0, np.nan)).fillna(0)
    agg["on_time_rate"] = (agg["delivered_orders"] / agg["total_orders"].replace(0, np.nan)).fillna(0)
    agg["updated_at"]  = pd.Timestamp.utcnow()

    return agg


def build_city_metrics(df: pd.DataFrame) -> pd.DataFrame:
    """
    Aggregate per-city metrics.
    """
    if df.empty:
        return pd.DataFrame()

    delivered = df[df["status"].isin(["Delivered", "Delayed"])].copy()

    agg = (
        df.groupby("city")
        .agg(
            total_orders=("order_id", "count"),
            delayed_orders=("delay_flag", "sum"),
            delivered_orders=("on_time_flag", "sum"),
        )
        .reset_index()
    )

    avg_days = (
        delivered.groupby("city")["actual_days"]
        .mean()
        .reset_index()
        .rename(columns={"actual_days": "avg_delivery_days"})
    )

    agg = agg.merge(avg_days, on="city", how="left")
    agg["delay_rate"]  = (agg["delayed_orders"] / agg["total_orders"].replace(0, np.nan)).fillna(0)
    agg["on_time_rate"] = (agg["delivered_orders"] / agg["total_orders"].replace(0, np.nan)).fillna(0)
    agg["updated_at"]  = pd.Timestamp.utcnow()

    return agg


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    # Quick smoke test
    sample = pd.DataFrame([{
        "order_id": "test-1", "city": "Mumbai", "warehouse_id": "MUM01",
        "shipping_type": "Express", "product_category": "Electronics",
        "distance_km": 450.0, "promised_days": 3, "actual_days": 5,
        "status": "Delayed",
        "created_at": pd.Timestamp.now(), "updated_at": pd.Timestamp.now(),
    }])
    result = transform_orders(sample)
    print(result[["order_id", "delay_days", "delay_flag", "delivery_speed", "distance_bucket"]].to_string())
