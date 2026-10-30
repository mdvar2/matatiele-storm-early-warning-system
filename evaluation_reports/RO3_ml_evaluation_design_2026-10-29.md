# RO3 Machine Learning Evaluation — Design and Pre-registration

**Status:** PROPOSED. Awaiting researcher approval. **No model has been trained and no metric has been calculated under this design.**
**Date:** 29 October 2026
**Purpose:** a reproducible chronological train / validation / test evaluation of the Random Forest storm model, with the decision threshold chosen on validation data only, and without modifying the deployed prototype.

This document fixes the evaluation method *before* results are seen. Any later deviation must be reported as a deviation.

---

## 1. Inspection findings that shape the design

| # | Finding | Evidence | Consequence |
|---|---|---|---|
| F1 | The deployed model is `RandomForestClassifier(n_estimators=300, max_depth=None, min_samples_split=2, min_samples_leaf=1, max_features='sqrt', class_weight='balanced', bootstrap=True, criterion='gini', random_state=42)`, with 29 features | Parameters read from `outputs/model_live/random_forest_live_model.pkl`; [14_train_live_compatible_random_forest.py:423](../14_train_live_compatible_random_forest.py#L423); `live_model_features.txt` | The evaluation model reuses this configuration exactly. No hyperparameter tuning. |
| F2 | The deployed model was trained on the first 80% of rows: 121,817 rows, 2018-01-01 01:00 → 2025-08-25 17:00 UTC | Replication of the split in [14:294](../14_train_live_compatible_random_forest.py#L294); the replicated test rows match `live_model_test_predictions.csv` exactly (30,455 rows) | **The deployed model has seen every label before 25 Aug 2025**, including any candidate validation year. Its predictions there are in-sample and **cannot be used for threshold selection**. |
| F3 | The existing split divides the timestamp **2025-08-25 17:00 UTC**: 1 grid-cell row in training, 3 in test | Same replication | The existing split breaks the requirement that all cells at a timestamp share a period. The new design uses whole UTC days. |
| F4 | The deployed threshold 0.35 was selected by maximising F1 **on the test predictions** | [15_evaluate_live_threshold.py:270-372](../15_evaluate_live_threshold.py#L270-L372) | 0.35 must not be presented as validated. It is reported only as a reference. |
| F5 | Spatial coverage changes: 1 cell (−30.25, 28.75) until 2023-06-30; **4 cells from 2023-07-01 01:00 UTC** | `outputs/model_ready.csv` | Training is dominated by one cell; validation and test contain all four. A single-cell sensitivity analysis is required. |
| F6 | Missing months: 2018-07, 2021-06, 2026-06 | `outputs/model_ready.csv` | June 2026 (dry season) is absent from the test period; reported as a limitation. |
| F7 | The test period has already been examined: deployed-model and persistence metrics were computed during the audit on 29 Oct 2026 | Audit (chat) | The test set is not fully "unseen" by the researchers. Mitigated by fixing every analysis choice in this document before the new evaluation is run. |

**Does a model trained with test-period labels invalidate the evaluation?**
- The deployed model was **not** trained on test-period labels. Its training ends at 2025-08-25 17:00 UTC, before the proposed test start of 2025-08-26 00:00 UTC.
- It **was** trained on the proposed validation labels. Using it to select a threshold would therefore be invalid.
- The primary evaluation uses a **new model trained on the training period only**, so the deployed model's training history cannot leak into threshold selection or testing.

## 2. Proposed periods (UTC, whole days, all four cells kept together)

| Period | Start (inclusive) | End (exclusive) | Rows | Timestamps | Positives | Positive rate | Distinct storm-hours | Storm-days |
|---|---|---|---|---|---|---|---|---|
| **Training** | 2018-01-01 01:00 | 2024-08-12 00:00 | 85,460 | 56,159 (46,392 one-cell, 9,767 four-cell) | 1,961 | 2.29% | 1,521 | 443 |
| Embargo A (excluded) | 2024-08-12 00:00 | 2024-08-19 00:00 | 672 | 168 | 0 | 0% | 0 | 0 |
| **Validation** | 2024-08-19 00:00 | 2025-08-19 00:00 | 35,040 | 8,760 (all four-cell) | 1,027 | 2.93% | 483 | 111 |
| Embargo B (excluded) | 2025-08-19 00:00 | 2025-08-26 00:00 | 672 | 168 | 0 | 0% | 0 | 0 |
| **Test** | 2025-08-26 00:00 | 2026-08-07 23:00 (last row 22:00) | 30,428 | 7,607 (all four-cell) | 860 | 2.83% | 391 | 90 |

**Rationale:**
- Validation and test each contain exactly one full wet season (Oct–Mar).
- The test period is the deployed model's original test period, trimmed to a whole-day start (28 rows from 25 Aug removed). This keeps it comparable with earlier results, and the deployed model never saw these labels.
- Each 7-day embargo stops the training target (t+1) and lagged features from crossing a boundary, and reduces autocorrelation between periods. Both embargo weeks fall in the dry season and contain no positives.
- Before training, the script will assert that no timestamp appears in more than one period.

## 3. Models evaluated

| ID | Model | Trained on | Threshold | Role |
|---|---|---|---|---|
| **M1** | New RF, configuration identical to deployed (F1), same 29 features | **Training period only** | Selected on **validation** (rule §4) | **Primary result** |
| M2 | Deployed RF (existing artefact, not retrained) | Deployed training data (F2) | M1's validation-selected threshold, fixed in advance | Secondary: performance of the actual prototype under an a-priori threshold. It uses the saved test probabilities without choosing anything from them. Caveat: the threshold transfers between differently trained models. |
| M2-ref | Deployed RF | Deployed training data | 0.35 (test-tuned) | Reference only, labelled "threshold selected on test data; optimistic" |
| B1 | Always-negative baseline | — | — | Accuracy floor |
| B2 | Persistence: predict `storm_label(t)` for `target_storm` (t+1) | — | — | Skill benchmark |

M1 is **not** refitted on training plus validation data. M2 already represents such a refit, being trained on all pre-test data with the same configuration.

## 4. Threshold-selection rule (validation data, M1 only)

- **Grid:** 0.01 to 0.99 in steps of 0.01. Values are generated as exact decimals (`np.round(k/100, 2)`) to avoid the floating-point problem identified in the audit. Decision rule: `probability ≥ threshold`.
- **Primary rule:** the threshold that maximises F1 on validation. Ties are broken by the **higher** threshold, giving fewer alarms.
- **Secondary rule (sensitivity):** among thresholds with validation recall ≥ 0.70, the one with the highest F1, matching the project's existing recall-oriented rule ([08_evaluate_threshold.py:303-326](../08_evaluate_threshold.py#L303-L326)).
- The full validation threshold table is saved. **The test set is never used to choose or adjust anything.**

## 5. Metrics (test period; validation metrics also reported)

- **Counts:** observations, positives, storm-hours, storm-days, and the exact date range for each period.
- **Threshold-dependent:** accuracy, balanced accuracy, precision, recall (probability of detection), F1, false-alarm ratio, critical success index, and the confusion matrix (TN, FP, FN, TP).
- **Threshold-free (M1, M2):** ROC-AUC, PR-AUC (average precision; the reference value equals prevalence), and Brier score (reference: climatological prevalence from training).
- **Baselines** B1 and B2 are reported with the same threshold-dependent metrics.

## 6. Uncertainty and the "meaningful improvement" criterion

- **Confidence intervals:** moving-block bootstrap over **contiguous 7-day blocks** of the test period. All hours and all four cells in a block are resampled together, preserving temporal and spatial dependence. B = 2,000 resamples, seed 20261029, percentile 95% intervals.
- **Paired comparisons:** the difference M1 − B2 (persistence) in F1, recall, precision and CSI is computed on the same bootstrap resamples.
- **Pre-specified criterion:** M1 counts as *meaningfully better than persistence* only if **both** hold:
  1. The 95% CI of the F1 difference (M1 − B2) excludes 0.
  2. The point difference is at least **0.05 F1**.
- Otherwise the improvement is reported as not demonstrated.
- **Caveat:** about 46 blocks makes the intervals approximate. That is stated alongside them.

## 7. Pre-specified sensitivity analyses

1. **Single cell:** the evaluation restricted to cell (−30.25, 28.75), the only cell present in all periods.
2. **Recall-constrained threshold:** the secondary rule in §4.
3. **M1 at the default 0.50 threshold**, for comparison with the audit.
4. **Seed stability:** M1 retrained with 4 additional random seeds (1–4) on the same training data. Report the range of the validation-selected threshold and of test F1, PR-AUC and ROC-AUC. This shows how much results depend on randomness rather than data.

No other analyses will be presented as results. Any further exploration will be labelled post hoc.

## 8. Leakage controls

| Risk | Control |
|---|---|
| Same timestamp in two periods | Whole-day boundaries; assertion in the script |
| Target (t+1) or lagged features crossing a boundary | 7-day embargoes |
| Threshold chosen on test | Validation-only selection; the test is evaluated once |
| Deployed model's knowledge of validation labels | M1 trained from scratch on training only; M2 is never used for selection |
| Preprocessing fitted on future data | None is fitted: features are raw ERA5 values and lags. `class_weight='balanced'` is computed from the training data inside the fit. |
| Feature leakage of the label | `storm_label`, `storm_status`, `target_storm`, `kx` and `previous_kx` are excluded, as in deployment ([14:164-179](../14_train_live_compatible_random_forest.py#L164-L179)). The current-hour ingredients of the label (tp, cp, cape, tcc) remain as features, as deployed. This is a known circularity, discussed in §10, not a leak of t+1. |

## 9. Implementation plan (after approval)

**Files read (read-only):**
- `outputs/model_ready.csv` — model-ready dataset; not regenerated.
- `outputs/model_live/live_model_features.txt` — the 29-feature list.
- `outputs/model_live/live_model_test_predictions.csv` — deployed-model test probabilities, for M2 only.
- `outputs/model_live/random_forest_live_model.pkl` — **parameters only**, to confirm the configuration. It is never refitted or saved.

**New files (written only to `evaluation_reports/ml_evaluation_2026-10-29/`):**

| File | Content |
|---|---|
| `ro3_chronological_evaluation.py` | Evaluation script, standalone |
| `config.json` | Periods, seeds, grid, rules, library versions, SHA-256 of the input files |
| `period_summary.csv` | Counts and date ranges per period |
| `validation_threshold_table.csv` | Every grid threshold with validation metrics |
| `predictions_validation_test.csv.gz` | M1 probabilities for validation and test (no model file saved) |
| `test_metrics.csv`, `bootstrap_ci.csv`, `sensitivity.csv` | Results |
| `RO3_ml_evaluation_results.md` | Results report, including the Phase 3 limitations |

**Runtime:** roughly 1–3 minutes per RF fit (85k rows, 300 trees, all cores), so about 5–15 minutes in total including the seed-stability fits.

**No changes** to the deployed model, threshold, dashboard, worker, SMS code, prediction files or existing reports. No network access.

## 10. Limitations to be reported with the results (Phase 3)

1. **Proxy labels.** The target is an ERA5 rule (≥ 1 mm/h rain plus CAPE, convective-precipitation, K-index or cloud indicator), not observed storms. Every metric measures how well the model reproduces this rule one hour ahead.
2. **Circularity.** The label's ingredients at time t are features, so the model largely learns to carry the labelling rule forward one hour. Persistence is therefore a strong baseline.
3. **Temporal dependence.** Storm hours cluster into multi-hour events. With 391 storm-hours over 90 storm-days in the test period, the effective sample is far smaller than 30,428 rows. Block bootstrapping addresses this only partly.
4. **Spatial dependence.** The four adjacent 0.25° cells are highly correlated and do not add four independent observations. Training is dominated by a single cell (F5).
5. **Class imbalance.** About 2.3–2.9% positives. Accuracy is uninformative (always-negative scores about 97%), so PR-AUC, F1 and CSI are emphasised.
6. **Single-season validation and test.** One wet season each; inter-annual variability is not captured. The seed and sensitivity analyses help but do not substitute for more seasons.
7. **Residual leakage risks.** Embargoes reduce, but do not eliminate, dependence between periods. Researchers have already seen deployed-model test results (F7).
8. **Reanalysis vs. operational forecasts.** Inputs here are ERA5 reanalysis. The deployed system uses ECMWF IFS forecasts via Open-Meteo, with substitute variables (e.g., `showers` for convective precipitation, no K-index). Operational skill is expected to be lower, and this evaluation does not measure it.
9. **No independent observations.** No observed storm reports, lightning or validated station data are used (the Meteostat files were excluded after the provenance investigation). **This evaluation does not establish prediction accuracy against independently observed storms.**

---

**Approval requested:** periods (§2), models (§3), threshold rules (§4), metrics (§5), the improvement criterion (§6), sensitivity analyses (§7) and the implementation plan (§9).
