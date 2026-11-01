# Final UI Refinement: Evidence (31 October 2026)

**Guided by RO3:** to design and develop a smart resilient storm early warning system for low-connectivity environments, using Matatiele as a case study.

These are presentation and wording changes only. The model, its 29 inputs, the 35% threshold, forecast retrieval, warning decisions, SMS configuration, authentication, warning records and acknowledgement storage are unchanged (§3).

## 1. Changes

| Area | Change |
|---|---|
| Home | The redundant green "NO WARNING IN EFFECT" card is removed from the page. A red banner still appears only when a genuine warning is in effect, and an amber one for a labelled development test. The risk card shows the model estimate, risk category, prediction period, model update time and **Warning threshold: 35%**, with an expandable "Why 35%?" note and a **Threshold details** link to Risk Analysis. **View warnings** and the **Low-data view** link sit beside SMS registration and the emergency contacts. |
| Scientific wording | Text now distinguishes the *weather forecast* (ECMWF via Open-Meteo), the *model-estimated storm risk* (Random Forest) and the *warning decision* (35%). The Forecast page states that the system does not produce weather forecasts. "Forecast period" becomes "Prediction period", and "one forecast point" becomes "one model location". |
| Threshold | Risk Analysis has an "About the 35% warning threshold" section with the agreed text, plus how it was set. The threshold script compared 10–60% by F1 on the held-out period; 30–40% scored almost the same; 35% is a working setting, **not an independently validated optimum**. |
| Map | The title, basemap selector and forecast-hour slider form one compact band, so the map starts higher. The legend now names the actual quantity: *forecast rainfall in mm in the hour, from the ECMWF IFS 0.25° forecast at 25 real grid points about 30 km apart, interpolated and smoothed*. It separates this from the ring showing *model-estimated storm risk at Matatiele (one location)*. The data is unchanged. |
| About | The diagram is the resident workflow: **External forecast → Random Forest → 35% warning decision → Warning information → SMS communication** (optional, with its real state). It has no Officials tile, is compact, and stacks vertically on phones. Two expandable sections: **How the model and system work** (nine steps, verified against scripts 01–15 and the evaluation reports, with no performance figures) and **Designed for low connectivity** (low-data view, SMS, low-data map, and what is *not* claimed: offline operation, sensors, LoRa). |
| Emergency contacts | The resident-facing note is now: "Calls connect to emergency services, not to the Matatiele Storm Early Warning System." Numbers and tap-to-call are unchanged. |
| README | Rewritten around RO3, the forecast / model / decision distinction, the verified model facts, the threshold caveat, the dashboard, low-connectivity features, SMS and its limitations, the officials' portal, installation, testing and known limitations. |

## 2. Before and after (`screenshots/<before|after>_<theme>_<width>_<page>.png`)

Home, Forecast, Map, Risk Analysis and About, in light and dark, at 1440, 820 and 390 px (60 images). The checks were measured identically before and after ([before](before_light.json), [after](after_light.json)):

| Check | Before | After |
|---|---|---|
| Green "NO WARNING IN EFFECT" card on Home (all 6 views) | present | **absent** |
| "Officials" in the About diagram | present | **absent** |
| Map visible without scrolling: desktop / tablet / phone | 441 / 396 / 113 px | **496 / 423 / 159 px** |
| Horizontal overflow on any affected page | none | none |

## 3. Model and warning logic unchanged

[`verify_model_unchanged.py`](verify_model_unchanged.py) → [`model_unchanged.json`](model_unchanged.json):
- The model file, feature list and threshold file have the same content as `main`. Only the line endings differ in the two text files.
- Re-scoring all **30,455** held-out rows reproduces the saved probabilities (largest difference 1.1 × 10⁻¹⁶, floating-point rounding) and the saved class predictions exactly.
- The threshold in use is **0.35**.

The worker equivalence check is **21/21 identical**. The changes to `official_portal.py` and `warning_events.py` are three display labels only.

**Finding (pre-existing, not changed):** the local, git-ignored evaluation file `live_test_predictions_with_threshold.csv` is reproduced exactly at **0.40**, not 0.35. This matches the saved threshold table, where 40% has a marginally higher F1 (0.601 vs 0.600 at 35%). The threshold script was evidently re-run after 35% was set; the committed setting remained 35%. The README and dashboard therefore describe 35% as the setting in use, not as the best F1 result.

## 4. Tests

- **Full suite:** **344 passed, 274 subtests**, run twice ([1](full_regression_run1.txt), [2](full_regression_run2.txt)). No network access was used and no SMS was sent.
- **Covered:**
  - the officials' portal (sign-in, review and history);
  - SMS registration and the worker;
  - the theme switch and its persistence;
  - no duplicated components;
  - no emoji.
- **New or updated tests:**
  - the green card is absent and the risk card remains;
  - the threshold explanation appears on Home and Risk Analysis, makes no claim of an optimum, and the threshold file still says 0.35;
  - the About diagram is five steps with no Officials tile, has an optional SMS step, and stacks on phones;
  - the model and low-connectivity explanations are present;
  - the emergency note has no dates or sources.

## 5. Remaining limitations

- **Phone map position:** the header still sits above the map, so only the top 159 px of the map shows without scrolling.
- **Tablet controls:** the controls take two slim rows.
- **Wording:** "Live forecast data" in the status strip refers to the latest retrieval of external forecast data.
- **Streamlit's ⋮ menu:** its separate theme option can still conflict with the header switch.
