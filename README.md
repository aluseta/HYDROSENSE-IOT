# HydroSense‑IoT Project Overview

## Objective
Develop an **automated edge-to-cloud hydro-meteorological monitoring and early warning system (EWS)** (HydroSense‑IoT) for flood-prone watersheds, quantifying surface water partitioning and subsurface saturation dynamics across multiple urban sites.

---

## Deliverables & Technical Scope

### 1. Hardware Architecture & Instrumentation
- **Datalogger & Controller**: Custom PenaAWS datalogger / industrial NEMA/IP65 enclosure.
- **Power System**: 50W Solar Panel + upgraded **15–20 Ah LiFePO₄** (or 18–26 Ah VRLA) battery storage for 2–3 day autonomy.
- **Gateway & Telemetry**: Teltonika cellular gateway (RUT955) transmitting telemetry over MQTT at 1-minute intervals.
- **Integrated Sensors**:
  1. **DAVIS Tipping-bucket rain gauge**: High-precision precipitation measurement (`RA`).
  2. **DFRobot RS485 Modbus-RTU IP68 Soil Sensors (SEN0600)**: 4 vertical tiers at depths **10 cm, 20 cm, 30 cm, and 40 cm**, measuring Volumetric Water Content (`SM`) and Soil Temperature (`ST`).
  3. **Concentric ASTM D3385 Double-Ring Infiltrometer** (30 cm inner & 60 cm outer ring) + **Vertical Magnetic Water Level Float Sensor**: Measures ponding depth ($H$) with a 3–5 cm overflow weir to avoid artificial hydrostatic pooling.

### 2. Analytical & Hydrological Formulation
- **Surface Mass-Balance Infiltration**:
  $$f(t) = I(t) - \frac{\Delta H}{\Delta t}$$
  - **Pre-ponding ($H = 0$)**: $f(t) = I(t)$ (all precipitation is absorbed).
  - **Active ponding ($H > 0$)**: $f(t) = I(t) - \Delta H/\Delta t$.
  - **Post-rainfall with standing water ($I = 0, H > 0$)**: $f(t) = -\frac{\Delta H}{\Delta t} = K_s$ (in-situ saturated hydraulic conductivity).
- **Horton Baseline Formulation (from ASTM D3385 field survey)**:
  $$f(t) = f_c + (f_0 - f_c) \cdot e^{-k t}$$
  Where $f_0$ is initial infiltration capacity, $f_c \equiv K_s$ is ultimate steady-state capacity, and $k$ is the decay constant.

---

## MQTT Telemetry Schema

Structured JSON payload published to `hydrosense/<station_id>/telemetry`:

```json
{
  "station_id": "HS-CTM-01",
  "timestamp": 1729415500,
  "system": {
    "ptemp": 29.4,        // Panel temperature (°C)
    "pvolt": 12.82        // Panel battery voltage (V)
  },
  "hydro": {
    "ra": 0.0,            // Rain accumulation (mm/min)
    "h": 0.0,             // Infiltrometer ponding depth (mm)
    "ir": 0.024           // Infiltration rate (mm/s)
  },
  "soil": {
    "depths_cm": [10, 20, 30, 40],
    "sm": [38.2, 34.1, 28.5, 21.0],  // Volumetric Water Content (%)
    "st": [26.5, 25.8, 25.2, 24.9]   // Soil Temperature (°C)
  }
}
```

---

## Dashboard UI/UX Specification

The production dashboard utilizes a **two-page navigation structure**:

### Page 1: 📡 Dashboard Utama (Real-Time Command Center)
- **Top Bar**: Station switcher (`DAS Citarum Hulu`, `Jatinangor`, `Garut`), live MQTT heartbeat, scenario simulator buttons (Normal, Banjir Hortonian, Longsor, Kemarau).
- **KPI Summary Row**:
  - `PVolt` (Aki status, radial/fill bar)
  - `PTemp` (Suhu panel, batas aman 50°C)
  - `RA` (Curah hujan sesaat & 24 jam)
  - `H` (Ketinggian genangan di ring)
  - `IR` (Laju infiltrasi $f(t)$ + indikator fase)
  - `EWS Status Badge` (Normal, Waspada, Awas)
- **Unified Main Grid**:
  - **Left 40% — Profil Tanah Gabungan (SM & ST)**:
    - Sumbu Y vertikal: Kedalaman tanah ($0\text{ cm}$ permukaan $\to$ $-40\text{ cm}$ bawah).
    - Sumbu X bawah (Biru): Kelembaban tanah `SM` ($0 - 100\%$) dengan isian area gradien.
    - Sumbu X atas (Oranye): Suhu tanah `ST` (°C).
    - Garis batas referensi: Titik Layu Permanen ($15\%$) dan Saturasi Kritis ($90\%$).
  - **Right 60% — Hujan (RA) & Laju Infiltrasi f(t)**:
    - Hyetograph terbalik di atas (batang hujan biru menggantung dari atas).
    - Kurva $f(t)$ real-time dari sensor (garis teal solid).
    - Overlay **Kurva Horton Baseline** (garis putus abu-abu) dari hasil survey lapangan.
    - Area arsiran merah otomatis menandai terjadinya **Limpasan Permukaan / Runoff** ($I > f$).
    - Indikator posisi $K_s$ survey vs $K_s$ real-time dan selisih pergeseran (*drift*).
- **Bottom Section — Matriks EWS**:
  - 🌊 **Banjir Bandang (Hortonian Runoff)**: Terpicu saat $RA \gg f(t)$ dan $SM_{10\text{cm}} > 90\%$.
  - ⛰️ **Longsor Dangkal**: Terpicu saat $SM_{30\text{cm}}$ & $SM_{40\text{cm}} \to 100\%$ (akumulasi tekanan air pori).
  - 🌾 **Kekeringan Agrikultur (SMDI)**: Terpicu saat seluruh profil $SM < \text{PWP}$ dan $RA = 0$ berkepanjangan.

### Page 2: 🔬 Survey & Fitting Horton
- **Data Entry Table**: Input interaktif pasangan data waktu uji ($t$ menit) dan laju infiltrasi terukur ($f$ mm/min) dari pengujian double-ring infiltrometer lapangan.
- **Fitting Engine**: Menghitung parameter Horton ($f_0$, $f_c = K_s$, $k$) dan koefisien determinasi $R^2$ secara otomatis.
- **Preview Chart**: Plot titik data aktual vs kurva fitting eksponensial Horton.
- **Action**: Tombol *"Terapkan sebagai Baseline ke Dashboard Utama"* untuk langsung memperbarui kurva acuan tanpa restart server.

---

## Partners & Responsibilities

| Partner | Tanggung Jawab Utama |
|---|---|
| **ITB** (Institut Teknologi Bandung) | Desain hidrologi & riset, firmware, algoritma EWS, pemodelan Horton, infrastruktur cloud & database |
| **PT MANVIS** | Fabrikasi hardware/PCB, penyediaan perangkat pengaman & sensor industri, perizinan lokasi, pengujian pasar |

---

## Files & Artifacts Reference
- `dashboard_final.html`: Mockup interaktif final dua halaman (Dashboard Utama + Survey Horton).
- `Rapat Mitra MANVIS HydroSense-IoT (6-10-2026).pptx`: Dokumen notulen rapat kerja sama awal.
