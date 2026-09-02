"""Real German day-ahead electricity prices (EUR/MWh), sourced from SMARD.de
(Bundesnetzagentur's market transparency platform, public API, filter 4169 -
"Großhandelspreise Deutschland/Luxemburg", quarter-hourly data averaged to
hourly). Fetched 2026-09-02 for three days from the preceding weeks, chosen
to show genuinely different market conditions - not cherry-picked for a
dramatic story, just representative of what actually happened on the German
day-ahead market recently.
"""

# Hour 0 = first hour of the day; no timezone claim is made beyond that.
PRICE_PRESETS = {
    "Volatiler Tag (13.08.2026)": [
        143.42, 142.72, 144.92, 157.40, 174.23, 171.10, 156.80, 135.65,
        109.59, 51.73, 2.81, 0.00, 2.52, 44.44, 111.48, 150.01,
        204.00, 326.60, 338.86, 270.01, 213.48, 176.17, 158.87, 151.86,
    ],
    "Negative Preise (08.08.2026)": [
        145.24, 145.92, 143.87, 145.69, 146.26, 137.70, 115.03, 62.55,
        3.86, -1.52, -5.99, -11.00, -12.15, -7.01, -0.56, 68.16,
        140.00, 167.87, 184.66, 179.50, 170.85, 154.42, 145.27, 139.34,
    ],
    "Ruhiger Tag (17.08.2026)": [
        163.90, 160.28, 159.07, 174.97, 197.40, 205.15, 208.61, 198.79,
        175.49, 166.97, 154.28, 150.19, 141.30, 139.88, 140.09, 152.02,
        177.10, 204.10, 213.40, 210.00, 197.71, 179.92, 173.57, 159.79,
    ],
}

DEFAULT_PRESET = "Volatiler Tag (13.08.2026)"

# A representative small home/commercial battery.
DEFAULT_CAPACITY_KWH = 10.0
DEFAULT_MAX_RATE_KW = 5.0
DEFAULT_EFFICIENCY = 0.90  # round-trip efficiency (charge and discharge combined)
DEFAULT_START_SOC_FRACTION = 0.5  # battery starts half-full
