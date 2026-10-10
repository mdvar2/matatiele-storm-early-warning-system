import pandas as pd
import numpy as np
from pathlib import Path

from sklearn.metrics import (
    precision_score,
    recall_score,
    f1_score,
    confusion_matrix
)


# ============================================================
# EVALUATE STORM DECISION THRESHOLD
# ============================================================

BASE_DIR = Path(__file__).resolve().parent

INPUT_FILE = (
    BASE_DIR /
    "outputs" /
    "model" /
    "test_predictions.csv"
)

OUTPUT_DIR = (
    BASE_DIR /
    "outputs" /
    "model"
)

OUTPUT_DIR.mkdir(
    parents=True,
    exist_ok=True
)

RESULTS_FILE = (
    OUTPUT_DIR /
    "threshold_results.csv"
)

SELECTED_THRESHOLD_FILE = (
    OUTPUT_DIR /
    "selected_threshold.txt"
)


print("=" * 60)
print("STORM PREDICTION THRESHOLD EVALUATION")
print("=" * 60)

print("\nReading:")
print(INPUT_FILE)


# ============================================================
# 1. LOAD TEST PREDICTIONS
# ============================================================

df = pd.read_csv(
    INPUT_FILE
)

print("\nInput rows:", len(df))
print("Input columns:", len(df.columns))


# ============================================================
# 2. CHECK REQUIRED COLUMNS
# ============================================================

required_columns = [
    "target_storm",
    "storm_probability"
]

for column in required_columns:

    if column not in df.columns:
        raise ValueError(
            f"Required column '{column}' was not found."
        )


# ============================================================
# 3. REMOVE MISSING VALUES
# ============================================================

df = df.dropna(
    subset=[
        "target_storm",
        "storm_probability"
    ]
).copy()

df["target_storm"] = (
    df["target_storm"]
    .astype(int)
)

df["storm_probability"] = (
    df["storm_probability"]
    .astype(float)
)


print("\nRows available for threshold evaluation:", len(df))


# ============================================================
# 4. ORIGINAL 0.50 THRESHOLD
# ============================================================

print("\n" + "=" * 60)
print("CURRENT DEFAULT THRESHOLD")
print("=" * 60)

default_threshold = 0.50

default_prediction = (
    df["storm_probability"] >= default_threshold
).astype(int)

default_precision = precision_score(
    df["target_storm"],
    default_prediction,
    zero_division=0
)

default_recall = recall_score(
    df["target_storm"],
    default_prediction,
    zero_division=0
)

default_f1 = f1_score(
    df["target_storm"],
    default_prediction,
    zero_division=0
)

default_cm = confusion_matrix(
    df["target_storm"],
    default_prediction
)

print(f"\nThreshold: {default_threshold:.2f}")
print(f"Precision: {default_precision:.4f}")
print(f"Recall   : {default_recall:.4f}")
print(f"F1-score : {default_f1:.4f}")

print("\nConfusion matrix:")

print(
    f"True Negatives : {default_cm[0, 0]}"
)

print(
    f"False Positives: {default_cm[0, 1]}"
)

print(
    f"False Negatives: {default_cm[1, 0]}"
)

print(
    f"True Positives : {default_cm[1, 1]}"
)


# ============================================================
# 5. TEST MULTIPLE THRESHOLDS
# ============================================================

thresholds = np.arange(
    0.10,
    0.61,
    0.05
)

results = []


for threshold in thresholds:

    predictions = (
        df["storm_probability"] >= threshold
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
            "threshold": round(
                float(threshold),
                2
            ),
            "precision": precision,
            "recall": recall,
            "f1_score": f1,
            "true_negatives": cm[0, 0],
            "false_positives": cm[0, 1],
            "false_negatives": cm[1, 0],
            "true_positives": cm[1, 1]
        }
    )


results_df = pd.DataFrame(
    results
)


# ============================================================
# 6. DISPLAY RESULTS
# ============================================================

print("\n" + "=" * 60)
print("THRESHOLD COMPARISON")
print("=" * 60)

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
    results_df[display_columns]
    .to_string(index=False)
)


# ============================================================
# 7. FIND BEST F1 THRESHOLD
# ============================================================

best_f1_row = results_df.loc[
    results_df["f1_score"].idxmax()
]

best_f1_threshold = (
    best_f1_row["threshold"]
)


print("\n" + "=" * 60)
print("BEST F1 THRESHOLD")
print("=" * 60)

print(
    f"\nThreshold: {best_f1_threshold:.2f}"
)

