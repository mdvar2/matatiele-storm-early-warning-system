from pathlib import Path
from datetime import datetime, UTC
import os
import tempfile
import argparse

import joblib
import numpy as np
import pandas as pd
import requests
from forecast_timing import model_input_hour
from cape_normalisation import normalise_cape

parser = argparse.ArgumentParser(description='Genuine ECMWF / Random Forest inference; no SMS.')
parser.add_argument('--dashboard-next-hour', action='store_true',
                    help='Predict the next complete hourly interval using its genuine forecast input row; save separately from the SMS worker result.')
args = parser.parse_args()


# ============================================================
# LIVE FORECAST -> LIVE-COMPATIBLE RANDOM FOREST
# ============================================================

BASE_DIR = Path(__file__).resolve().parent

MODEL_DIR = BASE_DIR / "outputs" / "model_live"

MODEL_FILE = MODEL_DIR / "random_forest_live_model.pkl"
FEATURE_FILE = MODEL_DIR / "live_model_features.txt"
THRESHOLD_FILE = MODEL_DIR / "live_selected_threshold.txt"

OUTPUT_FILE = MODEL_DIR / ("dashboard_forecast_prediction.csv" if args.dashboard_next_hour
                           else "live_forecast_prediction.csv")


# ============================================================
# LOCATION
# ============================================================

TARGET_LATITUDE = -30.30
TARGET_LONGITUDE = 28.80

# Keep latitude / longitude close to the ERA5 training grid.
MODEL_LATITUDE = -30.25
MODEL_LONGITUDE = 28.75


# ============================================================
# OPEN-METEO ECMWF API
# ============================================================

API_URL = "https://api.open-meteo.com/v1/ecmwf"


print("=" * 70)
print("LIVE STORM PREDICTION SYSTEM")
print("=" * 70)


# ============================================================
# 1. CHECK MODEL FILES
# ============================================================

print("\nChecking live-compatible model files...")

required_files = [
    MODEL_FILE,
    FEATURE_FILE,
    THRESHOLD_FILE
]

for file in required_files:

    if not file.exists():
        raise FileNotFoundError(
            f"Required file not found:\n{file}"
        )

print("All live-compatible model files found.")


# ============================================================
# 2. LOAD MODEL
# ============================================================

print("\nLoading live-compatible Random Forest...")

model = joblib.load(MODEL_FILE)

print("Random Forest loaded successfully.")


# ============================================================
# 3. LOAD FEATURES
# ============================================================

with open(
    FEATURE_FILE,
    "r",
    encoding="utf-8"
) as file:

    features = [
        line.strip()
        for line in file
        if line.strip()
    ]


print(
    f"Model expects {len(features)} features."
)


# ============================================================
# 4. LOAD THRESHOLD
# ============================================================

with open(
    THRESHOLD_FILE,
    "r",
    encoding="utf-8"
) as file:

    threshold = float(
        file.read().strip()
    )


print(
    f"Storm decision threshold: "
    f"{threshold:.2f}"
)



# ============================================================
# 5. REQUEST LIVE FORECAST
# ============================================================

print(
    "\nRequesting live ECMWF forecast "
    "from Open-Meteo..."
)

hourly_variables = [
    "temperature_2m",
    "dew_point_2m",
    "pressure_msl",
    "surface_pressure",
    "precipitation",
    "showers",
    "cape",
    "cloud_cover",
    "wind_speed_10m",
    "wind_direction_10m",
    "wind_gusts_10m"
]

params = {
    "latitude": TARGET_LATITUDE,
    "longitude": TARGET_LONGITUDE,
    "hourly": ",".join(hourly_variables),
    "timezone": "UTC",
    "wind_speed_unit": "ms",
    "precipitation_unit": "mm",
    "past_days": 1,
    "forecast_days": 2
}

try:
    print("Request URL:", API_URL)
    print("Requested variables:", hourly_variables)

    response = requests.get(
        API_URL,
        params=params,
        timeout=(15, 120)
    )

    print("HTTP status:", response.status_code)

    response.raise_for_status()

except requests.RequestException as error:
    print("\nLive forecast request failed.")
    print(error)
    raise SystemExit(1)

data = response.json()
retrieved_at_utc = datetime.now(UTC).isoformat()

if data.get("error"):
    raise ValueError(
        f"Open-Meteo error: {data.get('reason')}"
    )

print("Live forecast downloaded successfully.")


# ============================================================
# 6. VALIDATE RESPONSE
# ============================================================

if "hourly" not in data:
    raise ValueError(
        "No hourly forecast data was returned."
    )

hourly = data["hourly"]

