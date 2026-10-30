# Model evaluation evidence

The figures on the dashboard's **Risk Analysis** page come from [`model_evidence.json`](model_evidence.json), written by [`25_build_model_evidence.py`](../25_build_model_evidence.py). The script:
- loads the deployed model (`outputs/model_live/random_forest_live_model.pkl`, unchanged);
- re-scores the saved held-out rows and stops if the probabilities differ from the saved ones;
- applies thresholds with the same rule as the live worker: **estimate ≥ threshold means warn**.

Nothing is retrained and the 35% threshold is not changed.

```
python 25_build_model_evidence.py      # needs the local, git-ignored outputs/model_live/*.csv files
```

## 1. What is being measured

| Item | Value |
|---|---|
| Labels | ERA5-derived **proxy** storm labels (`03_create_labels.py`): at least 1 mm of rain **and** CAPE ≥ 200 J/kg, convective rain ≥ 0.5 mm, K-index ≥ 26 or cloud cover ≥ 90%. These are not observed storm reports. |
| Target | The next hour's label (`06_prepare_model_data.py`). |
| Inputs | 29 ERA5 variables. Live operation uses ECMWF forecasts instead, so these results do not measure forecast-driven skill. |
| Held-out test period | 2025-08-25 17:00 to 2026-08-07 22:00 UTC: 30,455 grid-cell hours, 860 labelled storm hours. This is the most recent 20%, not used for training (script 14). |

## 2. Threshold comparison: deployed model, held-out period

| Threshold | Precision | Recall | F1 | False alarms | Missed storm hours | Warnings |
|---|---|---|---|---|---|---|
| 30% | 48.7% | 77.0% | 0.597 | 697 | 198 | 1,359 |
| **35% (in use)** | **51.6%** | **72.0%** | **0.601** | **581** | **241** | **1,200** |
| 40% | 54.5% | 67.3% | 0.602 | 483 | 281 | 1,062 |
| 45% | 56.1% | 61.7% | 0.588 | 416 | 329 | 947 |
| 50% | 59.2% | 55.1% | 0.571 | 327 | 386 | 801 |
| Persistence baseline | 55.9% | 55.9% | 0.559 | 379 | 379 | 860 |

At 35% the confusion matrix is 619 TP, 581 FP, 241 FN and 29,014 TN.

**Selection bias.** The 35% threshold was chosen by comparing F1 on this same period (`15_evaluate_live_threshold.py`), so the 35% row is optimistic. The scores from 30% to 40% are practically equal. 35% is a working setting, not a validated optimum.

**Correction to the saved threshold table.** `live_threshold_results.csv` (local, git-ignored) differs slightly from the table above. For example, at 35% it has 616 TP and 576 FP. Script 15 builds its thresholds with `np.arange(0.10, 0.61, 0.05)`, which produces values such as 0.35000000000000003. The model gives 8 to 10 held-out rows a score of exactly 0.30, 0.35 or 0.40, and those rows were counted as below the threshold. The live worker compares with exactly 0.35 (`probability < 0.35` means no warning), and the table above uses that rule.

**The saved 40% decision file.** `live_test_predictions_with_threshold.csv` (local, git-ignored) is reproduced exactly at 0.40, not 0.35. Script 15 was evidently re-run after 35% was set; the committed `live_selected_threshold.txt` has been 0.35 since the first commit. This was reported and left unchanged.

## 3. Stricter evaluation with a validation year

`evaluation_reports/ml_evaluation_2026-10-29/` (pre-registered design, run on 29 October 2026):
- **Periods:** training 2018 to August 2024, validation August 2024 to August 2025, test August 2025 to August 2026, with 7-day gaps between them. The threshold was chosen on validation only.

| Model (test year, 30,428 cell-hours) | Precision | Recall | F1 | False alarms | Missed |
|---|---|---|---|---|---|
| Same settings retrained on training years only, threshold 0.46 chosen on validation | 56.4% | 58.0% | 0.572 | 385 | 361 |
| Deployed model at 0.46 | 56.8% | 60.6% | 0.586 | 397 | 339 |
| Persistence baseline | 55.9% | 55.9% | 0.559 | 379 | 379 |

The F1 difference from persistence (+0.013, 95% CI −0.029 to +0.047) did not meet the pre-specified criterion for a meaningful improvement. At a validation-selected recall-oriented threshold, the model detected more labelled storm hours than persistence (75% vs. 56%), with lower precision. The deployed model's training period overlaps that validation year, so its row is for reference only.

## 4. Patterns learned (feature importance)

Impurity-based importances from `model.feature_importances_`, with the current and previous hour combined:

| Input group | Share |
|---|---|
| Rainfall (total and convective) | 59.3% |
| Atmospheric instability (CAPE) | 13.8% |
| Wind and gusts | 7.8% |
| Cloud cover | 6.5% |
| Temperature and humidity | 6.3% |
| Air pressure | 3.7% |
| Time of day and season | 2.5% |
| Grid-cell position | 0.1% |

These show what the model relies on, not what causes storms. Rainfall dominates partly because the label itself requires at least 1 mm of rain. Impurity-based importance can also favour some inputs over others.

## 5. Calibration check (assessment only)

The model was not calibrated after training. On the held-out period:

| Score range | Hours | Average score | Labelled storm fraction |
|---|---|---|---|
| 0–5% | 26,933 | 0.3% | 0.1% |
| 5–10% | 1,012 | 7.0% | 3.3% |
| 10–20% | 745 | 13.9% | 9.7% |
| 20–35% | 565 | 26.7% | 19.6% |
| 35–50% | 399 | 42.4% | 36.3% |
| 50–70% | 418 | 59.6% | 47.8% |
| 70–100% | 383 | 80.4% | 71.5% |

The Brier score is 0.0163. In every band the scores are higher than the labelled storm frequency, so a score should be read as a relative risk level, not a calibrated probability. No confidence interval is calculated for a single hour's estimate.

## 6. Why a Random Forest

The model suits tabular hourly weather data with non-linear interactions. It handles rare classes with balanced weights, gives a score that a threshold can be applied to, and reports importances. The project compared it with a persistence baseline, **not** with other machine-learning algorithms, so no claim is made that it is better than other methods.
