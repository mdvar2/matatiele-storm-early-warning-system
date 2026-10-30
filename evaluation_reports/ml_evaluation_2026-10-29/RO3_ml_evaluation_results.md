# RO3 Machine Learning Evaluation: Results

**Evaluation:** chronological training / validation / test evaluation of the Random Forest storm model
**Design:** `evaluation_reports/RO3_ml_evaluation_design_2026-10-29.md` (pre-registered 29 Oct 2026; approved by the researcher before this run)
**Run:** 29 October 2026, 15:18–15:20 SAST; single run, 105.5 s
**Script:** `ro3_chronological_evaluation.py` (this folder)

> **Scope of every result in this report.** All performance figures measure agreement with **ERA5-derived proxy storm labels** (a rule applied to reanalysis rainfall, instability and cloud variables). They measure how well the model reproduces that rule one hour ahead, using **ERA5 reanalysis inputs**. They are **not** measures of accuracy against **independently observed storm events**, and **not** measures of the operational system's skill with live ECMWF forecasts.

---

## 1. Summary of findings

| # | Finding | Favourable / unfavourable |
|---|---|---|
| 1 | On the test period, the new train-only model (M1) at its validation-selected threshold (0.46) scored **F1 = 0.572** [95% CI 0.512–0.629], against **0.559** [0.501–0.610] for persistence. | — |
| 2 | **The pre-registered criterion for meaningful improvement over persistence was NOT met.** F1 difference +0.013, 95% CI [−0.029, +0.047]: below the 0.05 margin, and the interval includes zero. | **Unfavourable** |
| 3 | The model's probabilities give a large improvement over chance ranking (PR-AUC 0.576 vs. a no-skill level of 0.028; Brier skill score 0.39 relative to training climatology). | Favourable |
| 4 | At the pre-specified recall-oriented threshold (0.30, chosen on validation), M1 detected **74.9%** of storm-hours against persistence's 55.9% (recall +0.19 [+0.14, +0.24]). The cost was lower precision (−0.07 [−0.10, −0.05]), about **1.8 times as many false alarms**. F1 improved by +0.029 [+0.008, +0.053]: statistically above zero but **below the 0.05 margin**. | Mixed |
| 5 | The deployed model (M2) at the a-priori threshold of 0.46 scored F1 = 0.586 [0.531–0.636]. Its advantage over persistence, +0.027 [+0.0001, +0.053], also falls **short of the margin**. | Unfavourable |
| 6 | The deployed threshold 0.35, tuned on this test period during development, gives F1 = 0.601 for the deployed model. This figure is **optimistic** and must not be reported as validated. Under an a-priori threshold, the figure is 0.586. | Unfavourable (for earlier claims) |
| 7 | Results are stable: across five random seeds, the selected threshold ranged 0.40–0.46, test F1 0.562–0.579, and PR-AUC 0.569–0.577. Validation and test F1 for M1 were almost identical (0.571 vs. 0.572), with no sign of over-fitting to the validation year. | Favourable (reliability) |
| 8 | The gap between M1 and persistence (0.013 F1) is **smaller than the spread across random seeds** (0.017 F1). | Unfavourable |
| 9 | Accuracy is uninformative: every classifier, including always-negative (0.972), falls within 0.970–0.977. | — |

**Overall:** the Random Forest reproduces the ERA5 proxy storm label one hour ahead about as well as simple persistence ("the next hour will be like this hour"). Its demonstrable added value is the ability to trade precision for recall: at a recall-oriented threshold it detects substantially more labelled storm-hours than persistence, at the cost of more false alarms. Under the pre-registered criterion, it does **not** meaningfully outperform persistence in F1.

## 2. Protocol adherence and deviations

