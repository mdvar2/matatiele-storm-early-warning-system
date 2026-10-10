from pathlib import Path

import joblib
import pandas as pd

from sklearn.ensemble import RandomForestClassifier
from sklearn.metrics import (
    accuracy_score,
    precision_score,
    recall_score,
    f1_score,
    roc_auc_score,
    average_precision_score,
    confusion_matrix,
    classification_report
)


# ============================================================
# TRAIN LIVE-COMPATIBLE RANDOM FOREST
# ============================================================

BASE_DIR = Path(__file__).resolve().parent

INPUT_FILE = (
    BASE_DIR
    / "outputs"
    / "model_ready.csv"
)

MODEL_DIR = (
    BASE_DIR
    / "outputs"
    / "model_live"
)

MODEL_DIR.mkdir(
    parents=True,
    exist_ok=True
)


MODEL_FILE = (
    MODEL_DIR
    / "random_forest_live_model.pkl"
)

FEATURE_FILE = (
    MODEL_DIR
    / "live_model_features.txt"
)

IMPORTANCE_FILE = (
    MODEL_DIR
    / "live_feature_importance.csv"
)

PREDICTIONS_FILE = (
    MODEL_DIR
    / "live_model_test_predictions.csv"
)


print("=" * 70)
print("TRAINING LIVE-COMPATIBLE RANDOM FOREST")
print("=" * 70)


# ============================================================
# 1. LOAD MODEL-READY DATA
# ============================================================

print("\nReading:")
print(INPUT_FILE)


if not INPUT_FILE.exists():

    raise FileNotFoundError(
        f"Model-ready dataset not found:\n{INPUT_FILE}"
    )


df = pd.read_csv(
    INPUT_FILE
)


print(
    f"\nInput rows: "
    f"{len(df):,}"
)

print(
    f"Input columns: "
    f"{len(df.columns)}"
)


# ============================================================
# 2. CONVERT TIME
# ============================================================

df["valid_time"] = pd.to_datetime(
    df["valid_time"],
    errors="coerce"
)


df = df.dropna(
    subset=[
        "valid_time",
        "target_storm"
    ]
).copy()


df = df.sort_values(
    "valid_time"
).reset_index(drop=True)


print("\nDate range:")

print(
    "Start:",
    df["valid_time"].min()
)

print(
    "End:",
    df["valid_time"].max()
)


# ============================================================
# 3. DEFINE TARGET
# ============================================================

TARGET = "target_storm"


df[TARGET] = (
    df[TARGET]
    .astype(int)
)


print("\nTarget distribution:")

print(
    df[TARGET]
    .value_counts()
    .sort_index()
)


# ============================================================
# 4. DEFINE EXCLUDED COLUMNS
# ============================================================

# These columns must not be used as model inputs.

EXCLUDE_COLUMNS = [

    "valid_time",

    "storm_label",
    "storm_status",

    "target_storm",

    # Open-Meteo live ECMWF feed did not provide K Index.
    # We intentionally remove both current and previous K Index
    # so the deployed model does not depend on fake fallback
    # values.

    "kx",
    "previous_kx"
]


# ============================================================
# 5. BUILD LIVE-COMPATIBLE FEATURE LIST
# ============================================================

FEATURE_COLUMNS = [

    column

    for column in df.columns

    if column not in EXCLUDE_COLUMNS
]


print("\nLive-compatible features:")

for feature in FEATURE_COLUMNS:
    print(" -", feature)


print(
    f"\nNumber of live-compatible features: "
    f"{len(FEATURE_COLUMNS)}"
)


# ============================================================
# 6. VERIFY K INDEX IS GONE
# ============================================================

if "kx" in FEATURE_COLUMNS:

    raise ValueError(
        "kx was not removed from the model features."
    )


if "previous_kx" in FEATURE_COLUMNS:

    raise ValueError(
        "previous_kx was not removed from the model features."
    )


# ============================================================
# 7. REMOVE ROWS WITH MISSING MODEL FEATURES
# ============================================================

model_columns = (
    FEATURE_COLUMNS
    +
    [TARGET]
)


print("\nMissing values before modelling:")

missing_values = (
    df[model_columns]
    .isna()
    .sum()
)


print(
    missing_values[
        missing_values > 0
    ]
)


before_cleaning = len(df)


df = df.dropna(
    subset=model_columns
).copy()


after_cleaning = len(df)


print(
    f"\nRows removed because of missing values: "
    f"{before_cleaning - after_cleaning:,}"
)

print(
    f"Rows available for modelling: "
    f"{after_cleaning:,}"
)


# ============================================================
# 8. BUILD X AND y
# ============================================================

X = df[
    FEATURE_COLUMNS
].copy()


y = df[
    TARGET
].astype(int)


# ============================================================
# 9. CHRONOLOGICAL TRAIN / TEST SPLIT
# ============================================================

split_index = int(
    len(df)
    *
    0.80
)


X_train = X.iloc[
    :split_index
].copy()


X_test = X.iloc[
    split_index:
].copy()


y_train = y.iloc[
    :split_index
].copy()


y_test = y.iloc[
    split_index:
].copy()


train_times = df[
    "valid_time"
].iloc[
    :split_index
]


test_times = df[
    "valid_time"
].iloc[
    split_index:
]


print("\n" + "=" * 70)
print("CHRONOLOGICAL TRAIN / TEST SPLIT")
print("=" * 70)


print(
    f"\nTraining rows: "
    f"{len(X_train):,}"
)

print(
    f"Testing rows: "
    f"{len(X_test):,}"
)


print("\nTraining period:")

