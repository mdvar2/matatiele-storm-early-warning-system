import pandas as pd
import numpy as np
from pathlib import Path

from sklearn.ensemble import RandomForestClassifier
from sklearn.metrics import (
    classification_report,
    confusion_matrix,
    accuracy_score,
    precision_score,
    recall_score,
    f1_score,
    roc_auc_score,
    average_precision_score
)
import joblib


# ============================================================
# TRAIN RANDOM FOREST MODEL
# ============================================================

BASE_DIR = Path(__file__).resolve().parent

INPUT_FILE = (
    BASE_DIR /
    "outputs" /
    "model_ready.csv"
)

MODEL_DIR = (
    BASE_DIR /
    "outputs" /
    "model"
)

MODEL_DIR.mkdir(
    parents=True,
    exist_ok=True
)

MODEL_FILE = (
    MODEL_DIR /
    "random_forest_storm_model.pkl"
)

FEATURE_FILE = (
    MODEL_DIR /
    "model_features.txt"
)


print("=" * 60)
print("RANDOM FOREST STORM PREDICTION")
print("=" * 60)

print("\nReading:")
print(INPUT_FILE)


# ============================================================
# 1. LOAD DATA
# ============================================================

df = pd.read_csv(INPUT_FILE)

print("\nInput rows:", len(df))
print("Input columns:", len(df.columns))


# ============================================================
# 2. CONVERT TIME
# ============================================================

df["valid_time"] = pd.to_datetime(
    df["valid_time"],
    errors="coerce"
)

df = df.dropna(
    subset=["valid_time"]
)

df = df.sort_values(
    "valid_time"
).reset_index(drop=True)


print("\nDate range:")
print("Start:", df["valid_time"].min())
print("End:", df["valid_time"].max())


# ============================================================
# 3. CHECK TARGET
# ============================================================

TARGET = "target_storm"

if TARGET not in df.columns:
    raise ValueError(
        f"Target column '{TARGET}' was not found."
    )

print("\nTarget counts:")
print(
    df[TARGET]
    .value_counts()
    .sort_index()
)


# ============================================================
# 4. REMOVE ROWS WITH MISSING VALUES
# ============================================================

before = len(df)

df = df.dropna()

after = len(df)

print("\nRows removed because of missing values:", before - after)
print("Rows available for modelling:", after)


# ============================================================
# 5. DEFINE FEATURES
# ============================================================

# These columns identify the observation or contain the
# current/previous storm label.
#
# storm_label is excluded because the model is predicting
# target_storm (the next-hour storm condition).

EXCLUDE_COLUMNS = [
    "valid_time",
    "storm_label",
    "storm_status",
    "target_storm"
]

FEATURE_COLUMNS = [
    column
    for column in df.columns
    if column not in EXCLUDE_COLUMNS
]

print("\nFeatures used by the model:")

for feature in FEATURE_COLUMNS:
    print(" -", feature)

print("\nNumber of features:", len(FEATURE_COLUMNS))


# ============================================================
# 6. CREATE X AND y
# ============================================================

X = df[FEATURE_COLUMNS]

y = df[TARGET].astype(int)


# ============================================================
# 7. CHRONOLOGICAL TRAIN / TEST SPLIT
# ============================================================

# Use the first 80% of the timeline for training and the
# final 20% for testing.

split_index = int(
    len(df) * 0.80
)

X_train = X.iloc[:split_index]
X_test = X.iloc[split_index:]

y_train = y.iloc[:split_index]
y_test = y.iloc[split_index:]

train_times = df["valid_time"].iloc[:split_index]
test_times = df["valid_time"].iloc[split_index:]


print("\n" + "=" * 60)
print("CHRONOLOGICAL TRAIN / TEST SPLIT")
print("=" * 60)

print("\nTraining rows:", len(X_train))
print("Testing rows:", len(X_test))

print("\nTraining period:")
print("Start:", train_times.min())
print("End:", train_times.max())

print("\nTesting period:")
print("Start:", test_times.min())
print("End:", test_times.max())


# ============================================================
# 8. CHECK CLASS BALANCE
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

print("\nTraining target percentages:")

