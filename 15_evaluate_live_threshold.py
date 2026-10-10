from pathlib import Path
import numpy as np
import pandas as pd

from sklearn.metrics import (
    precision_score,
    recall_score,
    f1_score,
    confusion_matrix
)


# ============================================================
# EVALUATE LIVE-COMPATIBLE MODEL THRESHOLD
# ============================================================

BASE_DIR = Path(__file__).resolve().parent

MODEL_DIR = (
    BASE_DIR
    / "outputs"
    / "model_live"
)

INPUT_FILE = (
    MODEL_DIR
    / "live_model_test_predictions.csv"
)

RESULTS_FILE = (
    MODEL_DIR
    / "live_threshold_results.csv"
)

THRESHOLD_FILE = (
    MODEL_DIR
    / "live_selected_threshold.txt"
)

UPDATED_PREDICTIONS_FILE = (
    MODEL_DIR
    / "live_test_predictions_with_threshold.csv"
)


print("=" * 70)
print("LIVE-COMPATIBLE THRESHOLD EVALUATION")
print("=" * 70)


# ============================================================
# 1. LOAD TEST PREDICTIONS
# ============================================================

print("\nReading:")
print(INPUT_FILE)


if not INPUT_FILE.exists():

    raise FileNotFoundError(
        f"Prediction file not found:\n{INPUT_FILE}"
    )


df = pd.read_csv(
    INPUT_FILE
)


print(
    f"\nRows: "
    f"{len(df):,}"
)


# ============================================================
# 2. CHECK REQUIRED COLUMNS
# ============================================================

required_columns = [
    "target_storm",
    "live_model_probability"
]


missing_columns = [

    column

    for column in required_columns

    if column not in df.columns
]


if missing_columns:

    raise ValueError(
        f"Missing required columns:\n"
        f"{missing_columns}"
    )


# ============================================================
# 3. CLEAN
# ============================================================

df = df.dropna(
    subset=required_columns
).copy()


df["target_storm"] = (
    df["target_storm"]
    .astype(int)
)


df["live_model_probability"] = (
    df["live_model_probability"]
    .astype(float)
)


print(
    f"Rows available for evaluation: "
    f"{len(df):,}"
)


# ============================================================
# 4. TEST THRESHOLDS
# ============================================================

thresholds = np.arange(
    0.10,
    0.61,
    0.05
)


results = []


for threshold in thresholds:

    predictions = (

        df["live_model_probability"]

        >=

        threshold

    ).astype(int)


    precision = precision_score(
        df["target_storm"],
        predictions,
        zero_division=0
    )


    recall = recall_score(
        df["target_storm"],
        predictions,
        zero_division=0
    )


    f1 = f1_score(
        df["target_storm"],
        predictions,
        zero_division=0
    )


    cm = confusion_matrix(
        df["target_storm"],
        predictions
    )


    results.append(
        {

            "threshold":
                round(
                    float(threshold),
                    2
                ),

            "precision":
                precision,

            "recall":
                recall,

            "f1_score":
                f1,

            "true_negatives":
                cm[0, 0],

            "false_positives":
                cm[0, 1],

            "false_negatives":
                cm[1, 0],

            "true_positives":
                cm[1, 1]
        }
    )


results_df = pd.DataFrame(
    results
)


# ============================================================
# 5. DISPLAY RESULTS
# ============================================================

print("\n" + "=" * 70)
print("THRESHOLD COMPARISON")
print("=" * 70)


display_columns = [

    "threshold",

    "precision",
    "recall",
    "f1_score",

    "false_positives",
    "false_negatives",
    "true_positives"
]


print(

    results_df[
        display_columns
    ]

    .to_string(
        index=False
    )
)


# ============================================================
# 6. BEST F1
# ============================================================

best_f1_row = results_df.loc[
    results_df[
        "f1_score"
    ].idxmax()
]


best_f1_threshold = (
    best_f1_row[
        "threshold"
    ]
)


print("\n" + "=" * 70)
print("BEST F1 THRESHOLD")
print("=" * 70)


