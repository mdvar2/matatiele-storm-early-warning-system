import shutil
import zipfile
from pathlib import Path
from datetime import datetime, timedelta, UTC

import cdsapi
import joblib
import numpy as np
import pandas as pd
import xarray as xr


# ============================================================
# AUTOMATIC ERA5 UPDATE -> RANDOM FOREST -> WARNING
# ============================================================

BASE_DIR = Path(__file__).resolve().parent

LIVE_DIR = BASE_DIR / "data" / "era5_live"
MODEL_DIR = BASE_DIR / "outputs" / "model"

LIVE_DIR.mkdir(parents=True, exist_ok=True)
MODEL_DIR.mkdir(parents=True, exist_ok=True)

# CDS may package this request as a ZIP because the variables
# belong to different ERA5 step types.
DOWNLOAD_FILE = LIVE_DIR / "latest_era5.zip"

EXTRACT_DIR = LIVE_DIR / "latest_era5_extracted"

MODEL_FILE = MODEL_DIR / "random_forest_storm_model.pkl"
FEATURE_FILE = MODEL_DIR / "model_features.txt"
THRESHOLD_FILE = MODEL_DIR / "selected_threshold.txt"

PREDICTION_FILE = MODEL_DIR / "automatic_prediction.csv"


# ============================================================
# SETTINGS
# ============================================================

# Matatiele point used by the project
TARGET_LATITUDE = -30.30
TARGET_LONGITUDE = 28.80

# ERA5 bounding box:
# North, West, South, East
NORTH = -30.23
WEST = 28.67
SOUTH = -30.49
EAST = 28.93


print("=" * 70)
print("AUTOMATIC ERA5 STORM PREDICTION SYSTEM")
print("=" * 70)


# ============================================================
# 1. CHECK MODEL FILES
# ============================================================

print("\nChecking trained model files...")

required_model_files = [
    MODEL_FILE,
    FEATURE_FILE,
    THRESHOLD_FILE
]

for file in required_model_files:

    if not file.exists():

        raise FileNotFoundError(
            f"Required model file not found:\n{file}"
        )

print("All model files found.")


# ============================================================
# 2. SELECT ERA5 DATE
# ============================================================

# ERA5/ERA5T is not a true live forecast product.
# We request several days behind the current UTC date to
# reduce the chance of requesting data that has not yet
# reached the CDS archive.

target_date = (
    datetime.now(UTC)
    - timedelta(days=6)
)

year = target_date.strftime("%Y")
month = target_date.strftime("%m")
day = target_date.strftime("%d")

print("\nERA5 target date:")
print(
    target_date.strftime("%Y-%m-%d")
)


# ============================================================
# 3. CLEAN PREVIOUS LIVE DOWNLOAD
# ============================================================

if DOWNLOAD_FILE.exists():

    print("\nRemoving previous ERA5 download...")

    DOWNLOAD_FILE.unlink()


if EXTRACT_DIR.exists():

    print("Removing previous extracted ERA5 files...")

    shutil.rmtree(
        EXTRACT_DIR
    )


EXTRACT_DIR.mkdir(
    parents=True,
    exist_ok=True
)


# ============================================================
# 4. CREATE CDS REQUEST
# ============================================================

print("\nPreparing CDS request...")

dataset_name = (
    "reanalysis-era5-single-levels"
)