print(
    (
        y_train
        .value_counts(normalize=True)
        .sort_index()
        * 100
    )
)


# ============================================================
# 9. CREATE RANDOM FOREST
# ============================================================

print("\n" + "=" * 60)
print("CREATING RANDOM FOREST")
print("=" * 60)

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

print("Algorithm: Random Forest")
print("Trees:", model.n_estimators)
print("Class weighting:", model.class_weight)
print("Random state:", model.random_state)


# ============================================================
# 10. TRAIN MODEL
# ============================================================

print("\nTraining model...")

model.fit(
    X_train,
    y_train
)

print("Training complete.")


# ============================================================
# 11. MAKE PREDICTIONS
# ============================================================

print("\nMaking predictions...")

y_pred = model.predict(
    X_test
)

y_probability = model.predict_proba(
    X_test
)[:, 1]


# ============================================================
# 12. MODEL PERFORMANCE
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


print("\n" + "=" * 60)
print("MODEL PERFORMANCE")
print("=" * 60)

print(f"\nAccuracy : {accuracy:.4f}")
print(f"Precision: {precision:.4f}")
print(f"Recall   : {recall:.4f}")
print(f"F1-score : {f1:.4f}")
print(f"ROC-AUC  : {roc_auc:.4f}")
print(f"PR-AUC   : {pr_auc:.4f}")


# ============================================================
# 13. CONFUSION MATRIX
# ============================================================

cm = confusion_matrix(
    y_test,
    y_pred
)

print("\n" + "=" * 60)
print("CONFUSION MATRIX")
print("=" * 60)

print("\n              Predicted")
print("              No Storm   Storm")
print(
    f"Actual No Storm  {cm[0, 0]:8d} {cm[0, 1]:7d}"
)
print(
    f"Actual Storm     {cm[1, 0]:8d} {cm[1, 1]:7d}"
)


# ============================================================
# 14. CLASSIFICATION REPORT
# ============================================================

print("\n" + "=" * 60)
print("CLASSIFICATION REPORT")
print("=" * 60)

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
# 15. FEATURE IMPORTANCE
# ============================================================

importance = pd.DataFrame(
    {
        "feature": FEATURE_COLUMNS,
        "importance": model.feature_importances_
    }
)

importance = importance.sort_values(
    "importance",
    ascending=False
)

print("\n" + "=" * 60)
print("FEATURE IMPORTANCE")
print("=" * 60)

print(
    importance
    .to_string(index=False)
)


# ============================================================
# 16. SAVE FEATURE IMPORTANCE
# ============================================================

importance_file = (
    MODEL_DIR /
    "feature_importance.csv"
)

importance.to_csv(
    importance_file,
    index=False
)

print("\nFeature importance saved to:")
print(importance_file)


# ============================================================
# 17. SAVE MODEL FEATURES
# ============================================================

with open(
    FEATURE_FILE,
    "w",
    encoding="utf-8"
) as file:

    for feature in FEATURE_COLUMNS:
        file.write(
            feature + "\n"
        )

print("\nModel features saved to:")
print(FEATURE_FILE)


# ============================================================
# 18. SAVE TRAINED MODEL
# ============================================================

joblib.dump(
    model,
    MODEL_FILE
)

print("\nTrained model saved to:")
print(MODEL_FILE)


# ============================================================
# 19. SAVE TEST PREDICTIONS
# ============================================================

predictions = df.iloc[
    split_index:
].copy()

predictions["predicted_storm"] = y_pred

predictions["storm_probability"] = y_probability

predictions_file = (
    MODEL_DIR /
    "test_predictions.csv"
)

predictions.to_csv(
    predictions_file,
    index=False
)

print("\nTest predictions saved to:")
print(predictions_file)


# ============================================================
# COMPLETE
# ============================================================

print("\n" + "=" * 60)
print("RANDOM FOREST TRAINING COMPLETE")
print("=" * 60)

print("\nFiles created:")

print(" -", MODEL_FILE)
print(" -", FEATURE_FILE)
print(" -", importance_file)
print(" -", predictions_file)

print("\nNext step:")
print("Evaluate the model and tune the storm decision threshold.")
