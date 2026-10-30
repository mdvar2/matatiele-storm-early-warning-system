# Model evaluation evidence

The figures on the dashboard's **Risk Analysis** page come from [`model_evidence.json`](model_evidence.json), written by [`25_build_model_evidence.py`](../25_build_model_evidence.py). The script:
- loads the deployed model (`outputs/model_live/random_forest_live_model.pkl`, unchanged);
- re-scores the saved held-out rows and stops if the probabilities differ from the saved ones;
- applies thresholds with the same rule as the live worker: **estimate ≥ threshold means warn**.

Nothing is retrained and the 35% threshold is not changed.

```
python 25_build_model_evidence.py --check   # works from a clean checkout; see section 7
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

## 7. Reproducing the evidence

Everything needed to regenerate `docs/model_evidence.json` is committed:

| File | Role | Kind |
|---|---|---|
| `outputs/model_live/random_forest_live_model.pkl`, `live_model_features.txt`, `live_selected_threshold.txt` | Deployed model (unchanged), its 29 inputs, the 35% threshold | Source artefacts |
| `docs/evidence/held_out_test_set.csv.gz` (1.9 MB) | The 30,455 held-out rows: time, the 29 ERA5 inputs, the current and next-hour storm labels, and the probabilities saved at training time. Values were copied as text from the git-ignored `outputs/model_live/live_model_test_predictions.csv`, without re-rounding. | Source artefact |
| `evaluation_reports/ml_evaluation_2026-10-29/` | The validation-year evaluation: design-registered script, configuration, metrics, threshold table, confusion matrices, bootstrap intervals, sensitivity analyses and predictions | Results of a past run (kept as recorded) |
| `docs/model_evidence.json` | Figures shown on the Risk Analysis page | Regenerated |

```
pip install -r requirements.txt               # scikit-learn 1.9.0 is pinned; the model was saved with it
python 25_build_model_evidence.py --check     # recompute everything and confirm the committed JSON; writes nothing
python 25_build_model_evidence.py             # rewrite the JSON
```

`--check` re-scores the held-out rows with the model and stops if the result differs from the saved probabilities. It then rebuilds the threshold comparison, persistence baseline, calibration bins and feature importances, and compares each value with the committed JSON. Software versions are recorded but not compared. The automated tests run `--check`, and it was confirmed from a clean clone of the branch.

**What cannot be regenerated from the repository alone:**
- **ERA5 data:** the model training (scripts 01–14) and the validation-year evaluation (`ro3_chronological_evaluation.py`, which reads `outputs/model_ready.csv`) need the hourly ERA5 single-level reanalysis.
  - It comes from the Copernicus Climate Data Store and needs a free CDS account. The project uses 2018–2026 for the grid cells around Matatiele: 2 m temperature and dew point, sea-level and surface pressure, total and convective precipitation, CAPE, K-index, total cloud cover, 10 m wind components and gusts.
  - It is saved as `data/era5/era5_<year>.nc`, about 96 MB, and is not committed.
  - Running scripts 01–06 rebuilds `outputs/model_ready.csv`.
- **Retraining:** retraining is not required to check the published figures, and retraining with a different library version would not necessarily reproduce the deployed model.
- **The 29 October run:** that evaluation's outputs are committed as recorded and were not re-run or altered.
