import pandas as pd
from pathlib import Path

# ============================================================
# PREPARE MODEL DATA
# ============================================================

BASE_DIR = Path(__file__).resolve().parent

INPUT_FILE = BASE_DIR / "outputs" / "era5_labeled.csv"
OUTPUT_FILE = BASE_DIR / "outputs" / "model_ready.csv"

print("=" * 60)
print("PREPARING MODEL DATA")
print("=" * 60)

# ------------------------------------------------------------
# 1. LOAD LABELED DATA
# ------------------------------------------------------------

print("\nReading:")
print(INPUT_FILE)

if not INPUT_FILE.exists():
    raise FileNotFoundError(
        f"Input file not found:\n{INPUT_FILE}"
    )

df = pd.read_csv(INPUT_FILE)

print(f"\nInput rows: {len(df):,}")
print(f"Input columns: {len(df.columns)}")

# ------------------------------------------------------------
# 2. CONVERT TIME
# ------------------------------------------------------------

df["valid_time"] = pd.to_datetime(
    df["valid_time"],
    errors="coerce"
)

# Remove invalid timestamps

df = df.dropna(
    subset=["valid_time"]
)

# Sort chronologically and by location

df = df.sort_values(
    ["latitude", "longitude", "valid_time"]
).reset_index(drop=True)

# ------------------------------------------------------------
# 3. REQUIRED COLUMNS
# ------------------------------------------------------------

required_columns = [
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
    "i10fg",
    "storm_label"
]

missing_columns = [
    column
    for column in required_columns
    if column not in df.columns
]

if missing_columns:
    raise ValueError(
        "Missing required columns:\n"
        + "\n".join(missing_columns)
    )

# ------------------------------------------------------------
# 4. REMOVE INCOMPLETE OBSERVATIONS
# ------------------------------------------------------------

weather_columns = [
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
    "i10fg",
    "storm_label"
]

print("\nMissing values before cleaning:")

print(
    df[weather_columns]
    .isna()
    .sum()
)

before_cleaning = len(df)

df = df.dropna(
    subset=weather_columns
).copy()

after_cleaning = len(df)

print(
    f"\nIncomplete observations removed: "
    f"{before_cleaning - after_cleaning:,}"
)

print(
    f"Complete observations remaining: "
    f"{after_cleaning:,}"
)

# ------------------------------------------------------------
# 5. CREATE TIME FEATURES
# ------------------------------------------------------------

print("\nCreating time features...")

df["hour"] = df["valid_time"].dt.hour

df["month"] = df["valid_time"].dt.month

df["day_of_year"] = (
    df["valid_time"].dt.dayofyear
)

# ------------------------------------------------------------
# 6. CREATE WIND SPEED
# ------------------------------------------------------------

print("Creating wind speed...")

df["wind_speed"] = (
    (df["u10"] ** 2 + df["v10"] ** 2)
    ** 0.5
)

# ------------------------------------------------------------
# 7. CREATE PREVIOUS-HOUR FEATURES
# ------------------------------------------------------------

print("Creating previous-hour features...")

group_columns = [
    "latitude",
    "longitude"
]

previous_features = [
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
    "i10fg",
    "wind_speed"
]

for column in previous_features:

    df[f"previous_{column}"] = (
        df.groupby(group_columns)[column]
        .shift(1)
    )

# ------------------------------------------------------------
# 8. CREATE NEXT-HOUR STORM TARGET
# ------------------------------------------------------------

print("Creating next-hour storm target...")

df["target_storm"] = (
    df.groupby(group_columns)["storm_label"]
    .shift(-1)
)

# ------------------------------------------------------------
# 9. CHECK TIME CONTINUITY
# ------------------------------------------------------------

print("\nChecking hourly continuity...")

df["time_difference"] = (
    df.groupby(group_columns)["valid_time"]
    .diff()
)

continuous_rows = (
    df["time_difference"]
    == pd.Timedelta(hours=1)
)

print(
    "Rows with previous observation exactly "
    f"1 hour earlier: {continuous_rows.sum():,}"
)

# ------------------------------------------------------------
# 10. REMOVE ROWS WITHOUT A NEXT-HOUR TARGET
# ------------------------------------------------------------

before_target = len(df)

df = df.dropna(
    subset=["target_storm"]
).copy()

after_target = len(df)

print(
    f"\nRows removed because next-hour target "
    f"is unavailable: "
    f"{before_target - after_target:,}"
)

# ------------------------------------------------------------
# 11. CONVERT TARGET TO INTEGER
# ------------------------------------------------------------

df["target_storm"] = (
    df["target_storm"]
    .astype(int)
)

# ------------------------------------------------------------
# 12. REMOVE UNNECESSARY COLUMNS
# ------------------------------------------------------------

# storm_label represents the current hour.
# We keep it for inspection but DO NOT use it
# as a model feature later.

# time_difference is only a diagnostic column.

df = df.drop(
    columns=["time_difference"]
)

# ------------------------------------------------------------
# 13. FINAL SORT
# ------------------------------------------------------------

df = df.sort_values(
    ["valid_time", "latitude", "longitude"]
).reset_index(drop=True)

# ------------------------------------------------------------
# 14. DISPLAY TARGET BALANCE
# ------------------------------------------------------------

print("\n" + "=" * 60)
print("NEXT-HOUR TARGET RESULTS")
print("=" * 60)

print("\nTarget counts:")

print(
    df["target_storm"]
    .value_counts()
    .sort_index()
)

print("\nTarget percentages:")

print(
    (
        df["target_storm"]
        .value_counts(normalize=True)
        .sort_index()
        * 100
    )
)

# ------------------------------------------------------------
# 15. DISPLAY DATE RANGE
# ------------------------------------------------------------

print("\nDate range:")

print(
    "Start:",
    df["valid_time"].min()
)

print(
    "End:",
    df["valid_time"].max()
)

# ------------------------------------------------------------
# 16. DISPLAY FINAL DATASET INFORMATION
# ------------------------------------------------------------

print("\n" + "=" * 60)
print("MODEL-READY DATASET")
print("=" * 60)

print(
    f"\nRows:    {len(df):,}"
)

print(
    f"Columns: {len(df.columns)}"
)

print("\nColumns:")

for column in df.columns:
    print(" -", column)

# ------------------------------------------------------------
# 17. SAVE
# ------------------------------------------------------------

OUTPUT_FILE.parent.mkdir(
    parents=True,
    exist_ok=True
)

df.to_csv(
    OUTPUT_FILE,
    index=False
)

print("\n" + "=" * 60)
print("MODEL DATA CREATED")
print("=" * 60)

print("\nSaved to:")

print(OUTPUT_FILE)

print("\nNext step:")
print("Inspect model_ready.csv before training the Random Forest.")