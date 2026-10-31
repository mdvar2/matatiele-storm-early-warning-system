# SMS warnings and low-connectivity operation

## 1. Warning pipeline

```
ECMWF forecast (Open-Meteo) → Random Forest estimate → 35% threshold → warning event (public ledger, reserved first)
   → SMS queued per subscriber (reserved before sending) → provider attempt → outcome recorded → visible on the admin page
```

| Property | How it is achieved | Code |
|---|---|---|
| Warning independent of SMS | The worker reserves the warning hour in the public ledger **before** any SMS. An SMS failure never removes the warning, which stays on the Alerts page. | `18_scheduled_sms_worker.py` |
| Stable event ID | `REAL-SHORT-V1-<forecast hour, UTC>` | `warning_events.py`, worker |
| No duplicates | One ledger reservation per hour. One delivery record per (warning, subscriber), reserved before sending. Re-runs send nothing twice. | `subscriber_alerts.deliver_warning` |
| Honest status | `pending` (queued), `submitted` (accepted by provider, **delivery not confirmed**), `delivered` (only after provider confirmation), `failed`, `uncertain` (never retried automatically), `outbox` (simulated, not sent) | `subscriber_alerts.py` |
| Message content | `MATATIELE MODEL ALERT: <period> SAST. Storm risk <p>%. If severe weather develops, stay indoors. Avoid lightning/flooded roads. Check SAWS.` Simulated messages begin with `TEST ONLY - NOT A REAL WARNING.` | `sms_alert._build_warning_message` |
| No stale warnings | The worker rejects forecasts it did not retrieve in the same run, and expired targets (`stale_forecast`). | worker; `tests/test_run_record.py` |

## 2. Delivery modes (`SMS_DELIVERY_MODE`)

| Mode | Setting | What happens | Status |
|---|---|---|---|
| **A: Simulation** | `outbox` with the local file store | Messages go to a local outbox file and are labelled TEST ONLY. Refused against the real subscriber store. | Default for demonstrations |
| **B: Controlled test** | `twilio` (trial account) | Only numbers verified on the trial account. The `--test-sms` workflow sends a labelled "NO WEATHER WARNING" connectivity message. | One test SMS received (run #4) |
| **C: Public** | — | Not enabled. It needs an upgraded provider account, POPIA compliance and ethics clearance, a private subscriber store, and the project owner's approval. | Disabled |

The Home page shows three indicators, each derived from configuration and the code present (`resident_alerts.communication_status`):

| Indicator | States |
|---|---|
| Dashboard alerts | **Available**, or "Warning record unreachable" when the public warning record cannot be read |
| SMS simulation | **Available** (the outbox gateway and `26_sms_simulation_demo.py` are present), "Active on this deployment" in outbox mode, or "Unavailable" |
| Public SMS delivery | **Disabled**. With `twilio` it shows "Controlled test only"; no setting enables public delivery |

The Alerts page (SMS alerts) gives the details: the current configuration, simulation, public registration ("Not yet available" when SMS is disabled), delivery limitations, research-test restrictions, and SMS record counts taken from real records only, with no phone numbers.

## 3. Reproducible SMS simulation

```
python 26_sms_simulation_demo.py --out sms_simulation.json
```

The script runs in a new temporary folder with throw-away keys, and network access is blocked inside the process. Steps:
1. A fictional subscriber registers and verifies.
2. A stated **test** probability (62%, not a model output) is compared with 35%.
3. A warning event is recorded and labelled `development test`.
4. The TEST ONLY SMS is written to the outbox with status `outbox`.
5. Running the same warning again creates no new message.
6. A simulated provider timeout leaves the warning recorded and the delivery `uncertain`.
7. A 20% value creates no warning.

It never touches the model, the threshold, the public ledger or any real store. `tests/test_research_refinement.py` runs it.

`24_create_dev_test_warning.py` (outbox mode) creates the same kind of labelled development warning for the dashboard's Alerts page.

## 4. Low connectivity

| | What exists | Status |
|---|---|---|
| Low-data text view (`?view=text`) | Matatiele, prediction period, estimate, **warning decision**, last update, **information status (current / OUT OF DATE)**, safety advice and the **emergency numbers** as plain text (calls need mobile network coverage), with no maps, charts or images | Implemented |
| Last known information | If a refresh fails, the last saved estimate is shown labelled "Outdated data" / "OUT OF DATE", and the warning decision reads "No warning decision: the information is out of date". | Implemented |
| No warnings from stale data | Worker freshness checks (`stale_forecast`) | Implemented, tested |
| Low-data map | Basemap without tiles | Implemented |
| SMS | Needs no mobile data or smartphone on the recipient's side, only network signal. The sending gateway (GitHub Actions and the provider) needs Internet access. | Simulated / controlled test |
| Offline operation, local sensors, LoRa, MQTT | No code exists. They are mentioned in documents as future research only. | Not implemented |

**Connectivity-failure demonstration:**
- `tests/test_research_refinement.py::RiskAnalysisAndHome::test_connectivity_failure_then_recovery` runs normal (fresh, 41%, warning condition met), then failure (refresh fails: last estimate flagged, no decision), then recovery (fresh again).
- Screenshots of the failure state are in `evaluation_reports/research_refinement_evidence_2026-10-30/`.

## 5. Connectivity-failure demonstration and system log

- **Demonstration:** administrators can switch on **Connectivity-failure demonstration (this session only)** in the sidebar. For that browser session the dashboard makes no forecast retrieval. It shows the last known information labelled out of date, and the warning decision reads NO DECISION. Other users are unaffected.
- **System log:** switching the demonstration on and off is recorded under Alerts, then System log, as "Forecast connection set to OFFLINE for a low-connectivity demonstration" and "… restored". Genuine outages are recorded separately as "Forecast service unreachable" or "Forecast data out of date".
