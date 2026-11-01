# Resilient dissemination: evidence (31 October 2026)

Three additions, so warnings reach residents when networks fail ([docs/RESILIENT_DISSEMINATION.md](../../docs/RESILIENT_DISSEMINATION.md)):
1. **early alerts** from a 12-hour model outlook;
2. an **offline page**;
3. **community relays**.

The model, its 29 inputs, the 35% threshold and the validated next-hour warning are unchanged:
- `18_scheduled_sms_worker.py`, `12_live_forecast_and_predict.py` and `sms_alert.py` are untouched;
- worker equivalence is 21/21;
- the model files are identical to `main` ([model_unchanged.json](model_unchanged.json)).

## Verification

| Claim | Evidence |
|---|---|
| The outlook uses exactly the live script's inputs | `tests/test_outlook.py`: for each hour checked, the 29-feature row equals the live script's, with zero difference, and the score is identical |
| Hours with missing forecast values are skipped, never filled in | `test_missing_hours_are_skipped_not_filled` |
| Early alerts: off by default; recorded once per 6-hour block; residents and relays messaged once; labelled TEST in simulation; never fail the job | `EarlyAlertStep` tests (real model, simulated outbox, fake GitHub API) |
| The offline page works with **no network** | Headless Chrome ([browser_checks.json](browser_checks.json)). With a connection: "Connected. Saved …", and the service worker controls the page. With the network cut off and the page reloaded: "No connection: showing the last saved information", with the score, decision, advice and emergency numbers ([screenshot](screenshots/light_offline_page_no_network.png)). |
| The offline status is genuine | Neither the on-screen simulation nor the connectivity demonstration reaches `status.json` (test) |
| Relay option and announcement script | [Registration](screenshots/light_sms_registration_relay_option.png); [script on a labelled development test warning](screenshots/light_warning_announcement_script.png) |
| Home outlook card | [Screenshot](screenshots/light_home_with_outlook.png): live ECMWF data, "No raised storm risk in the next 12 hours" at capture |

**A bug found and fixed during browser verification:** with no network, the offline page first said "Connected", because the service worker answered from its saved copy. Saved copies are now marked, the page says "No connection", and a test covers this.

## Tests

388 passed, run twice; the second run used a network guard, with 0 outbound attempts ([1](test_run1.txt), [2](test_run2.txt)).

## Switches

All are off by default and set as repository variables on GitHub:
- `OUTLOOK_ALERTS_ENABLED=true` turns on early-alert records;
- `SUBSCRIBER_ALERTS_ENABLED=true` also sends SMS (needs a non-trial provider, POPIA compliance and ethics clearance).

The workflow step takes effect after merging into `main`.
