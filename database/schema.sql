-- ====================================================================
-- HYDROSENSE-IOT: TimescaleDB / PostgreSQL Production Schema
-- Designed for 1-minute telemetry, ASTM D3385 Horton baselines & EWS
-- ====================================================================

-- 1. Enable TimescaleDB extension if available
CREATE EXTENSION IF NOT EXISTS timescaledb CASCADE;

-- 2. Master Stations Table
CREATE TABLE IF NOT EXISTS stations (
    id VARCHAR(32) PRIMARY KEY,                  -- e.g. 'HS-CTM-01'
    name VARCHAR(128) NOT NULL,                  -- e.g. 'DAS Citarum Hulu Stasiun 01'
    basin_name VARCHAR(128) NOT NULL,            -- e.g. 'DAS Citarum'
    latitude DOUBLE PRECISION,
    longitude DOUBLE PRECISION,
    soil_texture VARCHAR(64) DEFAULT 'Sandy Loam',
    description TEXT,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- 3. Horton Survey Baselines Table
-- Stores empirical parameters obtained from ASTM D3385 double-ring field tests
CREATE TABLE IF NOT EXISTS horton_baselines (
    id SERIAL PRIMARY KEY,
    station_id VARCHAR(32) NOT NULL REFERENCES stations(id) ON DELETE CASCADE,
    f0 DOUBLE PRECISION NOT NULL,                -- Initial infiltration rate (mm/min)
    fc DOUBLE PRECISION NOT NULL,                -- Saturated conductivity Ks (mm/min)
    k DOUBLE PRECISION NOT NULL,                 -- Horton decay constant (min^-1)
    r_squared DOUBLE PRECISION,                  -- Coefficient of determination (R^2)
    survey_date DATE NOT NULL DEFAULT CURRENT_DATE,
    raw_survey_json JSONB,                       -- Raw {t: minutes, f: rate} data array
    is_active BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_horton_station_active 
ON horton_baselines (station_id, is_active);

-- 4. Primary Time-Series Telemetry Table
CREATE TABLE IF NOT EXISTS telemetry (
    ts TIMESTAMPTZ NOT NULL,
    station_id VARCHAR(32) NOT NULL REFERENCES stations(id) ON DELETE CASCADE,
    
    -- System health metrics
    pvolt NUMERIC(5,2),                          -- Battery voltage (V)
    ptemp NUMERIC(5,2),                          -- PenaAWS panel enclosure temp (°C)
    
    -- Hydrology metrics
    ra NUMERIC(6,2) DEFAULT 0.0,                 -- Rain accumulation per minute (mm/min)
    h NUMERIC(6,2) DEFAULT 0.0,                  -- Ponding depth in infiltrometer (mm)
    ir NUMERIC(8,4) DEFAULT 0.0,                 -- Derived infiltration rate f(t) (mm/s)
    
    -- Multi-depth soil moisture (Volumetric Water Content %)
    sm_10 NUMERIC(5,2),
    sm_20 NUMERIC(5,2),
    sm_30 NUMERIC(5,2),
    sm_40 NUMERIC(5,2),
    
    -- Multi-depth soil temperature (°C)
    st_10 NUMERIC(5,2),
    st_20 NUMERIC(5,2),
    st_30 NUMERIC(5,2),
    st_40 NUMERIC(5,2),
    
    PRIMARY KEY (ts, station_id)
);

-- Convert telemetry to TimescaleDB hypertable partitioned by time (7-day chunk interval)
DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM pg_extension WHERE extname = 'timescaledb') THEN
        PERFORM create_hypertable('telemetry', 'ts', chunk_time_interval => INTERVAL '7 days', if_not_exists => TRUE);
    END IF;
END $$;

CREATE INDEX IF NOT EXISTS idx_telemetry_station_ts 
ON telemetry (station_id, ts DESC);

-- 5. Early Warning System (EWS) Alert Logs
CREATE TABLE IF NOT EXISTS ews_alerts (
    id BIGSERIAL PRIMARY KEY,
    ts TIMESTAMPTZ NOT NULL,
    station_id VARCHAR(32) NOT NULL REFERENCES stations(id) ON DELETE CASCADE,
    alert_type VARCHAR(32) NOT NULL,             -- 'flash_flood', 'landslide', 'drought'
    severity VARCHAR(16) NOT NULL,               -- 'INFO', 'WARNING', 'CRITICAL'
    title VARCHAR(128) NOT NULL,
    trigger_reason TEXT NOT NULL,
    metrics_snapshot JSONB,                      -- Snapshot of {ra, ir, sm, h} at trigger time
    is_resolved BOOLEAN DEFAULT FALSE,
    resolved_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_ews_station_ts 
ON ews_alerts (station_id, ts DESC);

-- 6. Helper View: Latest Station Status
CREATE OR REPLACE VIEW v_latest_station_status AS
SELECT DISTINCT ON (s.id)
    s.id AS station_id,
    s.name AS station_name,
    s.basin_name,
    t.ts AS last_seen,
    t.pvolt,
    t.ptemp,
    t.ra,
    t.h AS ponding_depth,
    t.ir AS infiltration_rate,
    t.sm_10, t.sm_20, t.sm_30, t.sm_40,
    t.st_10, t.st_20, t.st_30, t.st_40,
    hb.f0 AS horton_f0,
    hb.fc AS horton_fc,
    hb.k AS horton_k
FROM stations s
LEFT JOIN telemetry t ON s.id = t.station_id
LEFT JOIN horton_baselines hb ON s.id = hb.station_id AND hb.is_active = TRUE
ORDER BY s.id, t.ts DESC;