| Item | Status |
|---|---|
| Periods, embargoes, model configuration, threshold rules, metrics, bootstrap, criterion and sensitivity analyses | Executed exactly as approved |
| Decisions revised after seeing results | **None** |
| Code check before the run | A smoke run (5-tree forest, 20 resamples, output to a temporary folder outside the project, no metrics displayed) confirmed the script executes. The script was not changed between the smoke run and the real run. |
| Prior inspection of the test period | **Disclosed:** deployed-model and persistence results for essentially this test period were computed and discussed during the research audit (29 Oct 2026) before this design was written. The methodology was fixed before this run, but the test period is **not an untouched hold-out**. |
| Isolation | Twilio, GitHub and SMS-activation variables removed from the process. Outbound network blocked and logged (**0 attempts**). SHA-256 of 91 project files identical before and after. No model file saved. |

## 3. Data periods (UTC; all four grid cells at a timestamp kept in the same period)

| Period | First timestamp | Last timestamp | Rows | Timestamps | Positives | Rate | Storm-hours | Storm-days |
|---|---|---|---|---|---|---|---|---|
| Training | 2018-01-01 01:00 | 2024-08-11 23:00 | 85,460 | 56,159 | 1,961 | 2.29% | 1,521 | 443 |
| *Embargo A (excluded)* | 2024-08-12 00:00 | 2024-08-18 23:00 | 672 | 168 | 0 | — | — | — |
| Validation | 2024-08-19 00:00 | 2025-08-18 23:00 | 35,040 | 8,760 | 1,027 | 2.93% | 483 | 111 |
| *Embargo B (excluded)* | 2025-08-19 00:00 | 2025-08-25 23:00 | 672 | 168 | 0 | — | — | — |
| Test | 2025-08-26 00:00 | 2026-08-07 22:00 | 30,428 | 7,607 | 860 | 2.83% | 391 | 90 |

- Training contains 46,392 single-cell timestamps (cell −30.25, 28.75 only, until June 2023) and 9,767 four-cell timestamps. Validation and test are entirely four-cell.
- The test period has no June 2026 data (missing from the source).

## 4. Models and configuration

| ID | Description |
|---|---|
| **M1 (primary)** | New `RandomForestClassifier` trained on the **training period only**. Configuration copied from the deployed model: `n_estimators=300, max_depth=None, min_samples_split=2, min_samples_leaf=1, max_features='sqrt', class_weight='balanced', bootstrap=True, criterion='gini', random_state=42, n_jobs=-1`. The same 29 features as deployment (`live_model_features.txt`). Not saved. |
| **M2 (secondary)** | **Deployed** model (`random_forest_live_model.pkl`, unchanged), trained by script 14 on all data up to 2025-08-25 17:00. Its existing saved test probabilities were used; nothing was selected from them. |
| B1 | Always-negative |
| B2 | Persistence: `target_storm(t+1)` predicted by `storm_label(t)` in the same cell |

## 5. Threshold selection (validation period, M1 only)

- Grid 0.01–0.99 in steps of 0.01; rule `probability ≥ threshold`.
- **Primary (maximum validation F1, ties to the higher threshold): 0.46**, with validation F1 0.571.
- **Secondary (recall ≥ 0.70, then maximum F1): 0.30**, with validation recall 0.706 and F1 0.546.

Validation F1 near the optimum (full table: `validation_threshold_table.csv`):

| Threshold | Precision | Recall | F1 |
|---|---|---|---|
| 0.30 | 0.445 | 0.706 | 0.546 |
| 0.35 | 0.479 | 0.671 | 0.559 |
| 0.40 | 0.515 | 0.631 | 0.567 |
| 0.45 | 0.553 | 0.586 | 0.569 |
| **0.46** | **0.563** | **0.579** | **0.571** |
| 0.50 | 0.589 | 0.537 | 0.562 |
| 0.55 | 0.623 | 0.489 | 0.548 |

The F1 curve is flat between 0.40 and 0.50 (a range of 0.009), so the exact optimum is weakly determined.

## 6. Test-period results

