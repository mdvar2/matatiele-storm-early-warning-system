from pathlib import Path

import pandas as pd
import joblib


# ---------------------------------------------------------
# PATHS
# ---------------------------------------------------------

BASE_DIR = Path(__file__).resolve().parent

MODEL_FILE = (
    BASE_DIR /
    "models" /
    "storm_random_forest.pkl"
)

FEATURE_FILE = (
    BASE_DIR /
    "models" /
    "model_features.txt"
)

INPUT_FILE = (
    BASE_DIR /
    "outputs" /
    "storm_features.csv"
)


# ---------------------------------------------------------
# LOAD MODEL
# ---------------------------------------------------------

model = joblib.load(
    MODEL_FILE
)


# ---------------------------------------------------------
# LOAD FEATURE LIST
# ---------------------------------------------------------

with open(
    FEATURE_FILE,
    "r"
) as file:

    features = [
        line.strip()
        for line in file
        if line.strip()
    ]


# ---------------------------------------------------------
# LOAD WEATHER DATA
# ---------------------------------------------------------

df = pd.read_csv(
    INPUT_FILE
)


# ---------------------------------------------------------
# PREPARE FEATURES
# ---------------------------------------------------------

X = df[features].copy()


X = X.fillna(
    X.median(numeric_only=True)
)

X = X.fillna(0)


# ---------------------------------------------------------
# PREDICT
# ---------------------------------------------------------

predictions = model.predict(
    X
)


probabilities = model.predict_proba(
    X
)


# Probability of Storm

storm_probability = probabilities[:, 1]


# ---------------------------------------------------------
# ADD RESULTS
# ---------------------------------------------------------

df["predicted_storm"] = predictions

df["storm_probability"] = (
    storm_probability
)

df["predicted_status"] = (
    df["predicted_storm"]
    .map(
        {
            0: "NO STORM",
            1: "STORM"
        }
    )
)


# ---------------------------------------------------------
# SAVE
# ---------------------------------------------------------

output_file = (
    BASE_DIR /
    "outputs" /
    "storm_predictions.csv"
)


df.to_csv(
    output_file,
    index=False
)


# ---------------------------------------------------------
# DISPLAY LATEST PREDICTION
# ---------------------------------------------------------

latest = df.iloc[-1]


print("======================================")
print("STORM PREDICTION")
print("======================================")


print(
    f"Time: {latest.get('time', 'Unknown')}"
)

print(
    f"Prediction: {latest['predicted_status']}"
)

print(
    f"Storm probability: "
    f"{latest['storm_probability'] * 100:.2f}%"
)


print(
    f"\nSaved to: {output_file}"
)