print(
    f"Precision: {best_f1_row['precision']:.4f}"
)

print(
    f"Recall   : {best_f1_row['recall']:.4f}"
)

print(
    f"F1-score : {best_f1_row['f1_score']:.4f}"
)


# ============================================================
# 8. FIND HIGH-RECALL THRESHOLD
# ============================================================

# For a storm-warning system we want to avoid missing storms.
#
# We therefore look for the lowest threshold that achieves
# at least 70% recall while still maintaining reasonable
# precision.

minimum_recall = 0.70

high_recall_options = results_df[
    results_df["recall"] >= minimum_recall
].copy()


if not high_recall_options.empty:

    # Among thresholds achieving the required recall,
    # select the one with the highest F1 score.

    best_high_recall_row = (
        high_recall_options
        .sort_values(
            "f1_score",
            ascending=False
        )
        .iloc[0]
    )

    high_recall_threshold = (
        best_high_recall_row["threshold"]
    )

    print("\n" + "=" * 60)
    print("HIGH-RECALL THRESHOLD")
    print("=" * 60)

    print(
        f"\nRequired recall: {minimum_recall:.2f}"
    )

    print(
        f"Threshold: {high_recall_threshold:.2f}"
    )

    print(
        f"Precision: "
        f"{best_high_recall_row['precision']:.4f}"
    )

    print(
        f"Recall   : "
        f"{best_high_recall_row['recall']:.4f}"
    )

    print(
        f"F1-score : "
        f"{best_high_recall_row['f1_score']:.4f}"
    )

else:

    high_recall_threshold = None

    print("\n" + "=" * 60)
    print("HIGH-RECALL THRESHOLD")
    print("=" * 60)

    print(
        f"\nNo tested threshold achieved "
        f"{minimum_recall:.0%} recall."
    )


# ============================================================
# 9. SAVE ALL THRESHOLD RESULTS
# ============================================================

results_df.to_csv(
    RESULTS_FILE,
    index=False
)

print("\nThreshold results saved to:")
print(RESULTS_FILE)


# ============================================================
# 10. SELECT FINAL THRESHOLD
# ============================================================

# For now, use the best F1 threshold.
#
# We are NOT changing the Random Forest itself.
# We are only changing the probability required
# before the system declares "Storm".

selected_threshold = best_f1_threshold


with open(
    SELECTED_THRESHOLD_FILE,
    "w",
    encoding="utf-8"
) as file:

    file.write(
        f"{selected_threshold:.2f}"
    )


print("\nSelected threshold:")
print(
    f"{selected_threshold:.2f}"
)

print("\nSaved to:")
print(SELECTED_THRESHOLD_FILE)


# ============================================================
# 11. APPLY SELECTED THRESHOLD
# ============================================================

df["threshold_prediction"] = (
    df["storm_probability"] >= selected_threshold
).astype(int)


selected_precision = precision_score(
    df["target_storm"],
    df["threshold_prediction"],
    zero_division=0
)

selected_recall = recall_score(
    df["target_storm"],
    df["threshold_prediction"],
    zero_division=0
)

selected_f1 = f1_score(
    df["target_storm"],
    df["threshold_prediction"],
    zero_division=0
)


print("\n" + "=" * 60)
print("SELECTED THRESHOLD PERFORMANCE")
print("=" * 60)

print(
    f"\nThreshold: {selected_threshold:.2f}"
)

print(
    f"Precision: {selected_precision:.4f}"
)

print(
    f"Recall   : {selected_recall:.4f}"
)

print(
    f"F1-score : {selected_f1:.4f}"
)


# ============================================================
# 12. SAVE UPDATED TEST PREDICTIONS
# ============================================================

UPDATED_PREDICTIONS_FILE = (
    OUTPUT_DIR /
    "test_predictions_with_threshold.csv"
)

df.to_csv(
    UPDATED_PREDICTIONS_FILE,
    index=False
)

print("\nUpdated predictions saved to:")
print(UPDATED_PREDICTIONS_FILE)


# ============================================================
# COMPLETE
# ============================================================

print("\n" + "=" * 60)
print("THRESHOLD EVALUATION COMPLETE")
print("=" * 60)

print("\nFiles created:")

print(
    " -",
    RESULTS_FILE
)

print(
    " -",
    SELECTED_THRESHOLD_FILE
)

print(
    " -",
    UPDATED_PREDICTIONS_FILE
)

print("\nNext step:")
print(
    "Review the threshold results and select the "
    "threshold appropriate for the storm-warning system."
)