### 6.1 Main comparison (with 95% block-bootstrap CIs)

| Classifier | Precision | Recall (POD) | F1 | CSI | FAR | Accuracy | Bal. acc. |
|---|---|---|---|---|---|---|---|
| **M1 @ 0.46 (primary)** | 0.565 [0.501, 0.624] | 0.580 [0.506, 0.647] | **0.572 [0.512, 0.629]** | 0.401 [0.345, 0.459] | 0.436 [0.376, 0.500] | 0.976 | 0.784 |
| M2 deployed @ 0.46 | 0.568 [0.506, 0.624] | 0.606 [0.546, 0.658] | 0.586 [0.531, 0.636] | 0.415 [0.361, 0.466] | 0.433 [0.376, 0.494] | 0.976 | 0.796 |
| **B2 persistence** | 0.559 [0.501, 0.611] | 0.559 [0.501, 0.610] | **0.559 [0.501, 0.610]** | 0.388 [0.335, 0.438] | 0.441 [0.389, 0.499] | 0.975 | 0.773 |
| B1 always-negative | undefined | 0.000 | 0.000 | 0.000 | undefined | 0.972 | 0.500 |

### 6.2 Threshold-free metrics

| Model | ROC-AUC | PR-AUC (average precision) | PR-AUC no-skill level | Brier | Brier skill vs. training climatology |
|---|---|---|---|---|---|
| M1 | 0.980 [0.974, 0.985] | 0.576 [0.501, 0.647] | 0.028 | 0.0167 | 0.393 |
| M2 deployed | 0.981 [0.974, 0.985] | 0.589 [0.515, 0.657] | 0.028 | 0.0163 | 0.405 |

The high ROC-AUC partly reflects the large number of easily classified dry hours. PR-AUC is the more informative measure under this class imbalance. Persistence is a yes/no rule, so it has no ROC or PR curve to compare.

### 6.3 Confusion matrices (test, 30,428 rows; 860 positives)

| Classifier | TN | FP | FN | TP | Warnings issued |
|---|---|---|---|---|---|
| M1 @ 0.46 (primary) | 29,183 | 385 | 361 | 499 | 884 |
| M1 @ 0.30 (recall ≥ 0.70 rule) | 28,884 | 684 | 216 | 644 | 1,328 |
| M1 @ 0.35 (reference) | 28,995 | 573 | 275 | 585 | 1,158 |
| M1 @ 0.50 (reference) | 29,247 | 321 | 401 | 459 | 780 |
| M2 deployed @ 0.46 | 29,171 | 397 | 339 | 521 | 918 |
| M2 deployed @ 0.35 (test-tuned; optimistic) | 28,987 | 581 | 241 | 619 | 1,200 |
| M2 deployed @ 0.50 (reference) | 29,241 | 327 | 386 | 474 | 801 |
| B2 persistence | 29,189 | 379 | 379 | 481 | 860 |
| B1 always-negative | 29,568 | 0 | 860 | 0 | 0 |

Counts are cell-hours, and the four cells are strongly correlated. A "warning" here means a positive classification for one cell-hour, not an SMS.

### 6.4 Paired differences from persistence (same bootstrap resamples)

| Comparison | ΔF1 | ΔRecall | ΔPrecision | ΔCSI |
|---|---|---|---|---|
| **M1 @ 0.46 − persistence (pre-registered test)** | **+0.013 [−0.029, +0.047]** | +0.021 [−0.053, +0.084] | +0.005 [−0.018, +0.029] | +0.013 [−0.028, +0.047] |
| M1 @ 0.30 − persistence | +0.029 [+0.008, +0.053] | **+0.190 [+0.139, +0.242]** | −0.074 [−0.099, −0.047] | +0.029 [+0.008, +0.051] |
| M2 deployed @ 0.46 − persistence | +0.027 [+0.000, +0.053] | +0.047 [−0.002, +0.092] | +0.008 [−0.016, +0.034] | +0.026 [+0.000, +0.051] |
| M2 deployed @ 0.35 − persistence (optimistic) | +0.042 [+0.024, +0.062] | +0.161 [+0.126, +0.198] | −0.044 [−0.066, −0.017] | +0.041 [+0.023, +0.061] |

