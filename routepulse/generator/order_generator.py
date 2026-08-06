"""
RoutePulse — Synthetic Order Generator
Generates realistic Indian delivery order data and inserts into PostgreSQL.
On first run (empty table), seeds 30 days of historical data (~500 orders).
"""

import os
import random
import uuid
import logging
from datetime import datetime, timedelta

import psycopg2
from psycopg2.extras import execute_values
from dotenv import load_dotenv

load_dotenv()

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Reference data
# ---------------------------------------------------------------------------

CITIES = ["Mumbai", "Delhi", "Bangalore", "Hyderabad", "Chennai", "Kolkata", "Pune", "Ahmedabad"]

WAREHOUSES = {
    "Mumbai":    ["MUM01", "MUM02"],
    "Delhi":     ["DEL01", "DEL02"],
    "Bangalore": ["BLR01"],
    "Hyderabad": ["HYD01", "HYD02"],
    "Chennai":   ["CHN01"],
    "Kolkata":   ["KOL01"],
    "Pune":      ["PUN01"],
    "Ahmedabad": ["AMD01"],
}

# Base delay probability per warehouse (higher = more delays)
WAREHOUSE_DELAY_RATE = {
    "MUM01": 0.12, "MUM02": 0.10,
    "DEL01": 0.15, "DEL02": 0.18,
    "BLR01": 0.12,
    "HYD01": 0.35, "HYD02": 0.30,
    "CHN01": 0.14,
    "KOL01": 0.38,
    "PUN01": 0.16,
    "AMD01": 0.28,
}

# City-level delay multiplier
CITY_DELAY_MULTIPLIER = {
    "Mumbai":    1.0,
    "Delhi":     1.1,
    "Bangalore": 0.9,
    "Hyderabad": 1.2,
    "Chennai":   1.0,
    "Kolkata":   1.4,
    "Pune":      1.0,
    "Ahmedabad": 1.3,
}

# Shipping type distribution: (type, weight, promised_days_range)
SHIPPING_TYPES = [
    ("Standard", 60),
    ("Express",  30),
    ("Same-Day", 10),
]

PRODUCT_CATEGORIES = [
    ("Electronics", 20),
    ("Clothing",    25),
    ("Food",        15),
    ("Furniture",   10),
    ("Books",       30),
]

# Approximate inter-city distances (km)
CITY_DISTANCES = {
    ("Mumbai",    "Delhi"):     1400,
    ("Mumbai",    "Bangalore"): 980,
    ("Mumbai",    "Hyderabad"): 710,
    ("Mumbai",    "Chennai"):   1330,
    ("Mumbai",    "Kolkata"):   2100,
    ("Mumbai",    "Pune"):      150,
    ("Mumbai",    "Ahmedabad"): 530,
    ("Delhi",     "Bangalore"): 2150,
    ("Delhi",     "Hyderabad"): 1570,
    ("Delhi",     "Chennai"):   2200,
    ("Delhi",     "Kolkata"):   1470,
    ("Delhi",     "Pune"):      1410,
    ("Delhi",     "Ahmedabad"): 950,
    ("Bangalore", "Hyderabad"): 570,
    ("Bangalore", "Chennai"):   350,
    ("Bangalore", "Kolkata"):   1880,
    ("Bangalore", "Pune"):      840,
    ("Bangalore", "Ahmedabad"): 1470,
    ("Hyderabad", "Chennai"):   630,
    ("Hyderabad", "Kolkata"):   1500,
    ("Hyderabad", "Pune"):      560,
    ("Hyderabad", "Ahmedabad"): 1150,
    ("Chennai",   "Kolkata"):   1660,
    ("Chennai",   "Pune"):      1190,
    ("Chennai",   "Ahmedabad"): 1900,
    ("Kolkata",   "Pune"):      1870,
    ("Kolkata",   "Ahmedabad"): 1960,
    ("Pune",      "Ahmedabad"): 420,
}


def get_distance(city_a: str, city_b: str) -> float:
    """Return distance between two cities with some random variation."""
    key = tuple(sorted([city_a, city_b]))
    base = CITY_DISTANCES.get(key, 500)
    # ±10% variation
    return round(base * random.uniform(0.90, 1.10), 1)


def weighted_choice(options):
    """Choose from [(value, weight), ...] list."""
    values, weights = zip(*options)
    return random.choices(values, weights=weights, k=1)[0]


def promised_days_for(shipping_type: str) -> int:
    if shipping_type == "Same-Day":
        return 1
    elif shipping_type == "Express":
        return random.randint(2, 3)
    else:
        return random.randint(4, 7)