required_api_fields = [
    "time",
    "temperature_2m",
    "dew_point_2m",
    "pressure_msl",
    "surface_pressure",
    "precipitation",
    "showers",
    "cape",
    "cloud_cover",
    "wind_speed_10m",
    "wind_direction_10m",
    "wind_gusts_10m"
]

missing_api_fields = [
    field
    for field in required_api_fields
    if field not in hourly
]

if missing_api_fields:
    raise ValueError(
        "Open-Meteo response is missing:\n"
        f"{missing_api_fields}"
    )

# ============================================================
# 7. CONVERT TO DATAFRAME
# ============================================================

forecast = pd.DataFrame(
    hourly
)


forecast["valid_time"] = pd.to_datetime(
    forecast["time"],
    errors="coerce",
    utc=True
)


forecast = forecast.drop(
    columns=["time"]
)


forecast = forecast.sort_values(
    "valid_time"
).reset_index(drop=True)


print(
    f"\nForecast rows received: "
    f"{len(forecast):,}"
)


# ============================================================
# 8. CONVERT TO TRAINING UNITS
# ============================================================

# Celsius -> Kelvin
forecast["t2m"] = (
    forecast["temperature_2m"]
    +
    273.15
)


forecast["d2m"] = (
    forecast["dew_point_2m"]
    +
    273.15
)


# hPa -> Pa
forecast["msl"] = (
    forecast["pressure_msl"]
    *
    100
)


forecast["sp"] = (
    forecast["surface_pressure"]
    *
    100
)


# mm -> metres
forecast["tp"] = (
    forecast["precipitation"]
    /
    1000
)


# Closest substitute for convective precipitation
forecast["cp"] = (
    forecast["showers"]
    /
    1000
)


# Cloud percentage -> fraction
forecast["tcc"] = (
    forecast["cloud_cover"]
    /
    100
)


# Wind gust already requested in m/s
forecast["i10fg"] = (
    forecast["wind_gusts_10m"]
)


# ============================================================
# 9. CONVERT WIND SPEED / DIRECTION TO U / V
# ============================================================

direction_radians = np.radians(
    forecast["wind_direction_10m"]
)


forecast["u10"] = (

    -forecast["wind_speed_10m"]

    *

    np.sin(
        direction_radians
    )
)


forecast["v10"] = (

    -forecast["wind_speed_10m"]

    *

    np.cos(
        direction_radians
    )
)


forecast["wind_speed"] = np.sqrt(

    forecast["u10"] ** 2

    +

    forecast["v10"] ** 2
)


# ============================================================
# 10. CHECK LIVE DATA
# ============================================================

weather_columns = [

    "valid_time",

    "t2m",
    "d2m",

    "msl",
    "sp",

    "tp",
    "cape",
    "cp",
    "tcc",

    "u10",
    "v10",
    "i10fg",

    "wind_speed"
]


print("\n" + "=" * 70)
print("LIVE VARIABLE AVAILABILITY")
print("=" * 70)


print(
    "\nMissing values:"
)


print(
    forecast[
        weather_columns
    ]
    .isna()
    .sum()
)


# ============================================================
# 11. IDENTIFY REQUIRED NUMERIC INPUTS
# ============================================================

numeric_columns = [

    "t2m",
    "d2m",

    "msl",
    "sp",

    "tp",
    "cape",
    "cp",
    "tcc",

    "u10",
    "v10",
    "i10fg",

    "wind_speed"
]


# Missing meteorological inputs are never imputed. Require genuine values
# for the current and previous hour; otherwise keep the saved prediction.

# ============================================================
# 12. REMOVE INCOMPLETE ROWS
# ============================================================

forecast = forecast.dropna(
    subset=weather_columns
).copy()


if forecast.empty:

    raise ValueError(
        "No complete live forecast observations "
        "are available."
    )


print(
    f"\nComplete forecast rows: "
    f"{len(forecast):,}"
)


# ============================================================
# 13. FIND CURRENT FORECAST HOUR
# ============================================================

now_utc = datetime.now(UTC)


current_hour = model_input_hour(now_utc, next_complete=args.dashboard_next_hour)


available_current = forecast[

    forecast["valid_time"]

    ==

    current_hour

]


if available_current.empty:

    raise ValueError(
        "The selected forecast input hour is unavailable; no earlier row is substituted."
    )


latest = (
    available_current
    .iloc[-1]
)


latest_time = (
    latest["valid_time"]
)


if latest_time != current_hour:
    raise ValueError("Selected-hour ECMWF inputs are incomplete or unavailable.")


# ============================================================
# 14. FIND PREVIOUS HOUR
# ============================================================

previous_time = (

    latest_time

    -

    pd.Timedelta(hours=1)

)