request = {

    "product_type": [
        "reanalysis"
    ],

    "variable": [

        # Wind
        "10m_u_component_of_wind",
        "10m_v_component_of_wind",
        "instantaneous_10m_wind_gust",

        # Temperature
        "2m_dewpoint_temperature",
        "2m_temperature",

        # Pressure
        "mean_sea_level_pressure",
        "surface_pressure",

        # Precipitation
        "total_precipitation",
        "convective_precipitation",

        # Storm indicators
        "convective_available_potential_energy",
        "k_index",
        "total_cloud_cover"
    ],

    "year": [
        year
    ],

    "month": [
        month
    ],

    "day": [
        day
    ],

    "time": [

        "00:00",
        "01:00",
        "02:00",
        "03:00",
        "04:00",
        "05:00",
        "06:00",
        "07:00",
        "08:00",
        "09:00",
        "10:00",
        "11:00",
        "12:00",
        "13:00",
        "14:00",
        "15:00",
        "16:00",
        "17:00",
        "18:00",
        "19:00",
        "20:00",
        "21:00",
        "22:00",
        "23:00"
    ],

    "data_format": "netcdf",

    # We know CDS is packaging the mixed step types
    # into a ZIP archive.
    "download_format": "zip",

    "area": [
        NORTH,
        WEST,
        SOUTH,
        EAST
    ]
}


# ============================================================
# 5. DOWNLOAD ERA5
# ============================================================

print("\nDownloading ERA5 data...")

client = cdsapi.Client()

try:

    client.retrieve(
        dataset_name,
        request,
        str(DOWNLOAD_FILE)
    )

except Exception as error:

    print("\nERA5 download failed.")
    print(error)

    raise SystemExit(1)


print("\nERA5 download completed:")
print(DOWNLOAD_FILE)

print(
    f"Downloaded size: "
    f"{DOWNLOAD_FILE.stat().st_size:,} bytes"
)


# ============================================================
# 6. DETECT ACTUAL FILE FORMAT
# ============================================================

print("\nChecking downloaded file format...")

with open(
    DOWNLOAD_FILE,
    "rb"
) as file:

    signature = file.read(4)


is_zip = (
    signature == b"PK\x03\x04"
)


# ============================================================
# 7. EXTRACT ZIP OR USE DIRECT NETCDF
# ============================================================

if is_zip:

    print(
        "CDS returned a ZIP archive."
    )

    with zipfile.ZipFile(
        DOWNLOAD_FILE,
        "r"
    ) as archive:

        print("\nZIP contents:")

        for name in archive.namelist():
            print(" -", name)

        archive.extractall(
            EXTRACT_DIR
        )

    nc_files = sorted(
        EXTRACT_DIR.rglob("*.nc")
    )

else:

    print(
        "CDS returned a direct NetCDF file."
    )

    nc_files = [
        DOWNLOAD_FILE
    ]


if not nc_files:

    raise FileNotFoundError(
        "No NetCDF files were found after "
        "download/extraction."
    )


print(
    f"\nNetCDF files found: {len(nc_files)}"
)

for file in nc_files:
    print(" -", file)


# ============================================================
# 8. HELPER: NORMALISE TIME
# ============================================================

def normalise_time(frame):

    if "valid_time" in frame.columns:

        frame["valid_time"] = (
            pd.to_datetime(
                frame["valid_time"],
                errors="coerce"
            )
        )

    elif "time" in frame.columns:

        frame["valid_time"] = (
            pd.to_datetime(
                frame["time"],
                errors="coerce"
            )
        )

    else:

        raise ValueError(
            "No valid_time or time column "
            "was found in ERA5 data."
        )

    return frame


# ============================================================
# 9. HELPER: NORMALISE VARIABLE NAMES
# ============================================================

def normalise_columns(frame):

    # Most modern ERA5 NetCDF files already use these
    # short variable names, but this map provides some
    # protection against alternative names.

    rename_map = {

        "10u": "u10",
        "10v": "v10",

        "2t": "t2m",
        "2d": "d2m",

        "mean_sea_level_pressure": "msl",
        "surface_pressure": "sp",

        "total_precipitation": "tp",
        "convective_precipitation": "cp",

        "convective_available_potential_energy": "cape",

        "k_index": "kx",

        "total_cloud_cover": "tcc",

        "instantaneous_10m_wind_gust": "i10fg"
    }

    frame = frame.rename(
        columns=rename_map
    )

    return frame


# ============================================================
# 10. READ ALL EXTRACTED NETCDF FILES
# ============================================================

