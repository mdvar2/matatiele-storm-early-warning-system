import pandas as pd
import numpy as np
import joblib
from pathlib import Path


# ============================================================
# RANDOM FOREST AUTOMATED STORM PREDICTION
# ============================================================

BASE_DIR = Path(__file__).resolve().parent

OUTPUT_DIR = BASE_DIR / "outputs"

DATA_FILE = OUTPUT_DIR / "era5_merged.csv"
MODEL_FILE = OUTPUT_DIR / "model" / "random_forest_storm_model.pkl"
FEATURE_FILE = OUTPUT_DIR / "model" / "model_features.txt"
THRESHOLD_FILE = OUTPUT_DIR / "model" / "selected_threshold.txt"


print("=" * 60)
print("RANDOM FOREST AUTOMATED STORM PREDICTION")
print("=" * 60)


# ------------------------------------------------------------
# 1. Check required files
# ------------------------------------------------------------

print("\nChecking required files...")

required_files = [
    DATA_FILE,
    MODEL_FILE,
    FEATURE_FILE,
    THRESHOLD_FILE
]

for file in required_files:
    if not file.exists():
        raise FileNotFoundError(
            f"\nRequired file not found:\n{file}"
        )

print("All required files found.")


# ------------------------------------------------------------
# 2. Load trained Random Forest
# ------------------------------------------------------------

print("\nLoading trained Random Forest...")

model = joblib.load(MODEL_FILE)

print("Model loaded successfully.")


# ------------------------------------------------------------
# 3. Load model features
# ------------------------------------------------------------

with open(FEATURE_FILE, "r") as file:
    features = [
        line.strip()
        for line in file
        if line.strip()
    ]

print(f"\nNumber of model features: {len(features)}")


# ------------------------------------------------------------
# 4. Load selected threshold
# ------------------------------------------------------------

with open(THRESHOLD_FILE, "r") as file:
    threshold = float(file.read().strip())

print(f"Selected storm threshold: {threshold:.2f}")


# ------------------------------------------------------------
# 5. Read ERA5 merged dataset
# ------------------------------------------------------------

print("\nReading ERA5 weather data...")

df = pd.read_csv(DATA_FILE)

print(f"Input rows: {len(df):,}")
print(f"Input columns: {len(df.columns)}")


# ------------------------------------------------------------
# 6. Convert time column
# ------------------------------------------------------------

df["valid_time"] = pd.to_datetime(
    df["valid_time"],
    errors="coerce"
)


# ------------------------------------------------------------
# 7. Sort observations
# ------------------------------------------------------------

df = df.sort_values(
    ["latitude", "longitude", "valid_time"]
).reset_index(drop=True)


# ------------------------------------------------------------
# 8. Check required weather variables
# ------------------------------------------------------------

weather_columns = [
    "latitude",
    "longitude",
    "t2m",
    "d2m",
    "msl",
    "sp",
    "tp",
    "cape",
    "cp",
    "kx",
    "tcc",
    "u10",
    "v10",
    "i10fg"
]

missing_columns = [
    column
    for column in weather_columns
    if column not in df.columns
]

if missing_columns:
    raise ValueError(
        f"\nMissing required ERA5 columns:\n{missing_columns}"
    )


# ------------------------------------------------------------
# 9. Find latest complete observation
# ------------------------------------------------------------

df_complete = df.dropna(
    subset=weather_columns
).copy()

if df_complete.empty:
    raise ValueError(
        "No complete ERA5 observations are available."
    )


latest = df_complete.iloc[-1]


latest_time = latest["valid_time"]
latest_latitude = latest["latitude"]
latest_longitude = latest["longitude"]


print("\n" + "=" * 60)
print("LATEST ERA5 OBSERVATION")
print("=" * 60)

print(f"\nTime      : {latest_time}")
print(f"Latitude  : {latest_latitude}")
print(f"Longitude : {latest_longitude}")


# ------------------------------------------------------------
# 10. Find previous-hour observation
# ------------------------------------------------------------

previous_time = latest_time - pd.Timedelta(hours=1)

previous_matches = df[
    (df["latitude"] == latest_latitude)
    &
    (df["longitude"] == latest_longitude)
    &
    (df["valid_time"] == previous_time)
]

previous_matches = previous_matches.dropna(
    subset=weather_columns
)

if previous_matches.empty:

    print("\nWARNING:")
    print(
        "Previous-hour observation was not found."
    )

    print(
        "The model requires previous-hour features."
    )

    raise ValueError(
        f"No complete previous-hour observation found "
        f"for {previous_time}."
    )


previous = previous_matches.iloc[0]


# ------------------------------------------------------------
# 11. Calculate current wind speed
# ------------------------------------------------------------

wind_speed = np.sqrt(
    latest["u10"] ** 2 +
    latest["v10"] ** 2
)


# ------------------------------------------------------------
# 12. Calculate previous-hour wind speed
# ------------------------------------------------------------

previous_wind_speed = np.sqrt(
    previous["u10"] ** 2 +
    previous["v10"] ** 2
)


# ------------------------------------------------------------
# 13. Create time features
# ------------------------------------------------------------

hour = latest_time.hour

month = latest_time.month

day_of_year = latest_time.dayofyear