previous_rows = forecast[

    forecast["valid_time"]

    ==

    previous_time

]


if previous_rows.empty:

    raise ValueError(
        f"No previous-hour forecast found "
        f"for {previous_time}."
    )


previous = (
    previous_rows.iloc[0]
)


# ============================================================
# 14b. NORMALISE SMALL NEGATIVE CAPE (interpolation artefact)
# ============================================================
# Finite CAPE in [-50, 0) J/kg becomes 0 for both model inputs; anything else
# invalid is passed through unchanged and rejected by the SMS worker.
latest = latest.copy()
previous = previous.copy()
cape_raw, cape_status = latest["cape"], None
previous_cape_raw, previous_cape_status = previous["cape"], None
value, cape_status = normalise_cape(cape_raw)
if value is not None:
    latest["cape"] = value
value, previous_cape_status = normalise_cape(previous_cape_raw)
if value is not None:
    previous["cape"] = value
print(f"\nCAPE normalisation: current={cape_status} (raw {cape_raw}), "
      f"previous={previous_cape_status} (raw {previous_cape_raw})")


# ============================================================
# 15. TIME FEATURES
# ============================================================

hour = latest_time.hour
month = latest_time.month
day_of_year = latest_time.dayofyear


# ============================================================
# 16. BUILD EXACT 29-FEATURE INPUT
# ============================================================

prediction_data = {

    "latitude":
        MODEL_LATITUDE,

    "longitude":
        MODEL_LONGITUDE,

    "t2m":
        latest["t2m"],

    "d2m":
        latest["d2m"],

    "msl":
        latest["msl"],

    "sp":
        latest["sp"],

    "tp":
        latest["tp"],

    "cape":
        latest["cape"],

    "cp":
        latest["cp"],

    "tcc":
        latest["tcc"],

    "u10":
        latest["u10"],

    "v10":
        latest["v10"],

    "i10fg":
        latest["i10fg"],

    "hour":
        hour,

    "month":
        month,

    "day_of_year":
        day_of_year,

    "wind_speed":
        latest["wind_speed"],

    "previous_t2m":
        previous["t2m"],

    "previous_d2m":
        previous["d2m"],

    "previous_msl":
        previous["msl"],

    "previous_sp":
        previous["sp"],

    "previous_tp":
        previous["tp"],

    "previous_cape":
        previous["cape"],

    "previous_cp":
        previous["cp"],

    "previous_tcc":
        previous["tcc"],

    "previous_u10":
        previous["u10"],

    "previous_v10":
        previous["v10"],

    "previous_i10fg":
        previous["i10fg"],

    "previous_wind_speed":
        previous["wind_speed"]
}


prediction_df = pd.DataFrame(
    [prediction_data]
)


# ============================================================
# 17. CHECK FEATURE COMPATIBILITY
# ============================================================

missing_model_features = [

    feature

    for feature in features

    if feature not in prediction_df.columns
]


if missing_model_features:

    raise ValueError(
        f"Prediction input is missing features:\n"
        f"{missing_model_features}"
    )


if len(features) != 29 or int(model.n_features_in_) != 29:
    raise ValueError("Expected the existing 29-feature Random Forest.")
if list(model.feature_names_in_) != features:
    raise ValueError("The feature list does not match the trained model order.")
if not np.isclose(threshold, 0.35):
    raise ValueError("This research system requires the selected 35% threshold.")

prediction_df = (
    prediction_df[
        features
    ]
)


print(
    f"\nFeatures prepared for model: "
    f"{len(prediction_df.columns)}"
)


# ============================================================
# 18. MAKE PREDICTION
# ============================================================

if not np.isfinite(prediction_df.to_numpy(dtype=float)).all():
    raise ValueError("Nonfinite model input; prediction was not updated.")

storm_probability = (

    model.predict_proba(
        prediction_df
    )[0][1]

)


# Actual inference completion time, distinct from API retrieval and forecast validity.
prediction_generated_at = datetime.now(UTC).isoformat()

storm_prediction = int(

    storm_probability

    >=

    threshold

)


if storm_prediction == 1:

    warning_status = (
        "STORM WARNING"
    )

else:

    warning_status = (
        "NO STORM"
    )


# ============================================================
# 19. DISPLAY LIVE CONDITIONS
# ============================================================

print("\n" + "=" * 70)
print("LIVE ECMWF FORECAST INPUT")
print("=" * 70)


print(
    f"\nForecast input time : "
    f"{latest_time}"
)


print(
    f"Prediction for      : "
    f"{latest_time + pd.Timedelta(hours=1)}"
)


