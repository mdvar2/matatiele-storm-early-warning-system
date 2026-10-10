from pathlib import Path
import pandas as pd
import numpy as np


# ---------------------------------------------------------
# PATHS
# ---------------------------------------------------------

BASE_DIR = Path(__file__).resolve().parent

INPUT_FILE = (
    BASE_DIR /
    "outputs" /
    "merged_weather_data.csv"
)

OUTPUT_FILE = (
    BASE_DIR /
    "outputs" /
    "storm_features.csv"
)


# ---------------------------------------------------------
# LOAD DATA
# ---------------------------------------------------------

df = pd.read_csv(
    INPUT_FILE
)

df["time"] = pd.to_datetime(
    df["time"]
)

df = df.sort_values(
    "time"
)


# ---------------------------------------------------------
# TEMPERATURE / DEW POINT
# ---------------------------------------------------------

if "temp" in df.columns and "dwpt" in df.columns:

    df["temp_dewpoint_difference"] = (
        df["temp"] - df["dwpt"]
    )


# ---------------------------------------------------------
# WIND FEATURES
# ---------------------------------------------------------

if "wspd" in df.columns:

    df["wind_speed_squared"] = (
        df["wspd"] ** 2
    )


if "wspd" in df.columns and "wpgt" in df.columns:

    df["gust_difference"] = (
        df["wpgt"] - df["wspd"]
    )


# ---------------------------------------------------------
# PRESSURE CHANGE
# ---------------------------------------------------------

if "pres" in df.columns:

    df["pressure_change_1h"] = (
        df["pres"]
        .diff()
    )

    df["pressure_change_3h"] = (
        df["pres"]
        .diff(3)
    )

    df["pressure_change_6h"] = (
        df["pres"]
        .diff(6)
    )


# ---------------------------------------------------------
# PRECIPITATION FEATURES
# ---------------------------------------------------------

if "prcp" in df.columns:

    df["rain_3h"] = (
        df["prcp"]
        .rolling(3)
        .sum()
    )

    df["rain_6h"] = (
        df["prcp"]
        .rolling(6)
        .sum()
    )

    df["rain_12h"] = (
        df["prcp"]
        .rolling(12)
        .sum()
    )


# ---------------------------------------------------------
# HUMIDITY FEATURES
# ---------------------------------------------------------

if "rhum" in df.columns:

    df["humidity_change"] = (
        df["rhum"]
        .diff()
    )


# ---------------------------------------------------------
# TIME FEATURES
# ---------------------------------------------------------

df["hour"] = (
    df["time"]
    .dt.hour
)

df["month"] = (
    df["time"]
    .dt.month
)

df["day_of_year"] = (
    df["time"]
    .dt.dayofyear
)


# ---------------------------------------------------------
# REMOVE INFINITE VALUES
# ---------------------------------------------------------

df = df.replace(
    [np.inf, -np.inf],
    np.nan
)


# ---------------------------------------------------------
# SAVE
# ---------------------------------------------------------

df.to_csv(
    OUTPUT_FILE,
    index=False
)


print("======================================")
print("FEATURE ENGINEERING COMPLETE")
print("======================================")

print(
    f"Rows: {len(df)}"
)

print(
    f"Columns: {len(df.columns)}"
)

print(
    f"Saved: {OUTPUT_FILE}"
)