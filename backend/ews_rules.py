"""
Early Warning System (EWS) Rules Engine for HydroSense-IoT
Evaluates real-time sensor streams against hydrometeorological thresholds:
- Hortonian Flash Flood (Surface Runoff)
- Shallow Landslide (Pore Pressure Buildup)
- Agricultural Drought (Soil Water Deficit)
- System Hardware Health (Battery Voltage)
"""

from typing import List, Dict, Any


def evaluate_ews_alerts(
    station_id: str,
    pvolt: float,
    ra: float,
    ir: float,
    h: float,
    sm: List[float]
) -> List[Dict[str, Any]]:
    """
    Evaluates current telemetry against physics-based EWS rules.

    :param station_id: Station identifier (e.g. 'HS-CTM-01')
    :param pvolt: Battery voltage (V)
    :param ra: Rain rate (mm/min)
    :param ir: Infiltration rate (mm/s)
    :param h: Ponding level in ring (mm)
    :param sm: Soil moisture list at [10, 20, 30, 40] cm depths (%)
    :return: List of alert dictionaries to log and dispatch
    """
    alerts = []

    sm_10 = sm[0] if len(sm) > 0 else 0.0
    sm_20 = sm[1] if len(sm) > 1 else 0.0
    sm_30 = sm[2] if len(sm) > 2 else 0.0
    sm_40 = sm[3] if len(sm) > 3 else 0.0
    sm_avg = sum(sm) / len(sm) if sm else 0.0

    # 1. Flash Flood Alert (Hortonian Excess Runoff)
    # Condition: Rain intensity exceeds infiltration capacity (I >> f) and topsoil is near saturation
    rain_rate_mm_s = ra / 60.0
    if ra >= 5.0 and (rain_rate_mm_s > ir) and sm_10 >= 85.0:
        alerts.append({
            "station_id": station_id,
            "alert_type": "flash_flood",
            "severity": "CRITICAL",
            "title": "AWAS: Potensi Banjir Bandang (Limpasan Hortonian)",
            "trigger_reason": (
                f"Intensitas hujan ({ra:.1f} mm/min) melebihi laju resapan air tanah ({ir:.4f} mm/s) "
                f"dengan kelembaban topsoil 10cm mencapai {sm_10:.1f}%. Terjadi genangan & limpasan masif."
            ),
            "metrics": {"ra": ra, "ir": ir, "sm_10": sm_10, "h": h}
        })
    elif ra >= 2.5 and (rain_rate_mm_s > ir) and sm_10 >= 75.0:
        alerts.append({
            "station_id": station_id,
            "alert_type": "flash_flood",
            "severity": "WARNING",
            "title": "WASPADA: Laju Infiltrasi Menurun",
            "trigger_reason": (
                f"Intensitas hujan ({ra:.1f} mm/min) mendekati batas jenuh infiltrasi ({ir:.4f} mm/s). "
                f"Topsoil 10cm: {sm_10:.1f}%."
            ),
            "metrics": {"ra": ra, "ir": ir, "sm_10": sm_10, "h": h}
        })

    # 2. Shallow Landslide Alert (Pore Water Pressure & Shear Failure)
    # Condition: Prolonged infiltration saturating deep slip layers (30-40 cm)
    if sm_30 >= 90.0 and sm_40 >= 90.0:
        alerts.append({
            "station_id": station_id,
            "alert_type": "landslide",
            "severity": "CRITICAL",
            "title": "AWAS: Potensi Longsor Dangkal",
            "trigger_reason": (
                f"Lapisan tanah dalam (30cm: {sm_30:.1f}%, 40cm: {sm_40:.1f}%) jenuh air penuh. "
                f"Tekanan air pori positif meningkat kritis dan mengikis kuat geser tanah."
            ),
            "metrics": {"sm_30": sm_30, "sm_40": sm_40, "ra": ra}
        })
    elif sm_30 >= 80.0 and sm_40 >= 80.0:
        alerts.append({
            "station_id": station_id,
            "alert_type": "landslide",
            "severity": "WARNING",
            "title": "WASPADA: Penjenuhan Lapisan Tanah Bawah",
            "trigger_reason": (
                f"Wetting front telah menembus horizon 30-40cm (30cm: {sm_30:.1f}%, 40cm: {sm_40:.1f}%)."
            ),
            "metrics": {"sm_30": sm_30, "sm_40": sm_40, "ra": ra}
        })

    # 3. Agricultural Drought Alert (Soil Water Deficit Index)
    # Condition: Average profile moisture depleted below permanent wilting point (PWP ~15%)
    if sm_avg <= 15.0 and ra == 0.0:
        alerts.append({
            "station_id": station_id,
            "alert_type": "drought",
            "severity": "WARNING",
            "title": "WASPADA: Kekeringan Agrikultur",
            "trigger_reason": (
                f"Rerata kelembaban tanah 0-40cm ({sm_avg:.1f}%) berada di bawah Titik Layu Permanen (PWP). "
                f"Defisit air tanah tinggi."
            ),
            "metrics": {"sm_avg": sm_avg, "ra": ra}
        })

    # 4. Hardware Health Alert (Battery Drop)
    if pvolt < 11.8:
        alerts.append({
            "station_id": station_id,
            "alert_type": "hardware_health",
            "severity": "WARNING",
            "title": "PERHATIAN: Tegangan Baterai Kritis",
            "trigger_reason": f"Tegangan aki turun ke {pvolt:.2f} V. Risiko pemadaman gateway 4G.",
            "metrics": {"pvolt": pvolt}
        })

    return alerts
