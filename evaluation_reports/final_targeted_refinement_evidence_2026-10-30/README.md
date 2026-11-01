# Final targeted refinement: evidence (30 October 2026)

These are presentation and reproducibility changes only. The model, its 29 inputs, the 35% threshold, warning generation, the SMS simulation and low-connectivity handling are unchanged:
- [model_unchanged.json](model_unchanged.json): same content as `main`, and 30,455 held-out rows re-scored exactly;
- [equivalence_r3.txt](equivalence_r3.txt): worker equivalence 21/21.

## Changes

| Area | Change |
|---|---|
| Home | The emergency contacts panel is replaced by an **Emergency contacts** button next to View warnings and Safety advice. With an active warning, a **Safety and emergency contacts** button appears beside **Open the warning**. |
| Safety | New **Emergency contacts** section after the safety advice: three compact tap-to-call cards (10111, 10177, 112) side by side, stacked on phones, with the existing note. The shortcuts scroll it into view. |
| Low-data view | Lists the emergency numbers as plain text, noting that calls need mobile network coverage |
| Home communication card | Three indicators derived by `resident_alerts.communication_status`: Dashboard alerts (Available / Warning record unreachable), SMS simulation (Available / Active on this deployment / Unavailable), Public SMS delivery (Disabled / Controlled test only) |
| Alerts, SMS alerts | New **SMS service status** block: configuration, simulation, public registration, delivery limitations, research-test restrictions and real record counts |
| About | **Warning threshold · 35% · Model-risk score required to trigger a warning decision.** (was "Warning level · Next-hour estimate") |
| Disclaimer link | Dark brown #6b2f00 on #fff5dc (light) and #ffe08a on #3d3216 (dark), both at least 7:1 contrast, with a visible hover and keyboard-focus outline |
| Wording | The Risk Analysis subtitle and the resident manual say "35% warning threshold" instead of "warning level" |

## Browser checks ([light](browser_checks_light.json), [dark](browser_checks_dark.json))

At 1440, 820 and 390 px, in both themes:
- no horizontal overflow on Home, Safety, About or Alerts (SMS);
- no contacts panel on Home;
- after the Home shortcut, the contacts are in view, with tel links for 10111, 10177 and 112;
- the disclaimer link uses the new colour, and the threshold card text is present.

Screenshots are in `screenshots/final_<theme>_<width>_<page>.png`. `2safety_after_shortcut_viewport` shows exactly what is on screen after tapping **Emergency contacts**.

## Evidence reproducibility

- The inputs to `25_build_model_evidence.py` are now committed:
  - `docs/evidence/held_out_test_set.csv.gz`;
  - the 29 October evaluation outputs (`*.csv` files allowed by a narrow `.gitignore` exception).
- `--check` reproduces `docs/model_evidence.json` exactly, in the working tree ([evidence_check_working_tree.txt](evidence_check_working_tree.txt)) and from a clean clone of the commit ([evidence_check_clean_clone.txt](evidence_check_clean_clone.txt)).
- The published figures did not change: at 35%, precision 51.6%, recall 72.0%, F1 0.601, 581 false alarms and 241 missed storm hours (warning when estimate ≥ 0.35).
- ERA5 source data (about 96 MB) is not committed. [docs/MODEL_EVALUATION.md §7](../../docs/MODEL_EVALUATION.md) explains how to obtain it.

## Tests

- **Full suite:** 362 passed, 0 failed, 0 skipped (274 subtests), run twice. Run 2 used a process-wide network guard, with 0 outbound attempts ([run 1](test_run1.txt), [run 2](test_run2.txt)).
- **No live calls:** no SMS was sent.
- **New tests:**
  - contacts on Safety only, after the advice, with the shortcut scroll;
  - tap-to-call links;
  - plain-text numbers in the low-data view;
  - communication states for each configuration, including a missing simulation;
  - SMS registration still disabled;
  - the threshold label and its separation from the model score;
  - disclaimer contrast;
  - `--check` passing, with its inputs not git-ignored.
