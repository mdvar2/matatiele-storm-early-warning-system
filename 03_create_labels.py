import pandas as pd
from pathlib import Path

# ============================================================
# CREATE STORM LABELS
# ============================================================

BASE_DIR = Path(__file__).resolve().parent

INPUT_FILE = BASE_DIR / "outputs" / "era5_merged.csv"
OUTPUT_FILE = BASE_DIR / "outputs" / "era5_labeled.csv"

print("=" * 60)
print("CREATING STORM LABELS")
print("=" * 60)

# ------------------------------------------------------------
# 1. LOAD MERGED ERA5 DATA
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

# ------------------------------------------------------------
# 3. CHECK REQUIRED VARIABLES
# ------------------------------------------------------------

required_columns = [
    "tp",
    "cape",
    "cp",
    "kx",
    "tcc",
    "i10fg"
]

missing_columns = [
    col for col in required_columns
    if col not in df.columns
]

if missing_columns:
    raise ValueError(
        f"Missing required columns: {missing_columns}"
    )

# ------------------------------------------------------------
# 4. HANDLE MISSING VALUES
# ------------------------------------------------------------

print("\nMissing values before labeling:")

print(
    df[required_columns]
    .isna()
    .sum()
)

# We cannot reliably classify a storm when one of the
# required storm indicators is missing.
#
# Therefore, missing values will remain NaN until we
# determine the label from available observations.

# ------------------------------------------------------------
# 5. CREATE STORM CONDITIONS
# ------------------------------------------------------------

# Primary precipitation condition:
# 0.001 metres = 1 mm

rain_condition = (
    df["tp"] >= 0.001
)

# Atmospheric instability:
cape_condition = (
    df["cape"] >= 200
)

# Convective precipitation:
cp_condition = (
    df["cp"] >= 0.0005
)

# Atmospheric instability:
kx_condition = (
    df["kx"] >= 26
)

# High cloud cover:
cloud_condition = (
    df["tcc"] >= 0.90
)

# At least one supporting storm indicator
supporting_condition = (
    cape_condition
    | cp_condition
    | kx_condition
    | cloud_condition
)

# ------------------------------------------------------------
# 6. CREATE STORM LABEL
# ------------------------------------------------------------

df["storm_label"] = (
    rain_condition
    & supporting_condition
).astype("Int64")

# Rows where the main storm variables needed for the
# classification are missing should not automatically
# become "No Storm".

missing_storm_data = (
    df[
        [
            "tp",
            "cape",
            "cp",
            "kx",
            "tcc"
        ]
    ]
    .isna()
    .any(axis=1)
)

df.loc[
    missing_storm_data,
    "storm_label"
] = pd.NA

# ------------------------------------------------------------
# 7. CREATE STORM DESCRIPTION
# ------------------------------------------------------------

df["storm_status"] = df["storm_label"].map(
    {
        0: "No Storm",
        1: "Storm"
    }
)

# ------------------------------------------------------------
# 8. DISPLAY RESULTS
# ------------------------------------------------------------

print("\n" + "=" * 60)
print("STORM LABEL RESULTS")
print("=" * 60)

print("\nLabel counts:")

print(
    df["storm_label"]
    .value_counts(dropna=False)
    .sort_index()
)

print("\nStorm percentage:")

valid_labels = df["storm_label"].notna()

if valid_labels.sum() > 0:

    storm_percentage = (
        df.loc[valid_labels, "storm_label"]
        .eq(1)
        .mean()
        * 100
    )

    print(
        f"{storm_percentage:.2f}% of valid observations "
        f"are classified as storms."
    )

# ------------------------------------------------------------
# 9. DISPLAY STORM EXAMPLES
# ------------------------------------------------------------

display_columns = [
    "valid_time",
    "latitude",
    "longitude",
    "tp",
    "cape",
    "cp",
    "kx",
    "tcc",
    "i10fg",
    "storm_label",
    "storm_status"
]

print("\nSample storm observations:")

print(
    df.loc[
        df["storm_label"] == 1,
        display_columns
    ]
    .sort_values("tp", ascending=False)
    .head(20)
    .to_string(index=False)
)

# ------------------------------------------------------------
# 10. SAVE
# ------------------------------------------------------------

df.to_csv(
    OUTPUT_FILE,
    index=False
)

print("\n" + "=" * 60)
print("LABEL DATASET CREATED")
print("=" * 60)

print("\nSaved to:")
print(OUTPUT_FILE)

print(f"\nRows: {len(df):,}")
print(f"Columns: {len(df.columns)}")

print("\nNew columns:")
print(" - storm_label")
print(" - storm_status")

print("\nNext step:")
print("Inspect storm-label balance before model preparation.")
