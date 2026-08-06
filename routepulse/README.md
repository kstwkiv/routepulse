# 🚚 RoutePulse — Live Delivery Intelligence Platform

🌐 **Live Demo:** [routepulse.streamlit.app](https://routepulse.streamlit.app)

A fully automated delivery analytics platform that generates synthetic Indian logistics data, processes it through a real-time ETL pipeline, and visualises it in a professional multi-page Streamlit dashboard.

---

## Architecture

```
Synthetic Generator (every 5 min via Airflow)
         ↓
    PostgreSQL  ←  raw_orders table
         ↓
    Airflow ETL  →  validate → transform → load
         ↓
    DuckDB  →  orders, warehouse_metrics, city_metrics, pipeline_runs
         ↓
    Streamlit  →  4-page dashboard on port 8501
```

---

## Project Structure

```
routepulse/
├── docker-compose.yml          # All services wired together
├── Dockerfile.streamlit        # Streamlit app image
├── Dockerfile.airflow          # Airflow image with project deps
├── .env.example                # Environment variable template
├── requirements.txt
├── README.md
├── airflow/
│   ├── dags/
│   │   ├── generate_orders_dag.py    # Generates synthetic data every 5 min
│   │   └── etl_pipeline_dag.py       # Validate → transform → DuckDB load
│   └── plugins/
├── database/
│   └── init.sql                      # PostgreSQL schema
├── generator/
│   └── order_generator.py            # Synthetic delivery event generator
├── etl/
│   ├── validate.py                   # Data validation
│   ├── transform.py                  # Feature engineering
│   └── load_duckdb.py                # DuckDB upsert layer
├── analytics/
│   └── queries.py                    # All DuckDB queries for Streamlit
├── streamlit_app/
│   ├── app.py                        # Main entry point
│   ├── pages/
│   │   ├── 1_Overview.py             # KPIs, trends, city performance
│   │   ├── 2_Delivery_Operations.py  # Filterable order table
│   │   ├── 3_Delay_Analysis.py       # Delay root-cause charts
│   │   └── 4_Pipeline_Health.py      # ETL monitoring dashboard
│   └── utils/
│       ├── db.py                     # DB connection helpers
│       └── styles.py                 # Shared styling and theming
└── .streamlit/
    └── config.toml                   # Streamlit dark theme config
```

---

## Quick Start

### 1. Clone and configure

```bash
git clone <repo>
cd routepulse
cp .env.example .env
# Edit .env if you want to change credentials
```

### 2. Start all services

```bash
docker compose up --build -d
```

This will:
- Start PostgreSQL and run `init.sql` to create the schema
- Initialise Airflow (create admin user, run DB migrations)
- Start Airflow Webserver and Scheduler
- Start the Streamlit dashboard

### 3. Trigger initial data load

Once services are up, either wait for Airflow to trigger automatically (every 5 min), or trigger manually:

```bash
# Trigger the generator DAG
docker exec routepulse_airflow_scheduler airflow dags trigger generate_orders

# Then trigger the ETL DAG
docker exec routepulse_airflow_scheduler airflow dags trigger etl_pipeline
```

### 4. Access the dashboards

| Service         | URL                          | Credentials      |
|----------------|------------------------------|------------------|
| Streamlit       | http://localhost:8501        | —                |
| Airflow         | http://localhost:8080        | admin / admin    |
| PostgreSQL      | localhost:5432               | routepulse / routepulse123 |

---

## Data Coverage

- **Cities:** Mumbai, Delhi, Bangalore, Hyderabad, Chennai, Kolkata, Pune, Ahmedabad
- **Warehouses:** 11 warehouses across 8 cities
- **Shipping types:** Standard (60%), Express (30%), Same-Day (10%)
- **Product categories:** Electronics, Clothing, Food, Furniture, Books
- **Orders per run:** 50–100 synthetic orders, seeded with 30 days history on first run
- **Delay simulation:** Warehouses HYD01 and KOL01 have elevated delay rates (30–40%)

---

## Dashboard Pages

### 📊 Overview
- Total / Delivered / Delayed / At-Risk order metrics
- Orders & delays over last 7 days (line charts)
- On-time rate by city (horizontal bar)

### 🚛 Delivery Operations
- Sidebar filters: city, warehouse, shipping type, status, date range
- Paginated order table with status emoji badges
- CSV download for filtered results

### ⚠️ Delay Analysis
- Worst-performing warehouses (bar chart)
- City delay rates (horizontal bar)
- Delays by shipping method (grouped bar)
- Delay rate by distance bucket (line + bar)
- Product category delay rates (donut + bar)
- Automated insight callouts

### 🔧 Pipeline Health
- Real-time PostgreSQL, DuckDB, and Airflow connectivity checks
- Latest run status card (processed / failed / time)
- Last 10 pipeline run history table
- Processing time trend and records-processed charts
- Stale data warning if last run > 15 minutes ago

---

## ETL Pipeline

```
generate_orders DAG (*/5 * * * *)
  └── generate_orders_task   — create 50-100 orders → insert to PostgreSQL

etl_pipeline DAG (2-59/5 * * * *)  ← 2-minute offset
  ├── validate_data          — null checks, enum validation, duplicate detection
  ├── transform_data         — delay_days, delay_flag, distance_bucket, speed category
  ├── load_to_duckdb         — upsert orders + warehouse/city aggregates
  └── update_pipeline_metrics — record run stats in pipeline_runs table
```

---

## Environment Variables

| Variable              | Default           | Description                        |
|-----------------------|-------------------|------------------------------------|
| `POSTGRES_USER`       | routepulse        | PostgreSQL username                |
| `POSTGRES_PASSWORD`   | routepulse123     | PostgreSQL password                |
| `POSTGRES_DB`         | routepulse        | PostgreSQL database name           |
| `POSTGRES_HOST`       | postgres          | PostgreSQL hostname (Docker service)|
| `POSTGRES_PORT`       | 5432              | PostgreSQL port                    |
| `DUCKDB_PATH`         | /data/routepulse.duckdb | DuckDB file path (shared volume) |
| `AIRFLOW_UID`         | 50000             | Airflow process UID                |

---

## Local Development (without Docker)

```bash
python -m venv venv
source venv/bin/activate     # Windows: venv\Scripts\activate
pip install -r requirements.txt

# Set env vars pointing to your local Postgres/DuckDB
export POSTGRES_HOST=localhost
export DUCKDB_PATH=./data/routepulse.duckdb

# Seed data
python generator/order_generator.py

# Run ETL manually
python -c "
from etl.validate import run_validation
from etl.transform import transform_orders, build_warehouse_metrics, build_city_metrics
from etl.load_duckdb import run_load
valid_df, _ = run_validation()
t = transform_orders(valid_df)
run_load(t, build_warehouse_metrics(t), build_city_metrics(t))
"

# Start Streamlit
streamlit run streamlit_app/app.py
```

---

## Colour Scheme

| Status      | Colour    |
|-------------|-----------|
| Delayed     | `#FF4B4B` |
| Delivered   | `#00CC88` |
| In Transit  | `#FFD700` |
| Pending     | `#AAAAAA` |
| Primary     | `#1E88E5` |
