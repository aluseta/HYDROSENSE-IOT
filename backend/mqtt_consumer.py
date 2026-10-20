"""
MQTT Ingestion Worker for HydroSense-IoT
Subscribes to telemetry topics, executes mass-balance infiltration calculations,
evaluates EWS rules, and writes time-series records to TimescaleDB.
"""

import json
import logging
import time
from datetime import datetime, timezone
import psycopg2
from psycopg2.extras import RealDictCursor
import paho.mqtt.client as mqtt

from config import (
    DB_HOST, DB_PORT, DB_NAME, DB_USER, DB_PASSWORD,
    MQTT_BROKER, MQTT_PORT, MQTT_TOPIC_TELEMETRY,
    MQTT_USERNAME, MQTT_PASSWORD
)
from horton_engine import calculate_dynamic_infiltration
from ews_rules import evaluate_ews_alerts

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("MQTT_Consumer")

from contextlib import contextmanager

# In-memory station state tracker for ΔH/Δt computation
station_state = {}

# In-memory alert debouncing tracker: (station_id, alert_type) -> last_trigger_timestamp
ALERT_COOLDOWN_SECONDS = 300  # 5 minutes
recent_alerts = {}


@contextmanager
def get_db_connection():
    conn = psycopg2.connect(
        host=DB_HOST,
        port=DB_PORT,
        dbname=DB_NAME,
        user=DB_USER,
        password=DB_PASSWORD
    )
    try:
        yield conn
    finally:
        conn.close()


def get_active_horton_fc(station_id: str) -> float:
    """Fetch active Horton fc (steady infiltration capacity in mm/min) from DB."""
    try:
        with get_db_connection() as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute(
                    "SELECT fc FROM horton_baselines WHERE station_id = %s AND is_active = TRUE LIMIT 1;",
                    (station_id,)
                )
                row = cur.fetchone()
                if row:
                    return float(row["fc"])
    except Exception as e:
        logger.warning(f"Could not fetch Horton fc for {station_id}: {e}")
    return 0.96  # Default fallback (mm/min)



def on_connect(client, userdata, flags, rc):
    if rc == 0:
        logger.info(f"Connected to MQTT Broker ({MQTT_BROKER}:{MQTT_PORT})")
        client.subscribe(MQTT_TOPIC_TELEMETRY)
        logger.info(f"Subscribed to topic pattern: {MQTT_TOPIC_TELEMETRY}")
    else:
        logger.error(f"Failed to connect to MQTT broker, return code: {rc}")


def on_message(client, userdata, msg):
    try:
        payload_str = msg.payload.decode("utf-8")
        data = json.loads(payload_str)
        
        station_id = data.get("station_id") or msg.topic.split("/")[1]
        raw_ts = data.get("timestamp")
        
        if raw_ts:
            ts = datetime.fromtimestamp(raw_ts, tz=timezone.utc)
        else:
            ts = datetime.now(timezone.utc)

        system = data.get("system", {})
        pvolt = float(system.get("pvolt", 12.0))
        ptemp = float(system.get("ptemp", 25.0))

        hydro = data.get("hydro", {})
        ra = float(hydro.get("ra", 0.0))
        h = float(hydro.get("h", 0.0))

        soil = data.get("soil", {})
        sm_list = [float(x) for x in soil.get("sm", [0.0, 0.0, 0.0, 0.0])]
        st_list = [float(x) for x in soil.get("st", [25.0, 25.0, 25.0, 25.0])]

        # Ensure 4-element arrays
        while len(sm_list) < 4: sm_list.append(0.0)
        while len(st_list) < 4: st_list.append(25.0)

        # Dynamic Infiltration calculation: f(t) = I(t) - ΔH/Δt
        prev_h = None
        prev_time = None
        if station_id in station_state:
            prev_h = station_state[station_id].get("h")
            prev_time = station_state[station_id].get("ts")

        delta_t_min = 1.0
        if prev_time:
            delta_t_min = max(0.1, (time.time() - prev_time) / 60.0)

        fc_survey = get_active_horton_fc(station_id)
        
        # If payload already has computed 'ir', use it or compute dynamically
        if "ir" in hydro and hydro["ir"] is not None:
            ir = float(hydro["ir"])
            phase = "computed_by_edge"
        else:
            ir, phase = calculate_dynamic_infiltration(
                rain_rate_mm_min=ra,
                current_ponding_h_mm=h,
                previous_ponding_h_mm=prev_h,
                delta_t_min=delta_t_min,
                fc_steady_mm_min=fc_survey
            )

        # Update cache
        station_state[station_id] = {"h": h, "ts": time.time()}

        # 1. Insert into TimescaleDB telemetry table
        with get_db_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO telemetry (
                        ts, station_id, pvolt, ptemp, ra, h, ir,
                        sm_10, sm_20, sm_30, sm_40,
                        st_10, st_20, st_30, st_40
                    ) VALUES (
                        %s, %s, %s, %s, %s, %s, %s,
                        %s, %s, %s, %s,
                        %s, %s, %s, %s
                    ) ON CONFLICT (ts, station_id) DO NOTHING;
                    """,
                    (
                        ts, station_id, pvolt, ptemp, ra, h, ir,
                        sm_list[0], sm_list[1], sm_list[2], sm_list[3],
                        st_list[0], st_list[1], st_list[2], st_list[3]
                    )
                )

                # 2. Evaluate EWS Rules
                alerts = evaluate_ews_alerts(
                    station_id=station_id,
                    pvolt=pvolt,
                    ra=ra,
                    ir=ir,
                    h=h,
                    sm=sm_list
                )

                now_epoch = time.time()
                for alert in alerts:
                    key = (station_id, alert["alert_type"])
                    last_time = recent_alerts.get(key, 0)
                    # Debounce: Skip duplicate alerts for the same station & type within cooldown period
                    if now_epoch - last_time < ALERT_COOLDOWN_SECONDS:
                        continue

                    recent_alerts[key] = now_epoch
                    cur.execute(
                        """
                        INSERT INTO ews_alerts (
                            ts, station_id, alert_type, severity, title, trigger_reason, metrics_snapshot
                        ) VALUES (
                            %s, %s, %s, %s, %s, %s, %s
                        );
                        """,
                        (
                            ts,
                            alert["station_id"],
                            alert["alert_type"],
                            alert["severity"],
                            alert["title"],
                            alert["trigger_reason"],
                            json.dumps(alert["metrics"])
                        )
                    )
                    # Publish alert to outbound MQTT topic
                    alert_topic = f"hydrosense/{station_id}/alert"
                    client.publish(alert_topic, json.dumps(alert))
                    logger.warning(f"🚨 EWS ALERT TRIGGERED: {alert['title']} [{station_id}]")


            conn.commit()

        logger.info(f"[{station_id}] Telemetry logged: RA={ra} mm/min, IR={ir} mm/s, H={h} mm, SM10={sm_list[0]}%")

    except Exception as e:
        logger.error(f"Error processing MQTT message: {e}", exc_info=True)


def main():
    client = mqtt.Client(client_id="HydroSense_Backend_Consumer")
    if MQTT_USERNAME and MQTT_PASSWORD:
        client.username_pw_set(MQTT_USERNAME, MQTT_PASSWORD)

    client.on_connect = on_connect
    client.on_message = on_message

    logger.info(f"Starting MQTT consumer, connecting to {MQTT_BROKER}:{MQTT_PORT}...")
    client.connect(MQTT_BROKER, MQTT_PORT, 60)
    client.loop_forever()


if __name__ == "__main__":
    main()
