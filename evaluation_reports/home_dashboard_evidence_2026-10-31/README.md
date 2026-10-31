# Home dashboard in the reference layout: evidence (31 October 2026)

The homepage follows the layout of the reference image, using **only genuine data**. The model, its 29 inputs, the 35% threshold, warning generation and SMS are unchanged. The model files are identical to `main` ([model_unchanged.json](model_unchanged.json)), and worker equivalence is 21/21.

| Row | Cards | Source |
|---|---|---|
| 1 | Weather forecast · Model-estimated storm risk (gauge, 35% marker) · Prediction period (target hour, model update, fresh / out-of-date) · Warning decision | Saved prediction and ECMWF input; warning record |
| 2 | Next 6 hours chart (rain bars, wind line) · Key weather variables (rain, wind, temperature, dew point, CAPE, pressure) | ECMWF regional forecast at Matatiele; the model's input hour |
| 3 | **Recent predictions** log (target hour, forecast input hour, risk score, decision) · Warning communication | `prediction_history.csv` (saved hourly runs); configuration |

## Not reproduced from the reference image (they would need invented data)

| Reference element | Why not | What is shown instead |
|---|---|---|
| 6-hour storm-probability line | The model makes one next-hour estimate | Six hours of ECMWF rain and wind, and the log of past genuine scores |
| Red risk zone on a map around Matatiele | The model scores one location | The Map page keeps the rainfall forecast with a single Matatiele marker |
| "SMS warning sent · Delivered (2) · Sent (3)" | No SMS has been sent; public delivery is disabled | Three status tiles derived from configuration |
| "Send Test SMS" on the public page | It is an administrator action | It stays administrator-only |
| Landscape photo header | No rights-cleared image is available | The existing header |

## Prediction log rules

- One row per saved hourly run, newest first, showing the last six runs.
- **Warning** appears only where the public record holds a genuine warning for that hour. **Threshold reached** means the score was at least 35% with no record. Otherwise the row reads **No warning**.
- Hours without a saved run are not listed, and gaps are not filled in.

## Checks

- **Browser** ([light](browser_checks_light.json), [dark](browser_checks_dark.json)): at 1440, 820 and 390 px in both themes, there was no overflow and the risk score was visible without scrolling. The score was the genuine saved value (3% at capture).
- **Tests:** 368 passed, 0 failed, 0 skipped, run twice. The second run used a network guard, with 0 outbound attempts.
- **New tests:**
  - log rendering, including the empty-log message;
  - the log and variables come from the saved record, with one saved run giving one row;
  - the desktop and phone grid order.
