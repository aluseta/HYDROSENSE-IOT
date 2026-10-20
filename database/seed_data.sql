-- ====================================================================
-- HYDROSENSE-IOT: Seed Data for Initial 3 Stations & Baseline Surveys
-- ====================================================================

INSERT INTO stations (id, name, basin_name, latitude, longitude, soil_texture, description)
VALUES 
    ('HS-CTM-01', 'DAS Citarum Hulu Stasiun 01', 'DAS Citarum', -7.0345, 107.7123, 'Sandy Clay Loam', 'Titik survei infiltrasi Citarum Hulu (26-27 Sep 2026). Rawan banjir genangan.'),
    ('HS-JTG-02', 'DAS Jatinangor Stasiun 02', 'DAS Cikeruh / Cimanuk', -6.9288, 107.7715, 'Clay Loam', 'Area lereng kampus ITB Jatinangor. Pemantauan perambatan air pori & lereng.'),
    ('HS-GRT-03', 'DAS Garut Stasiun 03', 'DAS Cimanuk Hulu', -7.2140, 107.9021, 'Volcanic Ash / Silty Loam', 'DAS hulu Garut rawan limpasan permukaan tinggi.')
ON CONFLICT (id) DO NOTHING;

-- Initial Horton baseline survey for HS-CTM-01 (surveyed 27 Sep 2026)
INSERT INTO horton_baselines (station_id, f0, fc, k, r_squared, survey_date, raw_survey_json, is_active)
VALUES (
    'HS-CTM-01',
    8.50,          -- Initial rate f0 = 8.50 mm/min
    0.96,          -- Saturated rate fc = 0.96 mm/min (Ks)
    0.082,         -- Decay constant k = 0.082 min^-1
    0.984,         -- R^2
    '2026-09-27',
    '[
        {"t": 0, "f": 8.5},
        {"t": 5, "f": 6.2},
        {"t": 10, "f": 4.8},
        {"t": 15, "f": 3.6},
        {"t": 20, "f": 2.9},
        {"t": 30, "f": 2.1},
        {"t": 45, "f": 1.4},
        {"t": 60, "f": 1.1},
        {"t": 90, "f": 0.98},
        {"t": 120, "f": 0.96}
    ]'::jsonb,
    TRUE
);

-- Baseline for HS-JTG-02 (Clay Loam)
INSERT INTO horton_baselines (station_id, f0, fc, k, r_squared, survey_date, is_active)
VALUES (
    'HS-JTG-02',
    6.20,
    0.54,
    0.065,
    0.978,
    '2026-10-01',
    TRUE
);

-- Baseline for HS-GRT-03 (Volcanic Ash)
INSERT INTO horton_baselines (station_id, f0, fc, k, r_squared, survey_date, is_active)
VALUES (
    'HS-GRT-03',
    11.40,
    1.45,
    0.095,
    0.989,
    '2026-10-03',
    TRUE
);
