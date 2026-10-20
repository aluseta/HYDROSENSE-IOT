"""
FastAPI Backend Server for HydroSense-IoT
Serves REST API endpoints for telemetry visualization, Horton curve calibration,
and real-time early warning system alerts.
"""

from typing import List, Dict, Any, Optional
from datetime import datetime, timezone
import json
import psycopg2
from psycopg2.extras import RealDictCursor
from fastapi import FastAPI, HTTPException, Query, Body
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from config import DB_HOST, DB_PORT, DB_NAME, DB_USER, DB_PASSWORD
from horton_engine import fit_horton_curve

app = FastAPI(
    title="HydroSense-IoT Telemetry & EWS API",
    version="1.0.0",
    description="REST API for hydrological monitoring, Horton parameter calibration, and early warning detection."
)

# Enable CORS for web dashboards
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


def get_db():
    return psycopg2.connect(
        host=DB_HOST,
        port=DB_PORT,
        dbname=DB_NAME,
        user=DB_USER,
        password=DB_PASSWORD
    )


class HortonDataPoint(BaseModel):
    t: float = Field(..., description="Time in minutes")
    f: float = Field(..., description="Measured infiltration rate in mm/min")


class HortonFitRequest(BaseModel):
    survey_data: List[HortonDataPoint]
    survey_date: Optional[str] = None


@app.get("/api/health")
def health_check():
    return {"status": "healthy", "timestamp": datetime.now(timezone.utc).isoformat()}


@app.get("/api/stations")
def list_stations():
    """Retrieve all monitoring stations with latest telemetry snapshot."""
    try:
        with get_db() as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute("SELECT * FROM v_latest_station_status;")
                rows = cur.fetchall()
                return {"stations": rows}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/stations/{station_id}/telemetry")
def get_station_telemetry(station_id: str, minutes: int = Query(60, ge=5, le=1440)):
    """Retrieve historical time-series for chart rendering over the past N minutes."""
    try:
        with get_db() as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute(
                    """
                    SELECT 
                        ts, pvolt, ptemp, ra, h, ir,
                        sm_10, sm_20, sm_30, sm_40,
                        st_10, st_20, st_30, st_40
                    FROM telemetry
                    WHERE station_id = %s
                      AND ts >= NOW() - (%s || ' minutes')::INTERVAL
                    ORDER BY ts ASC;
                    """,
                    (station_id, minutes)
                )
                rows = cur.fetchall()
                return {
                    "station_id": station_id,
                    "count": len(rows),
                    "telemetry": rows
                }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/stations/{station_id}/horton")
def get_active_horton_baseline(station_id: str):
    """Retrieve the active Horton baseline empirical parameters for a station."""
    try:
        with get_db() as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute(
                    """
                    SELECT id, f0, fc, k, r_squared, survey_date, raw_survey_json, is_active, created_at
                    FROM horton_baselines
                    WHERE station_id = %s AND is_active = TRUE
                    LIMIT 1;
                    """,
                    (station_id,)
                )
                row = cur.fetchone()
                if not row:
                    raise HTTPException(status_code=404, detail="No active Horton baseline found for station.")
                return row
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/stations/{station_id}/horton/fit")
def calibrate_horton_curve(station_id: str, payload: HortonFitRequest):
    """
    Fits empirical double-ring infiltrometer survey points, calculates Horton parameters,
    and saves the result as the active baseline for the station.
    """
    if len(payload.survey_data) < 3:
        raise HTTPException(status_code=400, detail="Minimum 3 data points required for curve fitting.")

    data_dicts = [{"t": pt.t, "f": pt.f} for pt in payload.survey_data]
    try:
        fit_results = fit_horton_curve(data_dicts)
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Fitting failed: {e}")

    survey_date = payload.survey_date or datetime.now(timezone.utc).date().isoformat()

    try:
        with get_db() as conn:
            with conn.cursor() as cur:
                # Deactivate previous active baseline
                cur.execute(
                    "UPDATE horton_baselines SET is_active = FALSE WHERE station_id = %s;",
                    (station_id,)
                )
                # Insert newly calibrated baseline
                cur.execute(
                    """
                    INSERT INTO horton_baselines (
                        station_id, f0, fc, k, r_squared, survey_date, raw_survey_json, is_active
                    ) VALUES (
                        %s, %s, %s, %s, %s, %s, %s, TRUE
                    ) RETURNING id;
                    """,
                    (
                        station_id,
                        fit_results["f0"],
                        fit_results["fc"],
                        fit_results["k"],
                        fit_results["r_squared"],
                        survey_date,
                        json.dumps(data_dicts)
                    )
                )
                new_id = cur.fetchone()[0]
            conn.commit()

        return {
            "message": "Horton baseline calibrated and activated successfully.",
            "baseline_id": new_id,
            "station_id": station_id,
            "params": fit_results
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/stations/{station_id}/alerts")
def get_station_alerts(station_id: str, limit: int = Query(20, ge=1, le=100)):
    """Retrieve recent EWS alerts triggered for the station."""
    try:
        with get_db() as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute(
                    """
                    SELECT id, ts, alert_type, severity, title, trigger_reason, metrics_snapshot, is_resolved
                    FROM ews_alerts
                    WHERE station_id = %s
                    ORDER BY ts DESC
                    LIMIT %s;
                    """,
                    (station_id, limit)
                )
                return {"alerts": cur.fetchall()}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
