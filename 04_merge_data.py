from pathlib import Path
import pandas as pd

# =========================================================
# PATHS
# =========================================================

BASE_DIR = Path(__file__).resolve().parent

INPUT_FILE = (
    BASE_DIR
    / "outputs"
    / "era5_combined.csv"
)

OUTPUT_FILE = (
    BASE_DIR
    / "outputs"
    / "era5_merged.csv"
)

# =========================================================
# LOAD
# =========================================================

print("=" * 60)
print("MERGING ERA5 WEATHER DATA")
print("=" * 60)

print("\nReading:")
print(INPUT_FILE)

df = pd.read_csv(INPUT_FILE)

print(f"\nInput rows: {len(df):,}")
print(f"Input columns: {len(df.columns)}")

# =========================================================
# TIME
# =========================================================

df["valid_time"] = pd.to_datetime(
    df["valid_time"],
    errors="coerce"
)

df = df.dropna(
    subset=["valid_time", "latitude", "longitude"]
)

# =========================================================
# MERGE KEY
# =========================================================

keys = [
    "valid_time",
    "latitude",
    "longitude"
]

# =========================================================
# SPLIT CATEGORIES
# =========================================================

basic = df[
    df["data_category"] == "basic_weather"
].copy()

storm = df[
    df["data_category"] == "storm_indicators"
].copy()

wind = df[
    df["data_category"] == "wind"
].copy()

print("\nRows by category:")
print(f"Basic weather:     {len(basic):,}")
print(f"Storm indicators:  {len(storm):,}")
print(f"Wind:              {len(wind):,}")

# =========================================================
# FUNCTION TO KEEP FIRST NON-NULL VALUE
# =========================================================

def combine_duplicate_rows(data, columns):
    """
    Combine duplicate time/location rows.

    For each variable, keep the first non-null value.
    This prevents valid ERA5 values from being lost when
    duplicate rows contain different variables.
    """

    available = [
        c for c in columns
        if c in data.columns
    ]

    data = data[
        available
    ].copy()

    return (
        data
        .groupby(keys, as_index=False)
        .first()
    )

# =========================================================
# VARIABLES
# =========================================================

basic_columns = [
    "valid_time",
    "latitude",
    "longitude",
    "t2m",
    "d2m",
    "msl",
    "sp",
    "tp"
]

storm_columns = [
    "valid_time",
    "latitude",
    "longitude",
    "cape",
    "cp",
    "kx",
    "tcc"
]

wind_columns = [
    "valid_time",
    "latitude",
    "longitude",
    "u10",
    "v10",
    "i10fg"
]

# =========================================================
# COMBINE DUPLICATES
# =========================================================

print("\nCombining duplicate basic-weather rows...")

basic = combine_duplicate_rows(
    basic,
    basic_columns
)

print(
    f"Basic weather unique rows: {len(basic):,}"
)

print("\nCombining duplicate storm-indicator rows...")

storm = combine_duplicate_rows(
    storm,
    storm_columns
)

print(
    f"Storm indicator unique rows: {len(storm):,}"
)

print("\nCombining duplicate wind rows...")

wind = combine_duplicate_rows(
    wind,
    wind_columns
)

print(
    f"Wind unique rows: {len(wind):,}"
)

# =========================================================
# CHECK VARIABLES BEFORE MERGING
# =========================================================

print("\n" + "=" * 60)
print("VARIABLE AVAILABILITY BEFORE MERGE")
print("=" * 60)

print("\nBasic weather:")
print(
    basic[
        ["t2m", "d2m", "msl", "sp", "tp"]
    ].notna().sum()
)

print("\nStorm indicators:")
print(
    storm[
        ["cape", "cp", "kx", "tcc"]
    ].notna().sum()
)

print("\nWind:")
print(
    wind[
        ["u10", "v10", "i10fg"]
    ].notna().sum()
)

# =========================================================
# MERGE BASIC + STORM
# =========================================================

print("\n" + "=" * 60)
print("MERGING DATASETS")
print("=" * 60)

print("\nMerging basic weather + storm indicators...")

merged = pd.merge(
    basic,
    storm,
    on=keys,
    how="inner"
)

print(
    f"After basic + storm: {len(merged):,} rows"
)

# =========================================================
# MERGE WIND
# =========================================================

print("\nMerging wind data...")

merged = pd.merge(
    merged,
    wind,
    on=keys,
    how="inner"
)

print(
    f"After wind merge: {len(merged):,} rows"
)

# =========================================================
# SORT
# =========================================================

merged = merged.sort_values(
    keys
).reset_index(drop=True)

# =========================================================
# FINAL CHECK
# =========================================================

print("\n" + "=" * 60)
print("FINAL DATASET")
print("=" * 60)

print(
    f"\nRows:    {len(merged):,}"
)

print(
    f"Columns: {len(merged.columns)}"
)

print("\nColumns:")

for column in merged.columns:
    print(f" - {column}")

# =========================================================
# MISSING VALUES
# =========================================================

check_columns = [
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

print("\nMissing values:")

print(
    merged[check_columns].isna().sum()
)

# =========================================================
# SAVE
# =========================================================

merged.to_csv(
    OUTPUT_FILE,
    index=False
)

print("\n" + "=" * 60)
print("MERGE COMPLETE")
print("=" * 60)

print("\nSaved to:")
print(OUTPUT_FILE)