print(
    f"\nThreshold: "
    f"{best_f1_threshold:.2f}"
)

print(
    f"Precision: "
    f"{best_f1_row['precision']:.4f}"
)

print(
    f"Recall   : "
    f"{best_f1_row['recall']:.4f}"
)

print(
    f"F1-score : "
    f"{best_f1_row['f1_score']:.4f}"
)


# ============================================================
# 7. HIGH-RECALL OPTION
# ============================================================

minimum_recall = 0.70


high_recall_options = results_df[

    results_df["recall"]

    >=

    minimum_recall

].copy()


if not high_recall_options.empty:

    high_recall_row = (

        high_recall_options

        .sort_values(
            "f1_score",
            ascending=False
        )

        .iloc[0]
    )


    print("\n" + "=" * 70)
    print("HIGH-RECALL OPTION")
    print("=" * 70)


    print(
        f"\nRequired recall: "
        f"{minimum_recall:.2f}"
    )

    print(
        f"Threshold: "
        f"{high_recall_row['threshold']:.2f}"
    )

    print(
        f"Precision: "
        f"{high_recall_row['precision']:.4f}"
    )

    print(
        f"Recall   : "
        f"{high_recall_row['recall']:.4f}"
    )

    print(
        f"F1-score : "
        f"{high_recall_row['f1_score']:.4f}"
    )


# ============================================================
# 8. SELECT THRESHOLD
# ============================================================

# Use best F1 by default.
selected_threshold = (
    best_f1_threshold
)


# ============================================================
# 9. SAVE THRESHOLD
# ============================================================

with open(
    THRESHOLD_FILE,
    "w",
    encoding="utf-8"
) as file:

    file.write(
        f"{selected_threshold:.2f}"
    )


print(
    f"\nSelected threshold: "
    f"{selected_threshold:.2f}"
)


print(
    "Saved to:"
)

print(
    THRESHOLD_FILE
)


# ============================================================
# 10. APPLY SELECTED THRESHOLD
# ============================================================

df["live_threshold_prediction"] = (

    df["live_model_probability"]

    >=

    selected_threshold

).astype(int)


selected_precision = precision_score(
    df["target_storm"],
    df["live_threshold_prediction"],
    zero_division=0
)


selected_recall = recall_score(
    df["target_storm"],
    df["live_threshold_prediction"],
    zero_division=0
)


selected_f1 = f1_score(
    df["target_storm"],
    df["live_threshold_prediction"],
    zero_division=0
)


selected_cm = confusion_matrix(
    df["target_storm"],
    df["live_threshold_prediction"]
)


print("\n" + "=" * 70)
print("SELECTED THRESHOLD PERFORMANCE")
print("=" * 70)


print(
    f"\nThreshold: "
    f"{selected_threshold:.2f}"
)

print(
    f"Precision: "
    f"{selected_precision:.4f}"
)

print(
    f"Recall   : "
    f"{selected_recall:.4f}"
)

print(
    f"F1-score : "
    f"{selected_f1:.4f}"
)


print("\nConfusion matrix:")

print(
    f"True Negatives : "
    f"{selected_cm[0, 0]}"
)

print(
    f"False Positives: "
    f"{selected_cm[0, 1]}"
)

print(
    f"False Negatives: "
    f"{selected_cm[1, 0]}"
)

print(
    f"True Positives : "
    f"{selected_cm[1, 1]}"
)


# ============================================================
# 11. SAVE RESULTS
# ============================================================

results_df.to_csv(
    RESULTS_FILE,
    index=False
)


df.to_csv(
    UPDATED_PREDICTIONS_FILE,
    index=False
)


print("\nFiles created:")

print(
    " -",
    RESULTS_FILE
)

print(
    " -",
    THRESHOLD_FILE
)

print(
    " -",
    UPDATED_PREDICTIONS_FILE
)


print("\n" + "=" * 70)
print("LIVE THRESHOLD EVALUATION COMPLETE")
print("=" * 70)


print(
    "\nNext step:"
)

print(
    "Update the live Open-Meteo prediction script "
    "to use random_forest_live_model.pkl."
)