print(
    "Start:",
    train_times.min()
)

print(
    "End:",
    train_times.max()
)


print("\nTesting period:")

print(
    "Start:",
    test_times.min()
)

print(
    "End:",
    test_times.max()
)


# ============================================================
# 10. CLASS BALANCE
# ============================================================

print("\nTraining target distribution:")

print(
    y_train
    .value_counts()
    .sort_index()
)


print("\nTesting target distribution:")

print(
    y_test
    .value_counts()
    .sort_index()
)


print("\nTraining percentages:")

print(
    (
        y_train
        .value_counts(
            normalize=True
        )
        .sort_index()
        *
        100
    )
)


# ============================================================
# 11. CREATE RANDOM FOREST
# ============================================================

print("\n" + "=" * 70)
print("CREATING LIVE-COMPATIBLE RANDOM FOREST")
print("=" * 70)


model = RandomForestClassifier(

    n_estimators=300,

    max_depth=None,

    min_samples_split=2,

    min_samples_leaf=1,

    class_weight="balanced",

    random_state=42,

    n_jobs=-1
)


print("\nModel configuration:")

print(
    "Algorithm: Random Forest"
)

print(
    "Trees:",
    model.n_estimators
)

print(
    "Class weighting:",
    model.class_weight
)

print(
    "K Index used: NO"
)


# ============================================================
# 12. TRAIN MODEL
# ============================================================

print("\nTraining model...")


model.fit(
    X_train,
    y_train
)


print(
    "Training complete."
)


# ============================================================
# 13. TEST PREDICTIONS
# ============================================================

print(
    "\nMaking test predictions..."
)


y_pred = model.predict(
    X_test
)


y_probability = (
    model.predict_proba(
        X_test
    )[:, 1]
)


# ============================================================
# 14. EVALUATION
# ============================================================

accuracy = accuracy_score(
    y_test,
    y_pred
)


precision = precision_score(
    y_test,
    y_pred,
    zero_division=0
)


recall = recall_score(
    y_test,
    y_pred,
    zero_division=0
)


f1 = f1_score(
    y_test,
    y_pred,
    zero_division=0
)


roc_auc = roc_auc_score(
    y_test,
    y_probability
)


pr_auc = average_precision_score(
    y_test,
    y_probability
)


print("\n" + "=" * 70)
print("LIVE-COMPATIBLE MODEL PERFORMANCE")
print("=" * 70)


print(
    f"\nAccuracy : {accuracy:.4f}"
)

print(
    f"Precision: {precision:.4f}"
)

print(
    f"Recall   : {recall:.4f}"
)

print(
    f"F1-score : {f1:.4f}"
)

print(
    f"ROC-AUC  : {roc_auc:.4f}"
)

print(
    f"PR-AUC   : {pr_auc:.4f}"
)


# ============================================================
# 15. CONFUSION MATRIX
# ============================================================

cm = confusion_matrix(
    y_test,
    y_pred
)


print("\nConfusion matrix:")

print(
    f"True Negatives : "
    f"{cm[0, 0]}"
)

print(
    f"False Positives: "
    f"{cm[0, 1]}"
)

print(
    f"False Negatives: "
    f"{cm[1, 0]}"
)

print(
    f"True Positives : "
    f"{cm[1, 1]}"
)


# ============================================================
# 16. CLASSIFICATION REPORT
# ============================================================

print("\nClassification report:")


print(

    classification_report(

        y_test,

        y_pred,

        target_names=[
            "No Storm",
            "Storm"
        ],

        zero_division=0
    )
)


# ============================================================
# 17. FEATURE IMPORTANCE
# ============================================================

importance = pd.DataFrame(

    {

        "feature":
            FEATURE_COLUMNS,

        "importance":
            model.feature_importances_
    }

)


importance = importance.sort_values(

    "importance",

    ascending=False

).reset_index(
    drop=True
)


print("\n" + "=" * 70)
print("LIVE MODEL FEATURE IMPORTANCE")
print("=" * 70)


print(
    importance.to_string(
        index=False
    )
)


# ============================================================
# 18. SAVE FEATURE IMPORTANCE
# ============================================================

importance.to_csv(
    IMPORTANCE_FILE,
    index=False
)


# ============================================================
# 19. SAVE EXACT FEATURE LIST
# ============================================================

with open(
    FEATURE_FILE,
    "w",
    encoding="utf-8"
) as file:

    for feature in FEATURE_COLUMNS:

        file.write(
            feature
            +
            "\n"
        )


# ============================================================
# 20. SAVE MODEL
# ============================================================

joblib.dump(
    model,
    MODEL_FILE
)


# ============================================================
# 21. SAVE TEST PREDICTIONS
# ============================================================

test_results = df.iloc[
    split_index:
].copy()


test_results[
    "live_model_prediction"
] = y_pred


test_results[
    "live_model_probability"
] = y_probability


test_results.to_csv(
    PREDICTIONS_FILE,
    index=False
)


# ============================================================
# 22. FINAL SUMMARY
# ============================================================

print("\n" + "=" * 70)
print("LIVE-COMPATIBLE RANDOM FOREST TRAINING COMPLETE")
print("=" * 70)


print("\nFiles created:")

print(
    " -",
    MODEL_FILE
)

print(
    " -",
    FEATURE_FILE
)

print(
    " -",
    IMPORTANCE_FILE
)

print(
    " -",
    PREDICTIONS_FILE
)


print("\nImportant:")

print(
    "This model intentionally excludes "
    "kx and previous_kx."
)


print("\nNext step:")

print(
    "Evaluate and tune the decision threshold "
    "for this live-compatible model."
)
