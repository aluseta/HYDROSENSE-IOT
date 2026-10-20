"""
Hardware Field Telemetry Simulator for HydroSense-IoT
Emulates PenaAWS datalogger publishing real JSON telemetry packets over MQTT
for all 3 stations across customizable hydrometeorological scenarios.
"""

import argparse
import json
import math
import random
import time
from datetime import datetime, timezone
import paho.mqtt.client as mqtt

# Default MQTT broker settings
MQTT_BROKER = "localhost"
MQTT_PORT = 1883

STATIONS = [
    {"id": "HS-CTM-01", "name": "Citarum Hulu"},
    {"id": "HS-JTG-02", "name": "Jatinangor"},
    {"id": "HS-GRT-03", "name": "Garut"}
]


def generate_telemetry_payload(station_id: str, scenario: str, step: int) -> dict:
    """Generate realistic telemetry measurements based on the active scenario."""
    now_ts = int(time.time())

    if scenario == "flashflood":
        # Intense sudden convective storm
        ra = max(0.0, 14.0 + 3.0 * math.sin(step / 3.0) + random.uniform(-1.0, 1.0))
        h = min(35.0, step * 2.5)  # Rising ponding in infiltrometer
        pvolt = max(11.9, 12.4 - step * 0.02)
        ptemp = 24.5 + random.uniform(-0.5, 0.5)
        # Saturated topsoil
        sm = [
            min(98.0, 75.0 + step * 3.5),
            min(92.0, 60.0 + step * 2.8),
            min(75.0, 45.0 + step * 2.0),
            min(55.0, 30.0 + step * 1.5)
        ]
        st = [23.0, 23.4, 23.8, 24.1]

    elif scenario == "landslide":
        # Prolonged soaking rain driving deep layer saturation
        ra = max(0.0, 4.5 + math.sin(step / 5.0) + random.uniform(-0.5, 0.5))
        h = 8.0 + random.uniform(-0.5, 0.5)
        pvolt = 12.35 + random.uniform(-0.05, 0.05)
        ptemp = 25.0 + random.uniform(-0.5, 0.5)
        # Deep profile saturation (30-40cm)
        sm = [96.0, 95.5, min(99.0, 88.0 + step * 1.5), min(98.0, 85.0 + step * 1.8)]
        st = [22.8, 23.0, 23.2, 23.4]

    elif scenario == "drought":
        # Extended dry conditions with high panel temperatures
        ra = 0.0
        h = 0.0
        pvolt = 13.5 + random.uniform(-0.1, 0.1)
        ptemp = 36.0 + random.uniform(0.0, 2.5)
        # Moisture below permanent wilting point
        sm = [
            max(6.0, 10.0 - step * 0.2),
            max(8.0, 12.0 - step * 0.2),
            max(10.0, 14.0 - step * 0.2),
            max(12.0, 16.0 - step * 0.2)
        ]
        st = [32.0, 30.5, 29.2, 28.5]

    else:
        # Normal baseline conditions
        ra = 0.0 if (step % 20 < 15) else random.uniform(0.5, 2.0)
        h = 0.0
        pvolt = 12.8 + random.uniform(-0.05, 0.05)
        ptemp = 28.5 + random.uniform(-1.0, 1.0)
        sm = [38.0 + math.sin(step / 4.0), 34.0, 28.5, 21.0]
        st = [26.5, 25.8, 25.2, 24.9]

    return {
        "station_id": station_id,
        "timestamp": now_ts,
        "system": {
            "pvolt": round(pvolt, 2),
            "ptemp": round(ptemp, 1)
        },
        "hydro": {
            "ra": round(ra, 2),
            "h": round(h, 2)
        },
        "soil": {
            "depths_cm": [10, 20, 30, 40],
            "sm": [round(x, 1) for x in sm],
            "st": [round(x, 1) for x in st]
        }
    }


def main():
    parser = argparse.ArgumentParser(description="Simulate HydroSense-IoT field telemetry stream.")
    parser.add_argument("--broker", default=MQTT_BROKER, help="MQTT broker address")
    parser.add_argument("--port", type=int, default=MQTT_PORT, help="MQTT broker port")
    parser.add_argument("--scenario", default="normal", choices=["normal", "flashflood", "landslide", "drought"], help="Simulated weather scenario")
    parser.add_argument("--interval", type=int, default=5, help="Publish interval in seconds (default 5s for demo)")
    parser.add_argument("--station", default="HS-CTM-01", help="Target station ID (or 'all')")
    args = parser.parse_args()

    client = mqtt.Client(client_id="HydroSense_Field_Simulator")
    print(f"📡 Connecting to MQTT broker at {args.broker}:{args.port}...")
    try:
        client.connect(args.broker, args.port, 60)
        client.loop_start()
        print(" Connected successfully.")
    except Exception as e:
        print(f"❌ Failed to connect to broker: {e}")
        return

    target_stations = STATIONS if args.station == "all" else [s for s in STATIONS if s["id"] == args.station]
    if not target_stations:
        target_stations = [{"id": args.station, "name": args.station}]

    print(f"🚀 Publishing [{args.scenario.upper()}] telemetry for {len(target_stations)} station(s) every {args.interval}s...")
    step = 0
    try:
        while True:
            for st in target_stations:
                payload = generate_telemetry_payload(st["id"], args.scenario, step)
                topic = f"hydrosense/{st['id']}/telemetry"
                client.publish(topic, json.dumps(payload))
                print(f"[{datetime.now().strftime('%H:%M:%S')}] Published to {topic}: RA={payload['hydro']['ra']} mm/min, SM10={payload['soil']['sm'][0]}%")
            step += 1
            time.sleep(args.interval)
    except KeyboardInterrupt:
        print("\n🛑 Simulation stopped by user.")
        client.loop_stop()
        client.disconnect()


if __name__ == "__main__":
    main()