def actual_days_and_status(
    shipping_type: str,
    promised_days: int,
    warehouse_id: str,
    city: str,
    distance_km: float,
    created_at: datetime,
) -> tuple:
    """
    Returns (actual_days, status).
    ~15% of orders are still 'In Transit' or 'Pending' (no actual_days).
    """
    now = datetime.utcnow()
    hours_old = (now - created_at).total_seconds() / 3600

    # Orders newer than 12 hours are more likely still pending
    if hours_old < 12:
        if random.random() < 0.6:
            return None, "Pending"

    # Decide if in-transit (not yet delivered)
    if random.random() < 0.08:
        return None, "In Transit"

    # Compute delay probability
    base_delay = WAREHOUSE_DELAY_RATE.get(warehouse_id, 0.15)
    city_mult = CITY_DELAY_MULTIPLIER.get(city, 1.0)
    shipping_mult = {"Same-Day": 0.6, "Express": 0.8, "Standard": 1.3}.get(shipping_type, 1.0)
    distance_mult = 1.0 + (distance_km / 5000)

    delay_prob = min(base_delay * city_mult * shipping_mult * distance_mult, 0.70)

    if random.random() < delay_prob:
        # Delayed: actual_days > promised_days
        extra = random.randint(1, max(1, promised_days // 2))
        actual_days = promised_days + extra
        status = "Delayed"
    else:
        # On time: actual_days <= promised_days (can be 1 day early)
        early = random.randint(0, min(1, promised_days - 1))
        actual_days = max(1, promised_days - early)
        status = "Delivered"

    return actual_days, status


def generate_orders(n: int, base_time: datetime = None) -> list:
    """Generate `n` order records as dicts."""
    if base_time is None:
        base_time = datetime.utcnow()

    orders = []
    for _ in range(n):
        city = random.choice(CITIES)
        warehouse_id = random.choice(WAREHOUSES[city])
        shipping_type = weighted_choice(SHIPPING_TYPES)
        product_category = weighted_choice(PRODUCT_CATEGORIES)

        # Destination city for distance calculation
        dest_city = random.choice([c for c in CITIES if c != city])
        distance_km = get_distance(city, dest_city)

        promised_days = promised_days_for(shipping_type)

        # Spread created_at within the last few hours of base_time
        created_at = base_time - timedelta(minutes=random.randint(0, 290))

        actual_days, status = actual_days_and_status(
            shipping_type, promised_days, warehouse_id, city, distance_km, created_at
        )

        orders.append({
            "order_id":         str(uuid.uuid4()),
            "city":             city,
            "warehouse_id":     warehouse_id,
            "shipping_type":    shipping_type,
            "product_category": product_category,
            "distance_km":      distance_km,
            "promised_days":    promised_days,
            "actual_days":      actual_days,
            "status":           status,
            "created_at":       created_at,
            "updated_at":       base_time,
        })

    return orders


def get_connection():
    return psycopg2.connect(
        host=os.getenv("POSTGRES_HOST", "postgres"),
        port=int(os.getenv("POSTGRES_PORT", 5432)),
        dbname=os.getenv("POSTGRES_DB", "routepulse"),
        user=os.getenv("POSTGRES_USER", "routepulse"),
        password=os.getenv("POSTGRES_PASSWORD", "routepulse123"),
    )


def table_is_empty(conn) -> bool:
    with conn.cursor() as cur:
        cur.execute("SELECT COUNT(*) FROM raw_orders;")
        return cur.fetchone()[0] == 0


def insert_orders(conn, orders: list) -> int:
    if not orders:
        return 0

    rows = [
        (
            o["order_id"], o["city"], o["warehouse_id"], o["shipping_type"],
            o["product_category"], o["distance_km"], o["promised_days"],
            o["actual_days"], o["status"], o["created_at"], o["updated_at"],
        )
        for o in orders
    ]

    sql = """
        INSERT INTO raw_orders
            (order_id, city, warehouse_id, shipping_type, product_category,
             distance_km, promised_days, actual_days, status, created_at, updated_at)
        VALUES %s
        ON CONFLICT (order_id) DO UPDATE SET
            actual_days = EXCLUDED.actual_days,
            status      = EXCLUDED.status,
            updated_at  = EXCLUDED.updated_at;
    """
    with conn.cursor() as cur:
        execute_values(cur, sql, rows)
    conn.commit()
    return len(rows)


def seed_historical_data(conn):
    """Generate ~30 days of historical data so the dashboard isn't empty on first launch."""
    log.info("Seeding historical data (30 days)…")
    all_orders = []
    now = datetime.utcnow()

    for day_offset in range(30, 0, -1):
        base = now - timedelta(days=day_offset)
        n = random.randint(15, 25)  # ~500 total orders across 30 days
        orders = generate_orders(n, base_time=base)
        all_orders.extend(orders)

    inserted = insert_orders(conn, all_orders)
    log.info("Seeded %d historical orders.", inserted)


def run_generator():
    """Main entry: generates 50-100 new orders and inserts them."""
    conn = None
    try:
        conn = get_connection()
        log.info("Connected to PostgreSQL.")

        if table_is_empty(conn):
            seed_historical_data(conn)

        n = random.randint(50, 100)
        orders = generate_orders(n)
        inserted = insert_orders(conn, orders)
        log.info("Inserted %d new orders.", inserted)
        return inserted

    except Exception as exc:
        log.error("Generator failed: %s", exc)
        raise
    finally:
        if conn:
            conn.close()


if __name__ == "__main__":
    run_generator()