print(
    f"Location            : "
    f"{TARGET_LATITUDE}, "
    f"{TARGET_LONGITUDE}"
)


print("\nForecast conditions:")


print(
    f"Temperature      : "
    f"{latest['t2m'] - 273.15:.2f} °C"
)


print(
    f"Dew point        : "
    f"{latest['d2m'] - 273.15:.2f} °C"
)


print(
    f"MSL pressure     : "
    f"{latest['msl'] / 100:.2f} hPa"
)


print(
    f"Surface pressure : "
    f"{latest['sp'] / 100:.2f} hPa"
)


print(
    f"Precipitation    : "
    f"{latest['tp'] * 1000:.3f} mm"
)


print(
    f"Showers / CP     : "
    f"{latest['cp'] * 1000:.3f} mm"
)


print(
    f"CAPE             : "
    f"{latest['cape']:.2f} J/kg"
)


print(
    f"Cloud cover      : "
    f"{latest['tcc'] * 100:.1f}%"
)


print(
    f"Wind speed       : "
    f"{latest['wind_speed']:.2f} m/s"
)


print(
    f"Wind gust        : "
    f"{latest['i10fg']:.2f} m/s"
)


# ============================================================
# 20. DISPLAY PREDICTION
# ============================================================

print("\n" + "=" * 70)
print("LIVE NEXT-HOUR STORM PREDICTION")
print("=" * 70)


print(
    f"\nStorm probability : "
    f"{storm_probability * 100:.2f}%"
)


print(
    f"Decision threshold: "
    f"{threshold * 100:.0f}%"
)


print(
    f"\nPrediction: "
    f"{warning_status}"
)


if storm_prediction == 1:

    print(
        "\nWARNING:"
    )

    print(
        "The live-compatible Random Forest "
        "predicts storm conditions during "
        "the next hour."
    )

else:

    print(
        "\nThe live-compatible Random Forest "
        "predicts no storm during the next hour."
    )


# ============================================================
# 21. SAVE RESULT
# ============================================================

result = {

    "forecast_source":
        "Open-Meteo ECMWF",

    "forecast_retrieved_at": retrieved_at_utc,
    "prediction_generated_at": prediction_generated_at,
    "forecast_selection": "next_complete_hour" if args.dashboard_next_hour else "current_hour",
    # Existing t+1 target is unchanged; precipitation at t+1 covers (t, t+1].
    "target_interval_start": latest_time,
    "target_interval_end": latest_time + pd.Timedelta(hours=1),
    "forecast_issue_time": "",  # API response does not provide a run issue timestamp.

    "forecast_input_time":
        latest_time,

    "prediction_for":
        latest_time
        +
        pd.Timedelta(hours=1),

    "latitude":
        TARGET_LATITUDE,

    "longitude":
        TARGET_LONGITUDE,

    "storm_probability":
        storm_probability,

    "decision_threshold":
        threshold,

    "storm_prediction":
        storm_prediction,

    "warning_status":
        warning_status,

    "temperature_c":
        latest["t2m"]
        -
        273.15,

    "dewpoint_c":
        latest["d2m"]
        -
        273.15,

    "pressure_msl_hpa":
        latest["msl"]
        /
        100,

    "surface_pressure_hpa":
        latest["sp"]
        /
        100,

    "precipitation_mm":
        latest["tp"]
        *
        1000,

    "showers_mm":
        latest["cp"]
        *
        1000,

    "cape":
        latest["cape"],

    "cape_raw":
        cape_raw,

    "cape_normalisation":
        cape_status,

    "previous_cape":
        previous["cape"],

    "previous_cape_raw":
        previous_cape_raw,

    "previous_cape_normalisation":
        previous_cape_status,

    "cloud_cover_percent":
        latest["tcc"]
        *
        100,

    "wind_speed_ms":
        latest["wind_speed"],

    "wind_gust_ms":
        latest["i10fg"]
}


# Atomically replace only after successful inference; readers keep the old CSV
# if a request, validation or write fails.
with tempfile.NamedTemporaryFile(mode="w", suffix=".csv", dir=MODEL_DIR,
                                 encoding="utf-8", newline="", delete=False) as handle:
    temporary_prediction = Path(handle.name)
    try:
        pd.DataFrame([result]).to_csv(handle,index=False)
    except Exception:
        handle.close()
        temporary_prediction.unlink(missing_ok=True)
        raise
try:
    os.replace(temporary_prediction,OUTPUT_FILE)
finally:
    temporary_prediction.unlink(missing_ok=True)


print("\nPrediction saved to:")
print(OUTPUT_FILE)


print("\n" + "=" * 70)
print("LIVE PREDICTION COMPLETE")
print("=" * 70)