print("\n" + "=" * 70)
print("READING ERA5 NETCDF FILES")
print("=" * 70)

processed_frames = []


weather_variable_names = [

    "u10",
    "v10",
    "i10fg",

    "d2m",
    "t2m",

    "msl",
    "sp",

    "tp",
    "cp",

    "cape",
    "kx",
    "tcc"
]


merge_keys = [

    "valid_time",
    "latitude",
    "longitude"
]


for number, nc_file in enumerate(
    nc_files,
    start=1
):

    print(
        f"\n[{number}/{len(nc_files)}] "
        f"Opening:"
    )

    print(nc_file)

    try:

        ds = xr.open_dataset(
            nc_file,
            engine="netcdf4"
        )

    except Exception as error:

        print(
            "Could not open this NetCDF file."
        )

        print(error)

        continue


    print(
        "Variables:",
        list(ds.data_vars)
    )


    frame = (
        ds
        .to_dataframe()
        .reset_index()
    )

    ds.close()


    frame = normalise_time(
        frame
    )

    frame = normalise_columns(
        frame
    )


    # --------------------------------------------------------
    # REMOVE INVALID LOCATION/TIME RECORDS
    # --------------------------------------------------------

    frame = frame.dropna(
        subset=[
            "valid_time",
            "latitude",
            "longitude"
        ]
    )


    # --------------------------------------------------------
    # KEEP ONLY RELEVANT WEATHER VARIABLES
    # --------------------------------------------------------

    available_weather_columns = [

        column

        for column
        in weather_variable_names

        if column in frame.columns
    ]


    keep_columns = (
        merge_keys
        +
        available_weather_columns
    )


    frame = frame[
        keep_columns
    ].copy()


    # --------------------------------------------------------
    # COLLAPSE NUMBER / EXPVER DUPLICATES
    # --------------------------------------------------------

    # Some ERA5 files may generate multiple rows for the same
    # timestamp/location because of dimensions such as
    # expver or number.
    #
    # groupby().first() keeps the first non-null value for
    # each weather variable, which matches the method that
    # successfully worked for the historical dataset.

    frame = (
        frame
        .groupby(
            merge_keys,
            as_index=False
        )
        .first()
    )


    print(
        f"Rows after cleaning: "
        f"{len(frame):,}"
    )

    print(
        "Weather columns:",
        available_weather_columns
    )


    processed_frames.append(
        frame
    )


if not processed_frames:

    raise ValueError(
        "None of the downloaded NetCDF files "
        "could be processed."
    )


# ============================================================
# 11. MERGE NETCDF DATA HORIZONTALLY
# ============================================================

print("\n" + "=" * 70)
print("MERGING ERA5 VARIABLES")
print("=" * 70)


df = processed_frames[0]


for frame_number, next_frame in enumerate(
    processed_frames[1:],
    start=2
):

    print(
        f"\nMerging processed frame "
        f"{frame_number}..."
    )


    # Keep the merge keys plus variables that are not
    # already present in the current dataframe.

    new_columns = [

        column

        for column
        in next_frame.columns

        if (
            column in merge_keys
            or
            column not in df.columns
        )
    ]


    next_frame = next_frame[
        new_columns
    ]


    df = pd.merge(
        df,
        next_frame,
        on=merge_keys,
        how="outer"
    )


print(
    f"\nMerged rows: "
    f"{len(df):,}"
)

print(
    f"Merged columns: "
    f"{len(df.columns)}"
)


print("\nMerged ERA5 columns:")

for column in df.columns:
    print(" -", column)


# ============================================================
# 12. CHECK REQUIRED WEATHER VARIABLES
# ============================================================

required_weather = [

    "valid_time",

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

    for column
    in required_weather

    if column not in df.columns
]


if missing_columns:

    print(
        "\nRequired ERA5 variables are missing:"
    )

    for column in missing_columns:
        print(" -", column)

    raise ValueError(
        "The live ERA5 dataset does not contain "
        "all 31-model-input weather variables."
    )


