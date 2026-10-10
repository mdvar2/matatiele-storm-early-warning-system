from pathlib import Path
import pandas as pd
import xarray as xr

# ============================================================
# 02 - CLEAN WEATHER DATA
# ============================================================

print("=" * 60)
print("CLEANING WEATHER DATA")
print("=" * 60)

# ------------------------------------------------------------
# PROJECT DIRECTORIES
# ------------------------------------------------------------

PROJECT_DIR = Path(__file__).resolve().parent

METEOSTAT_DIR = PROJECT_DIR / "data" / "meteostat"
ERA5_DIR = PROJECT_DIR / "data" / "era5"
OUTPUT_DIR = PROJECT_DIR / "outputs"

# Create outputs folder if it does not exist
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

print("\nProject directory:")
print(PROJECT_DIR)

print("\nMeteostat directory:")
print(METEOSTAT_DIR)

print("\nERA5 directory:")
print(ERA5_DIR)

print("\nOutput directory:")
print(OUTPUT_DIR)


# ============================================================
# PART 1 - CLEAN METEOSTAT DATA
# ============================================================

print("\n" + "=" * 60)
print("PART 1 - CLEANING METEOSTAT DATA")
print("=" * 60)

meteostat_files = list(METEOSTAT_DIR.rglob("*.csv"))

if not meteostat_files:
    print("\nERROR: No Meteostat CSV files were found.")
else:

    print(f"\nFound {len(meteostat_files)} Meteostat CSV files.")

    meteostat_data = []

    for file in meteostat_files:

        print(f"\nReading: {file.name}")

        try:
            df = pd.read_csv(file)

            print(f"Rows found: {len(df)}")
            print(f"Columns: {list(df.columns)}")

            # Add source filename
            df["source_file"] = file.name

            meteostat_data.append(df)

        except Exception as e:

            print(f"ERROR reading {file.name}: {e}")

    # --------------------------------------------------------
    # COMBINE METEOSTAT FILES
    # --------------------------------------------------------

    if meteostat_data:

        meteostat = pd.concat(
            meteostat_data,
            ignore_index=True
        )

        print("\nCombined Meteostat rows:")
        print(len(meteostat))

        # ----------------------------------------------------
        # CLEAN COLUMN NAMES
        # ----------------------------------------------------

        meteostat.columns = (
            meteostat.columns
            .str.strip()
            .str.lower()
            .str.replace(" ", "_")
        )

        # ----------------------------------------------------
        # FIND DATE/TIME COLUMN
        # ----------------------------------------------------

        possible_time_columns = [
            "time",
            "date",
            "datetime",
            "timestamp"
        ]

        time_column = None

        for column in possible_time_columns:

            if column in meteostat.columns:
                time_column = column
                break

        if time_column:

            print(f"\nTime column found: {time_column}")

            meteostat["time"] = pd.to_datetime(
                meteostat[time_column],
                errors="coerce"
            )

            # Remove invalid timestamps
            meteostat = meteostat.dropna(
                subset=["time"]
            )

            meteostat = meteostat.sort_values(
                "time"
            )

        else:

            print("\nWARNING: No time column detected.")

        # ----------------------------------------------------
        # REMOVE DUPLICATES
        # ----------------------------------------------------

        before = len(meteostat)

        if "time" in meteostat.columns:

            meteostat = meteostat.drop_duplicates(
                subset=["time"]
            )

        else:

            meteostat = meteostat.drop_duplicates()

        after = len(meteostat)

        print(
            f"\nRemoved {before - after} duplicate rows."
        )

        # ----------------------------------------------------
        # SAVE CLEAN METEOSTAT DATA
        # ----------------------------------------------------

        meteostat_output = (
            OUTPUT_DIR / "meteostat_clean.csv"
        )

        meteostat.to_csv(
            meteostat_output,
            index=False
        )

        print(
            f"\n✓ Clean Meteostat data saved to:"
        )

        print(meteostat_output)

        print(
            f"✓ Final Meteostat rows: {len(meteostat)}"
        )


# ============================================================
# PART 2 - FIND ERA5 NETCDF FILES
# ============================================================

print("\n" + "=" * 60)
print("PART 2 - PROCESSING ERA5 DATA")
print("=" * 60)

# IMPORTANT:
#
# Your folders are structured like:
#
# era5/
#   era5_2018.nc/
#       January/
#           Basic Weather/
#           Storm_indicators/
#           Wind/
#
# Therefore we MUST recursively search for .nc files.

era5_files = list(
    ERA5_DIR.rglob("*.nc")
)