### 6.5 Pre-registered criterion

| Requirement | Result |
|---|---|
| ΔF1 (M1 − persistence) ≥ 0.05 | **No** (0.013) |
| 95% CI of ΔF1 excludes zero, on the positive side | **No** ([−0.029, +0.047]) |
| **Meaningful improvement demonstrated** | **No** |

No comparison in §6.4, including the optimistic test-tuned reference, reaches the 0.05 F1 margin.

### 6.6 Does the selected threshold improve on the baselines?

- **Against always-negative:** yes, trivially. F1 rises from 0 to 0.57, and 58% of labelled storm-hours are detected. Accuracy is essentially unchanged, which shows why accuracy is unsuitable here.
- **Against persistence:** **no meaningful improvement at the primary threshold.** Precision, recall, F1 and CSI are all within about 0.02 of persistence, with intervals overlapping zero.
- **At the recall-oriented threshold (0.30):** the model detects 163 more of the 860 labelled storm-hours than persistence (644 vs. 481), with 305 more false positives (684 vs. 379). That is a **different operating point** rather than a uniformly better one. Whether it is preferable is a policy choice about the cost of missed warnings versus false alarms, not something the F1 criterion establishes.

## 7. Sensitivity analyses (pre-specified)

### 7.1 Reference thresholds (not selected on test)

| Threshold | M1 F1 | M2 deployed F1 | Note |
|---|---|---|---|
| 0.46 (validation primary) | 0.572 | 0.586 | Valid a-priori choice |
| 0.35 (deployed) | 0.580 | **0.601** | For M2, **tuned on this test period**: optimistic |
| 0.50 (default) | 0.560 | 0.571 | — |

The deployed 0.35 threshold is **not** the F1-optimal threshold on independent validation data, which gives 0.46 for M1. It lies between the F1-optimal and recall-oriented validation thresholds. The paper should therefore justify 0.35 as a recall-favouring policy choice, not as an optimised value.

### 7.2 Single grid cell (−30.25, 28.75), test period (7,607 rows, 236 positives)

| Classifier | Precision | Recall | F1 | CSI | TN | FP | FN | TP | PR-AUC |
|---|---|---|---|---|---|---|---|---|---|
| M1 @ 0.46 | 0.587 | 0.589 | 0.588 | 0.416 | 7,273 | 98 | 97 | 139 | 0.586 |
| M2 deployed @ 0.46 | 0.589 | 0.606 | 0.597 | 0.426 | 7,271 | 100 | 93 | 143 | 0.603 |
| B2 persistence | 0.581 | 0.581 | 0.581 | 0.409 | 7,272 | 99 | 99 | 137 | — |
| B1 always-negative | — | 0.000 | 0.000 | 0.000 | 7,371 | 0 | 236 | 0 | — |

The same conclusion holds for the only cell present throughout training. M1 exceeds persistence by 0.007 F1 (2 more true positives out of 236).

### 7.3 Seed stability (M1 retrained with different random seeds; threshold re-selected on validation each time)

| Seed | Validation-selected threshold | Test F1 | Test PR-AUC | Test ROC-AUC |
|---|---|---|---|---|
| 42 (primary) | 0.46 | 0.572 | 0.576 | 0.980 |
| 1 | 0.44 | 0.576 | 0.577 | 0.980 |
| 2 | 0.45 | 0.562 | 0.569 | 0.979 |
| 3 | 0.40 | 0.579 | 0.571 | 0.980 |
| 4 | 0.44 | 0.568 | 0.570 | 0.979 |
| **Range** | **0.40–0.46** | **0.562–0.579** | **0.569–0.577** | **0.979–0.980** |

