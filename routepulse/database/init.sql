-- RoutePulse PostgreSQL Schema
-- Raw orders table for ingesting synthetic delivery data

CREATE TABLE IF NOT EXISTS raw_orders (
    order_id         VARCHAR PRIMARY KEY,
    city             VARCHAR NOT NULL,
    warehouse_id     VARCHAR NOT NULL,
    shipping_type    VARCHAR NOT NULL,       -- 'Standard', 'Express', 'Same-Day'
    product_category VARCHAR NOT NULL,       -- 'Electronics', 'Clothing', 'Food', 'Furniture', 'Books'
    distance_km      FLOAT NOT NULL,
    promised_days    INT NOT NULL,
    actual_days      INT,                    -- NULL if not yet delivered
    status           VARCHAR NOT NULL,       -- 'Delivered', 'In Transit', 'Delayed', 'Pending'
    created_at       TIMESTAMP NOT NULL DEFAULT NOW(),
    updated_at       TIMESTAMP NOT NULL DEFAULT NOW()
);

-- Index on status for fast filtering
CREATE INDEX IF NOT EXISTS idx_raw_orders_status ON raw_orders(status);

-- Index on city for geographic queries
CREATE INDEX IF NOT EXISTS idx_raw_orders_city ON raw_orders(city);

-- Index on created_at for time-series queries
CREATE INDEX IF NOT EXISTS idx_raw_orders_created_at ON raw_orders(created_at);

-- Index on warehouse_id for warehouse-level queries
CREATE INDEX IF NOT EXISTS idx_raw_orders_warehouse ON raw_orders(warehouse_id);

-- Pipeline runs tracking table (mirrored in DuckDB but kept here for resilience)
CREATE TABLE IF NOT EXISTS pipeline_runs (
    run_id           SERIAL PRIMARY KEY,
    dag_id           VARCHAR NOT NULL,
    run_type         VARCHAR NOT NULL,       -- 'generate', 'etl'
    started_at       TIMESTAMP NOT NULL DEFAULT NOW(),
    finished_at      TIMESTAMP,
    status           VARCHAR NOT NULL DEFAULT 'running',  -- 'running', 'success', 'failed'
    records_processed INT DEFAULT 0,
    records_failed   INT DEFAULT 0,
    processing_time_sec FLOAT,
    error_message    TEXT
);