# ============================================================
# 13. DISPLAY MISSING VALUES
# ============================================================

print("\nMissing values:")

print(
    df[
        required_weather
    ]
    .isna()
    .sum()
)


# ============================================================
# 14. REMOVE INCOMPLETE OBSERVATIONS
# ============================================================

complete = df.dropna(
    subset=required_weather
).copy()


if complete.empty:

    raise ValueError(
        "No complete live ERA5 observations "
        "were available."
    )


print(
    f"\nComplete ERA5 rows: "
    f"{len(complete):,}"
)


# ============================================================
# 15. FIND LATEST AVAILABLE TIME
# ============================================================

latest_time = (
    complete["valid_time"]
    .max()
)


latest_time_rows = complete[
    complete["valid_time"]
    ==
    latest_time
].copy()


print("\nLatest available ERA5 time:")
print(latest_time)


# ============================================================
# 16. SELECT GRID POINT NEAREST MATATIELE
# ============================================================

latest_time_rows["grid_distance"] = (

    (
        latest_time_rows["latitude"]
        -
        TARGET_LATITUDE
    ) ** 2

    +

    (
        latest_time_rows["longitude"]
        -
        TARGET_LONGITUDE
    ) ** 2
)


latest = (
    latest_time_rows
    .sort_values(
        "grid_distance"
    )
    .iloc[0]
)


latitude = latest["latitude"]
longitude = latest["longitude"]


print("\nSelected ERA5 grid point:")

print(
    f"Latitude : {latitude}"
)

print(
    f"Longitude: {longitude}"
)


# ============================================================
# 17. FIND PREVIOUS HOUR
# ============================================================

previous_time = (
    latest_time
    -
    pd.Timedelta(hours=1)
)


previous_rows = complete[

    (
        complete["valid_time"]
        ==
        previous_time
    )

    &

    (
        complete["latitude"]
        ==
        latitude
    )

    &

    (
        complete["longitude"]
        ==
        longitude
    )

]


if previous_rows.empty:

    raise ValueError(
        f"No complete previous-hour observation "
        f"was found for:\n"
        f"{previous_time}\n"
        f"{latitude}, {longitude}"
    )


previous = previous_rows.iloc[0]


# ============================================================
# 18. CALCULATE DERIVED FEATURES
# ============================================================

wind_speed = np.sqrt(

    latest["u10"] ** 2

    +

    latest["v10"] ** 2
)


previous_wind_speed = np.sqrt(

    previous["u10"] ** 2

    +

    previous["v10"] ** 2
)


hour = latest_time.hour
month = latest_time.month
day_of_year = latest_time.dayofyear


# ============================================================
# 19. BUILD RANDOM FOREST INPUT
# ============================================================

prediction_data = {

    # Location
    "latitude": latitude,
    "longitude": longitude,

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

    # Derived current feature
    "wind_speed": wind_speed,

    # Previous hour
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

    "previous_wind_speed": (
        previous_wind_speed
    )
}


prediction_df = pd.DataFrame(
    [prediction_data]
)


# ============================================================
# 20. LOAD TRAINED RANDOM FOREST
# ============================================================

print("\nLoading trained Random Forest...")

model = joblib.load(
    MODEL_FILE
)

print("Random Forest loaded.")


# ============================================================
# 21. LOAD EXACT TRAINING FEATURE ORDER
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
    f"Model expects "
    f"{len(features)} features."
)


missing_model_features = [

    feature

    for feature
    in features

    if feature not in prediction_df.columns
]


if missing_model_features:

    raise ValueError(
        "Prediction data is missing "
        f"model features:\n"
        f"{missing_model_features}"
    )


prediction_df = (
    prediction_df[
        features
    ]
)


# ============================================================
# 22. LOAD SELECTED THRESHOLD
# ============================================================

