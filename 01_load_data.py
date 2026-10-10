from pathlib import Path

print("=" * 60)
print("LOADING WEATHER DATA")
print("=" * 60)

# ---------------------------------------------------------
# PROJECT DIRECTORIES
# ---------------------------------------------------------

PROJECT_DIR = Path(__file__).resolve().parent

METEOSTAT_DIR = PROJECT_DIR / "data" / "meteostat"
ERA5_DIR = PROJECT_DIR / "data" / "era5"

print("\nProject directory:")
print(PROJECT_DIR)

print("\nMeteostat directory:")
print(METEOSTAT_DIR)

print("\nERA5 directory:")
print(ERA5_DIR)

# ---------------------------------------------------------
# FIND METEOSTAT CSV FILES
# ---------------------------------------------------------

print("\n" + "=" * 60)
print("SEARCHING FOR METEOSTAT FILES")
print("=" * 60)

meteostat_files = list(METEOSTAT_DIR.rglob("*.csv"))

if meteostat_files:
    print(f"\n✓ Found {len(meteostat_files)} Meteostat CSV files:")

    for file in meteostat_files:
        print("  ✓", file)

else:
    print("\n✗ No Meteostat CSV files found.")

# ---------------------------------------------------------
# FIND ERA5 NETCDF FILES
# ---------------------------------------------------------

print("\n" + "=" * 60)
print("SEARCHING FOR ERA5 NETCDF FILES")
print("=" * 60)

# IMPORTANT:
# rglob searches through ALL subfolders.
# This is necessary because your ERA5 structure contains
# many folders before reaching the actual .nc files.

era5_files = list(ERA5_DIR.rglob("*.nc"))

if era5_files:
    print(f"\n✓ Found {len(era5_files)} ERA5 NetCDF files.")

    print("\nFirst 20 ERA5 files:")

    for file in era5_files[:20]:
        print("  ✓", file)

    if len(era5_files) > 20:
        print(f"\n... and {len(era5_files) - 20} more files.")

else:
    print("\n✗ No ERA5 NetCDF files found.")

# ---------------------------------------------------------
# SUMMARY
# ---------------------------------------------------------

print("\n" + "=" * 60)
print("DATA LOADING COMPLETE")
print("=" * 60)

print(f"\nMeteostat files: {len(meteostat_files)}")
print(f"ERA5 files:      {len(era5_files)}")

if meteostat_files and era5_files:
    print("\n✓ Both datasets were successfully located.")
    print("✓ System is ready for data processing.")

elif meteostat_files:
    print("\n✓ Meteostat data found.")
    print("⚠ ERA5 data was not found.")

elif era5_files:
    print("\n✓ ERA5 data found.")
    print("⚠ Meteostat data was not found.")

else:
    print("\n✗ No weather datasets were found.")

print()