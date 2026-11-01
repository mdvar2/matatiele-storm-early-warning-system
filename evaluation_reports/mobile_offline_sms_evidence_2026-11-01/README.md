# Mobile navigation, offline dashboard and SMS pathway: evidence (01 Nov 2026)

Branch `mobile-offline-sms-final`, from `main` at `28343ac`. The real browser checks used headless Chrome driven over CDP against a local server running the real dashboard. The ECMWF retrieval and model inference were genuine. No SMS provider was configured, and no SMS was sent. All results are in `browser/checks.json`.

## Mobile navigation

| Check | 360 px | 390 px |
|---|---|---|
| Bottom navigation visible, `position: fixed`, flush with the bottom of the screen | yes | yes |
| Top tab row / ☰ button shown | no / no | no / no |
| Labels clipped (Home, Risk, Map, Safety, More) | none | none |
| Tap target height | 54 px | 54 px |
| Last content hidden behind the navigation | no (content ends at 712 px; navigation starts at 737 px) | no |
| Active state (Home, then Risk) | `primary` on the selected tab only | same |
| More sheet: items; Escape closes it; closes after a choice | Alerts, Forecast, Historical Data, About, Save for offline use, SMS service; yes; yes | same |
| Keyboard: tab buttons are focusable | yes | yes |

Tablet (820 px) and desktop (1366 px) show no bottom navigation and keep the side menu open. These layouts are unchanged.

Screenshots: `nav_360_*`, `nav_390_*`, `nav_tablet_820.png`, `nav_desktop_1366.png`.

## Offline dashboard (scenarios A–G)

| Scenario | Result | Screenshot |
|---|---|---|
| **A**: connected. The dashboard showed 1% and NO WARNING TRIGGERED. **Save for offline use** was pressed. | The file was served as `attachment; filename="matatiele-storm-info-20261101-0854.html"`, 19.7 KB. | `A_connected_dashboard.png` |
| **B**: the file opened with the network disabled. | "OFFLINE — SAVED INFORMATION", "Last saved: 01 Nov 2026 08:54 SAST", 1%, LOW RISK, NO WARNING TRIGGERED, threshold 35%, period and data age. | `B_offline_home.png` |
| **C**: each tab visited while fully offline (Home → Outlook → Alerts → Safety → More). | Each tab rendered without blanking. Outlook carried "Saved model outlook — unvalidated beyond one hour". Alerts read "No storm warning was active when this information was saved." More showed "Map unavailable offline — reconnect to view forecast rainfall map." | `C_offline_*.png` |
| **D**: reopened offline, in the same browser and then in a new browser process. | Same content. | `checks.json` |
| **E**: the saved copy was dated two days back, and four of its outlook hours were placed in the past (labelled test fixture). | "Saved information may be out of date."; data age 2 days; 4 of 11 outlook hours faded as past. | `E_stale_home.png`, `E_stale_outlook.png` |
| **F**: partial and corrupt saved values. | Partial: the score shows, and the missing parts say "No saved … in this copy". Corrupt: "No saved warning information yet". Never blank. | `F_partial.png`, `F_corrupt.png` |
| **G**: reconnected, and a newer snapshot saved. | Opened offline with "Last saved: 01 Nov 2026 08:58 SAST" (newer than A). | `G_newer_snapshot.png` |
| **H**: connection lost while the dashboard was open. | "Connection lost — live updates paused" appeared. **Open saved offline dashboard** showed the saved dashboard (1%, 08:54 SAST) with no server. **Back to live dashboard** closed it. The banner cleared on reconnection. | `H_*.png` |

## SMS

- **Resident view:** "SMS simulation" and "Public SMS delivery: Disabled" are shown. There is no controlled-test control.
- **Administrator panel (`I_admin_sms_panel.png`):**
  - Provider: "Not configured". Controlled live test: "disabled". Public subscriber delivery: "Disabled".
  - "Accepted by provider is not delivery" is shown.
  - **Send controlled SMS test** is disabled.
- **Real sends:** no real controlled test was sent, because no explicit approval or configuration was given. The pathway is ready for controlled verification.

## Automated tests

- `test_run1.txt`: 410 passed, 300 subtests.
- `test_run2.txt`: same, with a process-wide network guard (0 outbound attempts).
- The new tests cover:
  - offline tabs and wording;
  - snapshot content and the rule that only a valid result may replace it;
  - privacy;
  - the connection watcher;
  - bottom navigation and the More sheet;
  - the controlled test (disabled, unconfigured, invalid recipient, confirmation, simulation on, number never logged, failure and uncertainty, delivery parsing, trial detection);
  - the warning → ledger → duplicate check → SMS → state order, including provider failure keeping the warning and no duplicate on rerun.

## Integrity

The model, the 29 features, the 35% threshold, the worker, the outlook and the model evidence are byte-identical to `main`. `25_build_model_evidence.py --check` passed.