with open(
    THRESHOLD_FILE,
    "r",
    encoding="utf-8"
) as file:

    threshold = float(
        file.read().strip()
    )


# ============================================================
# 23. MAKE RANDOM FOREST PREDICTION
# ============================================================

probability = (
    model
    .predict_proba(
        prediction_df
    )[0][1]
)


prediction = int(
    probability
    >=
    threshold
)


# ============================================================
# 24. WARNING STATUS
# ============================================================

if prediction == 1:

    warning_status = (
        "STORM WARNING"
    )

else:

    warning_status = (
        "NO STORM"
    )


# ============================================================
# 25. DISPLAY WEATHER
# ============================================================

print("\n" + "=" * 70)
print("LATEST ERA5 WEATHER")
print("=" * 70)

print(
    f"\nObservation time : "
    f"{latest_time}"
)

print(
    f"Previous hour    : "
    f"{previous_time}"
)

print(
    f"Grid location    : "
    f"{latitude}, {longitude}"
)


print("\nCurrent conditions:")

print(
    f"Temperature      : "
    f"{latest['t2m']:.2f} K"
)

print(
    f"Dew point        : "
    f"{latest['d2m']:.2f} K"
)

print(
    f"MSL pressure     : "
    f"{latest['msl']:.2f} Pa"
)

print(
    f"Surface pressure : "
    f"{latest['sp']:.2f} Pa"
)

print(
    f"Precipitation    : "
    f"{latest['tp']:.6f} m"
)

print(
    f"Convective precip: "
    f"{latest['cp']:.6f} m"
)

print(
    f"CAPE             : "
    f"{latest['cape']:.2f}"
)

print(
    f"K Index          : "
    f"{latest['kx']:.2f}"
)

print(
    f"Cloud cover      : "
    f"{latest['tcc']:.3f}"
)

print(
    f"Wind speed       : "
    f"{wind_speed:.2f} m/s"
)

print(
    f"Wind gust        : "
    f"{latest['i10fg']:.2f} m/s"
)


# ============================================================
# 26. DISPLAY PREDICTION
# ============================================================

print("\n" + "=" * 70)
print("RANDOM FOREST NEXT-HOUR PREDICTION")
print("=" * 70)

print(
    f"\nStorm probability: "
    f"{probability * 100:.2f}%"
)

print(
    f"Decision threshold: "
    f"{threshold * 100:.0f}%"
)

print(
    f"\nPrediction: "
    f"{warning_status}"
)


if prediction == 1:

    print(
        "\nWARNING:"
    )

    print(
        "The Random Forest predicts storm "
        "conditions for the next hour."
    )

else:

    print(
        "\nThe Random Forest predicts no storm "
        "for the next hour."
    )


# ============================================================
# 27. SAVE AUTOMATIC PREDICTION
# ============================================================

result = {

    "era5_observation_time":
        latest_time,

    "prediction_for":
        latest_time
        + pd.Timedelta(hours=1),

    "latitude":
        latitude,

    "longitude":
        longitude,

    "storm_probability":
        probability,

    "decision_threshold":
        threshold,

    "storm_prediction":
        prediction,

    "warning_status":
        warning_status,

    "temperature_k":
        latest["t2m"],

    "dewpoint_k":
        latest["d2m"],

    "total_precipitation_m":
        latest["tp"],

    "convective_precipitation_m":
        latest["cp"],

    "cape":
        latest["cape"],

    "k_index":
        latest["kx"],

    "cloud_cover":
        latest["tcc"],

    "wind_speed_ms":
        wind_speed,

    "wind_gust_ms":
        latest["i10fg"]
}


pd.DataFrame(
    [result]
).to_csv(
    PREDICTION_FILE,
    index=False
)


print("\nPrediction saved to:")
print(PREDICTION_FILE)


print("\n" + "=" * 70)
print("AUTOMATIC UPDATE AND PREDICTION COMPLETE")
print("=" * 70)