Performance is reproducible across seeds. The seed-to-seed F1 range (0.017) exceeds the primary F1 gain over persistence (0.013).

### 7.4 Validation-period consistency

| Classifier (validation) | Precision | Recall | F1 |
|---|---|---|---|
| M1 @ 0.46 (threshold chosen on this period) | 0.563 | 0.579 | 0.571 |
| B2 persistence | 0.563 | 0.563 | 0.563 |

The same pattern appears in an independent season: a small, non-meaningful margin over persistence.

## 8. Methodological limitations (Phase 3)

1. **ERA5-derived proxy storm labels.** The target is a rule: hourly ERA5 precipitation ≥ 1 mm, together with CAPE ≥ 200 J/kg, convective precipitation ≥ 0.5 mm, K-index ≥ 26, or cloud cover ≥ 90% ([03_create_labels.py:91-130](../../03_create_labels.py#L91-L130)), shifted one hour ahead ([06_prepare_model_data.py:201-204](../../06_prepare_model_data.py#L201-L204)). The thresholds are not validated against observed storms. A "storm" in this evaluation is a modelled rainy, convective-looking hour, not a confirmed thunderstorm, hail or wind event.
2. **Circularity and the strength of persistence.** The current-hour ingredients of the label (tp, cp, cape, tcc) are model features. The model can largely reconstruct the current label and carry it forward, which explains why persistence is hard to beat. Beating persistence would show forecasting value beyond the current state; this evaluation shows little such value.
3. **Temporal dependence.** Storm-hours cluster into multi-hour, multi-day events. The test period has 860 positive cell-hours but only 391 distinct storm-hours over 90 storm-days. The 7-day moving-block bootstrap (46 blocks) accounts for this partially; with so few blocks, the confidence intervals are approximate.
4. **Spatial dependence.** The four neighbouring 0.25° cells are highly correlated and do not count as independent observations; they are resampled together. Training is dominated by one cell (2018–mid-2023), while validation and test use four. The single-cell analysis gives the same conclusion.
5. **Class imbalance.** About 2.3–2.9% of rows are positive. Accuracy (0.970–0.977 for every classifier, including always-negative) is uninformative, and ROC-AUC is inflated by easy negatives. PR-AUC, F1, CSI and FAR are the meaningful measures.
6. **Possible leakage (training/validation).**
   - Controlled: whole-day period boundaries, 7-day embargoes, no shared timestamps (asserted), threshold chosen only on validation, a train-only model, no fitted preprocessing.
   - Remaining:
     - The deployed model (M2) was trained on the validation year, so its results are not fully comparable.
     - The researchers had already seen deployed-model results for this test period (§2).
     - The validation-derived threshold was applied to M2, a model trained on more data, which shifts its probability calibration.
7. **Single-season validation and test.** Each covers one wet season (2024/25 and 2025/26). Year-to-year variation, such as ENSO phases or unusually wet or dry seasons, is not captured.
8. **Historical ERA5 inputs vs. operational ECMWF forecasts.** Here both features and labels come from ERA5 reanalysis, which has the benefit of hindsight. The deployed system uses ECMWF IFS forecasts via Open-Meteo, with `showers` substituted for convective precipitation and no K-index, at a different grid point and with forecast error. **Operational skill is expected to be lower than reported here and has not been measured.**
9. **No independent observations.** No observed storm reports, lightning detections or validated station records were used. The Meteostat files were excluded after the provenance investigation. **This evaluation therefore does not establish prediction accuracy against independently observed storms.** It establishes only how well the model reproduces an ERA5-derived proxy label.

## 9. Implications for RO3

- The evaluation provides **reproducible, leakage-controlled evidence** of the model's behaviour against its training target. That strengthens the methodological quality of RO3.
- It shows that the earlier headline results (F1 ≈ 0.60 at 0.35) were **optimistic** because the threshold was selected on the test data. The defensible a-priori figures are F1 0.57 (M1) and 0.59 (deployed model).
- It shows **no meaningful F1 improvement over persistence** under the pre-registered criterion. The supportable claim is narrower: the model provides calibrated probabilities that allow a higher-recall operating point than persistence, at a measurable false-alarm cost.
- Claims of "accurate storm prediction" are **not supported**. Neither independent storm observations nor operational forecast inputs were evaluated.

## 10. Suggested text for the Results section

> A chronological evaluation was conducted with training (Jan 2018 – Aug 2024), validation (Aug 2024 – Aug 2025) and test (Aug 2025 – Aug 2026) periods separated by 7-day embargoes. All grid cells sharing a timestamp were assigned to the same period, and the protocol was pre-registered before the run; the test period had been inspected during an earlier audit. A Random Forest with the deployed configuration was trained on the training period only, and its threshold was selected by maximising F1 on validation data (0.46). Against ERA5-derived proxy storm labels on the test period (30,428 cell-hours, 860 positive), the model achieved F1 = 0.57 (95% block-bootstrap CI 0.51–0.63), recall 0.58, precision 0.56 and PR-AUC 0.58 (no-skill 0.03). A persistence baseline achieved F1 = 0.56 (0.50–0.61). The F1 difference (+0.013, 95% CI −0.029 to +0.047) did not meet the pre-specified criterion for meaningful improvement (≥ 0.05, with a CI excluding zero). At a validation-selected recall-oriented threshold (0.30), the model detected 75% of labelled storm-hours against 56% for persistence (Δrecall +0.19, CI +0.14 to +0.24), at the cost of lower precision (0.48 vs. 0.56). The deployed model, evaluated at the a-priori threshold, gave F1 = 0.59; the previously reported F1 of 0.60 relied on a threshold tuned on the test data. Results were stable across five random seeds (F1 0.56–0.58). These results quantify agreement with a reanalysis-derived label using reanalysis inputs. They do not measure accuracy against independently observed storms or the skill of the operational forecast-driven system.

## 11. Reproducibility

**Command** (from the project root; the run used the same isolation as the automated tests):
```bash
python evaluation_reports/ml_evaluation_2026-10-29/ro3_chronological_evaluation.py
```

- **Environment:** Python 3.12.10, numpy 2.5.3, pandas 3.0.6, scikit-learn 1.9.0, joblib 1.6.0, Windows 11.
- **Inputs (read-only):** `outputs/model_ready.csv`, `outputs/model_live/live_model_features.txt`, `outputs/model_live/random_forest_live_model.pkl` (parameters only), `outputs/model_live/live_model_test_predictions.csv`. SHA-256 values are recorded in `config.json` and verified unchanged.
- **Fixed seeds:** RF 42 (and 1–4 for the sensitivity analysis); bootstrap 20261029.

| File | Content |
|---|---|
| `ro3_chronological_evaluation.py` | Evaluation script |
| `config.json` | Full configuration, selected thresholds, criterion result, input hashes, versions |
| `period_summary.csv` | Period counts and date ranges |
| `validation_threshold_table.csv` | Validation metrics at all 99 thresholds |
| `test_metrics.csv` | Point metrics for all classifiers (test and validation) |
| `confusion_matrices.csv` | Confusion matrices |
| `bootstrap_ci.csv` | 95% CIs and paired differences |
| `sensitivity_single_cell.csv`, `sensitivity_seed_stability.csv` | Sensitivity analyses |
| `predictions_validation_test.csv.gz` | M1 probabilities (validation and test) and deployed probabilities (test) |
| `run_log.txt`, `evidence/` | Console log, network-guard log (empty), project file hashes before and after (identical), network-guard source |

**Not changed:** deployed model, 0.35 threshold, dashboard, scheduled worker, SMS code, datasets, prediction files and earlier reports.