# ------------------------------------------------------------
# 14. Create model input
# ------------------------------------------------------------

prediction_data = {

    # Location
    "latitude": latest["latitude"],
    "longitude": latest["longitude"],

    # Current weather
    "t2m": latest["t2m"],
    "d2m": latest["d2m"],
    "msl": latest["msl"],
    "sp": latest["sp"],
    "tp": latest["tp"],
    "cape": latest["cape"],
    "cp": latest["cp"],
    "kx": latest["kx"],
    "tcc": latest["tcc"],
    "u10": latest["u10"],
    "v10": latest["v10"],
    "i10fg": latest["i10fg"],

    # Time
    "hour": hour,
    "month": month,
    "day_of_year": day_of_year,

    # Current wind speed
    "wind_speed": wind_speed,

    # Previous-hour weather
    "previous_t2m": previous["t2m"],
    "previous_d2m": previous["d2m"],
    "previous_msl": previous["msl"],
    "previous_sp": previous["sp"],
    "previous_tp": previous["tp"],
    "previous_cape": previous["cape"],
    "previous_cp": previous["cp"],
    "previous_kx": previous["kx"],
    "previous_tcc": previous["tcc"],
    "previous_u10": previous["u10"],
    "previous_v10": previous["v10"],
    "previous_i10fg": previous["i10fg"],

    # Previous wind speed
    "previous_wind_speed": previous_wind_speed
}


prediction_df = pd.DataFrame(
    [prediction_data]
)


# ------------------------------------------------------------
# 15. Verify all model features exist
# ------------------------------------------------------------

missing_features = [
    feature
    for feature in features
    if feature not in prediction_df.columns
]

if missing_features:
    raise ValueError(
        f"\nMissing model features:\n{missing_features}"
    )


# ------------------------------------------------------------
# 16. Arrange features in exact training order
# ------------------------------------------------------------

prediction_df = prediction_df[features]


# ------------------------------------------------------------
# 17. Check for missing values
# ------------------------------------------------------------

if prediction_df.isna().any().any():

    missing = prediction_df.columns[
        prediction_df.isna().any()
    ].tolist()

    raise ValueError(
        f"\nMissing values found in model input:\n{missing}"
    )


# ------------------------------------------------------------
# 18. Make prediction
# ------------------------------------------------------------

print("\n" + "=" * 60)
print("MAKING STORM PREDICTION")
print("=" * 60)

probabilities = model.predict_proba(
    prediction_df
)

storm_probability = probabilities[0][1]


# ------------------------------------------------------------
# 19. Apply selected threshold
# ------------------------------------------------------------

storm_prediction = int(
    storm_probability >= threshold
)


# ------------------------------------------------------------
# 20. Determine storm status
# ------------------------------------------------------------

if storm_prediction == 1:
    storm_status = "STORM WARNING"
else:
    storm_status = "NO STORM"


# ------------------------------------------------------------
# 21. Display weather information
# ------------------------------------------------------------

print("\nCurrent weather information:")

print(f"Temperature       : {latest['t2m']:.2f}")
print(f"Dew point         : {latest['d2m']:.2f}")
print(f"Total precipitation: {latest['tp']:.6f}")
print(f"CAPE              : {latest['cape']:.2f}")
print(f"Convective precip.: {latest['cp']:.6f}")
print(f"K Index           : {latest['kx']:.2f}")
print(f"Cloud cover       : {latest['tcc']:.3f}")
print(f"Wind speed        : {wind_speed:.2f}")
print(f"Wind gust         : {latest['i10fg']:.2f}")


# ------------------------------------------------------------
# 22. Display prediction
# ------------------------------------------------------------

print("\n" + "=" * 60)
print("STORM PREDICTION RESULT")
print("=" * 60)

print(f"\nObservation time  : {latest_time}")
print(f"Location          : {latest_latitude}, {latest_longitude}")

print(
    f"\nStorm probability : "
    f"{storm_probability * 100:.2f}%"
)

print(
    f"Decision threshold: "
    f"{threshold * 100:.0f}%"
)

print("\nPrediction:")

if storm_prediction == 1:

    print("  *** STORM WARNING ***")

    print(
        "\nThe Random Forest predicts STORM conditions."
    )

else:

    print("  NO STORM")

    print(
        "\nThe Random Forest predicts NO STORM conditions."
    )


# ------------------------------------------------------------
# 23. Display previous-hour information
# ------------------------------------------------------------

print("\nPrevious-hour observation:")
print(f"Time         : {previous_time}")
print(f"Wind speed   : {previous_wind_speed:.2f}")


# ------------------------------------------------------------
# 24. Save prediction
# ------------------------------------------------------------

prediction_output = OUTPUT_DIR / "model" / "latest_prediction.csv"

result = prediction_data.copy()

result["valid_time"] = latest_time
result["storm_probability"] = storm_probability
result["decision_threshold"] = threshold
result["storm_prediction"] = storm_prediction
result["storm_status"] = storm_status

result_df = pd.DataFrame([result])

result_df.to_csv(
    prediction_output,
    index=False
)


# ------------------------------------------------------------
# 25. Final message
# ------------------------------------------------------------

print("\nPrediction saved to:")
print(prediction_output)

print("\n" + "=" * 60)
print("PREDICTION COMPLETE")
print("=" * 60)