# Final research refinement: evidence (30 October 2026)

**Guided by RO3:** to design and develop a smart resilient storm early warning system for low-connectivity environments, using Matatiele as a case study. The RO3 mapping is in [docs/RO3_EVIDENCE.md](../../docs/RO3_EVIDENCE.md).

## 1. Scientific checks

| Check | Result |
|---|---|
| Model, feature list and threshold unchanged | Same content as `origin/main`. Re-scoring 30,455 held-out rows reproduces the saved probabilities (maximum difference 1.1 × 10⁻¹⁶). The threshold is 0.35. See [model_unchanged.json](model_unchanged.json). |
| Threshold table | Recomputed with the live rule (≥ 0.35) in [docs/model_evidence.json](../../docs/model_evidence.json). The saved `live_threshold_results.csv` differs by 8–10 rows because script 15 used floating-point thresholds (0.35000000000000003) and some scores are exactly 0.30, 0.35 or 0.40. See [docs/MODEL_EVALUATION.md](../../docs/MODEL_EVALUATION.md) §2. |
| The 40% decision file | `live_test_predictions_with_threshold.csv` is reproduced only at 0.40. This is a pre-existing artefact; the threshold in use is still 0.35. |
| Validation-year evaluation | F1 0.572 (retrained) and 0.586 (deployed model) against persistence at 0.559; not a meaningful improvement (`evaluation_reports/ml_evaluation_2026-10-29`) |
| Feature importance | Taken from `model.feature_importances_` and checked by a test. Rainfall 59%, CAPE 14%. |
| Calibration | Assessment only: the scores run higher than the labelled frequency in every band. Brier score 0.0163. The model was not changed. |
| Map grid | **Corrected:** the 25 requested points resolve to 25 ECMWF 0.25° cells, 0.25°–0.5° apart (about 24–48 km), not "about 30 km". The model forecast is requested for 30.30° S, 28.80° E, and the model location is the ERA5 cell at 30.25° S, 28.75° E. |
| MQTT and LoRa | No code exists. They are documented as future work. |

## 2. Changes

| Area | Change |
|---|---|
| Home | Subtitle; four summary cards (weather forecast, model-estimated storm risk with gauge, warning decision with genuine-record check, communication status with the real SMS mode and record counts). The large risk panel, large weather card and SAWS button are removed. The SMS button reads "SMS warning service (research prototype)". The actions are View warnings, Safety advice, SMS, emergency contacts and the low-data view. |
| Risk Analysis | Patterns learned (grouped importance chart), why a Random Forest, the threshold comparison 30–50% with persistence, the validation-year evaluation, the confusion matrix, what the percentage means, and a calibration check |
| Forecast | States which forecast hour the model uses, and that it makes one estimate |
| Map | Opens zoomed on Matatiele (zoom 8.6), with an overlay opacity control, a full date and retrieval time in the legend, and the corrected grid description |
| Historical Data | 24 hours / 7 days / all; zoom in time; 35% line with a label; lines break at missing hours (no interpolation); tooltips |
| About | Development vs. operation, an RO3 status table (implemented / simulated / future), the compact disclaimer, and a discreet SAWS link. The SAWS reference is also in the footer. |
| Low-data view | Adds the warning decision and the information status (current / OUT OF DATE) |
| SMS | Simulation (outbox) messages are prefixed `TEST ONLY - NOT A REAL WARNING.`; live wording is unchanged and tested. Adds the reproducible demo `26_sms_simulation_demo.py`. |
| Streamlit menu | Streamlit's ⋮ menu (with its conflicting theme setting) is hidden by CSS; the header switch is the only theme control |

## 3. Demonstrations

- **SMS simulation:** [sms_simulation_output.txt](sms_simulation_output.txt) and [sms_simulation_steps.json](sms_simulation_steps.json). It covers a fictional subscriber, the 62% TEST input against 35%, a warning event, a TEST ONLY SMS with status `outbox`, a re-run with 0 new recipients, a provider timeout (warning kept, delivery `uncertain`) and 20% with no warning. Nothing was sent; network access was blocked.
- **Dashboard in simulation mode:** `screenshots/sms_*`. A fictional subscriber and a labelled development warning were created in a separate demo copy.
- **Connectivity failure:** `screenshots/offline_*`. The server was started with an unreachable proxy, so the forecast refresh failed; the dashboard shows the last known information, labelled out of date, with no warning decision. The automated sequence normal → failure → recovery is `test_connectivity_failure_then_recovery`.

## 4. Screenshots (`screenshots/`)

- `page_<light|dark>_<1440|820|390>_<n><page>.png`: all nine views (Home, Forecast, Map, Safety, Alerts, Risk Analysis, Historical Data, About, low-data) in both themes at desktop, tablet and phone widths (54 images).
- No horizontal overflow on any page at any width, and no SAWS button on Home ([layout_checks_light.json](layout_checks_light.json), [layout_checks_dark.json](layout_checks_dark.json)).
- `sms_light_*`: simulation mode with a fictional subscriber and a labelled development warning. Home shows the amber development-test banner and "SMS records: 1 simulated, not sent". The redacted outbox is in [sms_demo_outbox_redacted.jsonl](sms_demo_outbox_redacted.jsonl), and the warning message begins `TEST ONLY - NOT A REAL WARNING.`
- `offline_light_*`: forecast refresh blocked. The page shows "Outdated data", "Storm risk information is out of date", "Last estimate", "No warning decision: the information is out of date", and the low-data view marked OUT OF DATE.

The Home page shows live ECMWF data from the time of capture (30 October 2026, evening, dry, 0% estimate). The forecast and estimate on the Home page are genuine; the development warning in the `sms_*` images is labelled as such.

## 5. Tests

- **Full suite:** 353 passed (274 subtests), run twice: [test_run1.txt](test_run1.txt), and [test_run2.txt](test_run2.txt) with a process-wide network guard (0 outbound connection attempts).
- **Mocked or local only:** every test. No live forecast call, GitHub ledger call or SMS is made by tests.
- **Live:** only the screenshot servers retrieved genuine ECMWF data from Open-Meteo. The SMS demo blocked the network.
- **Worker equivalence:** 21/21 identical ([equivalence_r3.txt](equivalence_r3.txt)).
- **New tests** (`tests/test_research_refinement.py`):
  - evidence consistency, and importances matching the model file;
  - Risk Analysis wording that avoids over-claiming;
  - the gauge rendered as an image with its value in the alt text;
  - decision and freshness lines in the low-data view;
  - connectivity failure followed by recovery;
  - the SMS simulation (TEST label, `outbox` status, idempotency, provider failure, masked number);
  - unchanged live SMS wording.
- **Corrected test:** the text-view assertion used a wrong element name (`arrow_vega_lite_chart`), so it could never fail.
