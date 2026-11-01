# Visual-first homepage: evidence (31 October 2026)

This changes the homepage only. The model, its 29 inputs, the 35% threshold and warning generation are unchanged, as are the SMS simulation and low-connectivity handling:
- [model_unchanged.json](model_unchanged.json): same content as `main`;
- [equivalence_r3.txt](equivalence_r3.txt): worker equivalence 21/21;
- [evidence_check.txt](evidence_check.txt): the Risk Analysis evidence is reproduced.

## What changed on Home

| Area | Before | After |
|---|---|---|
| Storm risk | Small gauge, "Model estimate: 0% chance of a storm", several caption lines | Large gauge (the first and largest card) with a red marker labelled 35%, a large score, a category badge (LOW / ELEVATED / MODERATE / HIGH RISK, or OUT OF DATE), "Model risk score — not a calibrated probability", the target hour, the update time and "Not a guarantee: storms can still develop." |
| Warning decision | Sentences | A coloured badge with an icon. NO WARNING TRIGGERED (green). THRESHOLD REACHED (amber), when the score is at or above 35% but the public record holds no genuine warning for that hour. WARNING TRIGGERED (red), only when a genuine warning record exists. NO DECISION (grey), when data is out of date or missing. SIMULATED WARNING appears only in the administrator simulation. Below the badge: "Warning threshold: 35%", the **Why 35%?** tooltip, and "not an official SAWS warning". |
| Weather | Text lines | Large temperature, a condition icon from the forecast values, three icon tiles (rain, wind, gusts) and "ECMWF forecast · HH:MM SAST" |
| Communication | Labelled rows | Three icon tiles with status dots: Dashboard alerts, SMS simulation, Public SMS delivery (derived from configuration, as before) |
| Actions | A column of full-width buttons | One compact row: View warnings, Safety advice, Emergency contacts, SMS service |
| Next hours | Small icons | Larger icons and temperatures, labelled "ECMWF weather forecast · not storm-risk scores" |
| Duplication | The status strip repeated the update time and sources, and the footer repeated them again | The status strip shows freshness and the chain (ECMWF forecast → Random Forest risk score → 35% decision). The update time appears once, on the risk card. The footer is one line. |
| Genuine warning | — | The act-now safety actions move to the top, directly under the warning banner |

**Layout:**
- **Desktop:** risk on the left (spanning two rows); decision and weather beside it; communication below.
- **Tablet:** risk and decision side by side, then weather and communication.
- **Phone:** risk, decision, weather, communication.

## Measurements ([light](after_light.json), [dark](after_dark.json))

| Width | Overflow | Risk score visible without scrolling | Score font size |
|---|---|---|---|
| 1440 px | none | yes | 58 px |
| 820 px | none | yes | 40 px |
| 390 px | none | yes | 46 px |

On a 390 × 800 px phone, the warning-decision badge starts just below the first screen (898 px), directly under the risk card. The title, clock, theme switch and navigation take the top 500 px.

The gauge and score showed the genuine saved model output at capture time (0.0, so 0%). The alt text was "Model risk score 0%, warning threshold 35%". No value was illustrative.

## Screenshots (`screenshots/`)

- `before_<theme>_<width>_home.png`: at commit `2dd09f4`.
- `after_<theme>_<width>_home.png` (full page) and `after_<theme>_<width>_home_first_screen.png` (what is visible before scrolling).

## Tests

- **Full suite:** 366 passed, 0 failed, 0 skipped (281 subtests), run twice. Run 2 used a process-wide network guard, with 0 outbound attempts ([run 1](test_run1.txt), [run 2](test_run2.txt)).
- **No live calls:** no SMS was sent.
- **New or updated tests:**
  - every decision state, including "threshold reached is not a warning";
  - the gauge filled to exactly the score, with the marker at 35% and nothing drawn for 0;
  - score formatting;
  - no "chance of a storm" wording;
  - phone ordering;
  - act-now advice first during a genuine warning;
  - the status-strip chain;
  - the condition icon from the forecast values.