print(
    f"\nFound {len(era5_files)} ERA5 NetCDF files."
)


if not era5_files:

    print(
        "\nERROR: No ERA5 NetCDF files were found."
    )

else:

    # --------------------------------------------------------
    # SHOW FILE TYPES
    # --------------------------------------------------------

    accum_files = []

    instant_files = []

    for file in era5_files:

        if "accum" in file.name.lower():
            accum_files.append(file)

        elif "instant" in file.name.lower():
            instant_files.append(file)

    print(
        f"\nAccumulated files: {len(accum_files)}"
    )

    print(
        f"Instantaneous files: {len(instant_files)}"
    )


# ============================================================
# PART 3 - PROCESS ERA5 FILES
# ============================================================

print("\n" + "=" * 60)
print("READING ERA5 NETCDF FILES")
print("=" * 60)

era5_data = []

# Limit output messages so the terminal does not become
# impossible to read.

for number, file in enumerate(era5_files, start=1):

    print(
        f"\n[{number}/{len(era5_files)}] "
        f"Reading {file.name}"
    )

    try:

        # Open NetCDF
        ds = xr.open_dataset(
            file
        )

        # Convert to pandas DataFrame
        df = ds.to_dataframe().reset_index()

        # Add information about where this data came from
        df["source_file"] = file.name

        # ----------------------------------------------------
        # DETERMINE YEAR
        # ----------------------------------------------------

        year = None

        for parent in file.parents:

            if parent.name.startswith("era5_"):

                year_text = (
                    parent.name
                    .replace("era5_", "")
                    .replace(".nc", "")
                )

                if year_text.isdigit():

                    year = int(year_text)

                    break

        if year:

            df["year"] = year

        # ----------------------------------------------------
        # DETERMINE MONTH
        # ----------------------------------------------------

        months = {
            "January": 1,
            "February": 2,
            "March": 3,
            "April": 4,
            "May": 5,
            "June": 6,
            "July": 7,
            "August": 8,
            "September": 9,
            "October": 10,
            "November": 11,
            "December": 12
        }

        month = None

        for parent in file.parents:

            if parent.name in months:

                month = months[parent.name]

                break

        if month:

            df["month_folder"] = month

        # ----------------------------------------------------
        # DETERMINE DATA CATEGORY
        # ----------------------------------------------------

        category = "unknown"

        for parent in file.parents:

            folder_name = parent.name.lower()

            if folder_name == "basic weather":
                category = "basic_weather"

            elif folder_name == "storm_indicators":
                category = "storm_indicators"

            elif folder_name == "wind":
                category = "wind"

        df["data_category"] = category

        # Add to list
        era5_data.append(df)

        ds.close()

    except Exception as e:

        print(
            f"WARNING: Could not read:"
        )

        print(file)

        print(f"Reason: {e}")


# ============================================================
# PART 4 - COMBINE ERA5 DATA
# ============================================================

print("\n" + "=" * 60)
print("COMBINING ERA5 DATA")
print("=" * 60)

if not era5_data:

    print(
        "\nERROR: No ERA5 datasets could be read."
    )

else:

    print(
        f"\nSuccessfully read "
        f"{len(era5_data)} ERA5 files."
    )

    # --------------------------------------------------------
    # IMPORTANT
    #
    # We do NOT immediately concatenate all ERA5 files.
    #
    # Different ERA5 files contain different variables.
    #
    # Instead, we save the processed files individually.
    # --------------------------------------------------------

    ERA5_OUTPUT_DIR = (
        OUTPUT_DIR / "era5_processed"
    )

    ERA5_OUTPUT_DIR.mkdir(
        parents=True,
        exist_ok=True
    )

    # Save each processed dataset

    for index, df in enumerate(
        era5_data,
        start=1
    ):

        output_file = (
            ERA5_OUTPUT_DIR /
            f"era5_processed_{index}.csv"
        )

        df.to_csv(
            output_file,
            index=False
        )

    print(
        f"\n✓ Saved {len(era5_data)} "
        f"processed ERA5 files."
    )

    print(
        f"Location:"
    )

    print(ERA5_OUTPUT_DIR)


# ============================================================
# FINAL SUMMARY
# ============================================================

print("\n" + "=" * 60)
print("CLEANING COMPLETE")
print("=" * 60)

print(
    "\nMeteostat files found:"
    f" {len(meteostat_files)}"
)

print(
    "ERA5 files found:"
    f" {len(era5_files)}"
)

print(
    "\nThe cleaned data is now available in:"
)

print(OUTPUT_DIR)

print(
    "\nNext step:"
)

print(
    "03_create_labels.py"
)

print()