# Warning Interactions and Decision Support: Evidence (30 October 2026)

**Branch:** `research-dashboard-ui-redesign` (local; not pushed or deployed). No SMS was sent. Public registration and subscriber warnings remain off.

**What is new:**
- a Qaphela-inspired redesign: top navigation, warning banner, blue weather card, hourly strip and tap-to-call contacts;
- resident warning interactions: current and past warnings, details, acknowledgement and emergency contacts;
- an access-controlled decision-support portal for disaster-management officials.

## 1. Automated tests

| Check | Result |
|---|---|
| Full suite, two consecutive runs after all changes | **335 passed, 274 subtests passed** ([run 1](full_regression_run1.txt), [run 2](full_regression_run2.txt)) |
| Network connection attempts (network guard) | **0** |
| Worker equivalence with subscriber alerts off | **21/21 identical** |
| Files written into the real `outputs/` | none |

New tests in `tests/test_warning_interactions.py` (19):

| Requirement | Test(s) |
|---|---|
| Genuine ledger warnings; exact probability only where recorded; development tests only in outbox mode and labelled | `Events::*`, `Banner::test_development_tests_never_look_like_real_warnings` |
| One acknowledgement per device; persistent across restarts; only a keyed hash stored | `Acknowledgements::test_one_per_device_and_persistent_across_restarts` |
| Concurrent acknowledgements (10 from one device and 15 from others → 16 records) | `test_concurrent_acknowledgements` |
| Wording never implies safety | `test_wording_never_implies_safety` |
| No acknowledgement possible before the browser identifies the device (prevents a duplicate after a reload) | `WarningJourneys::test_no_acknowledgement_until_the_browser_identifies_the_device` |
| Officials' status and notes attributed and timestamped; invalid input refused; no dispatch status exists | `Reviews::*` |
| Hashed official accounts; wrong and unknown users refused | `OfficialAccounts::test_hashing_and_verification` |
| Tap-to-call 10111, 10177, 112 | `EmergencyContacts::*` |
| Dashboard journeys: homepage banner → warning; details and acknowledgement once; past warnings; portal sign-in required and never visible to residents; review with aggregate acknowledgements; history | `WarningJourneys::*` |
| Simulation creates no warnings or records | `test_simulation_creates_no_warning_events` |

## 2. Browser walkthrough

[`browser_walkthrough.py`](browser_walkthrough.py) ran in headless Chrome, with real input and a genuine live forecast, in light and dark themes. All 21 checks passed in each theme ([light](journey_light.json), [dark](journey_dark.json)). The only server log entries were Windows connection-reset messages from closing the headless browser.

**Demonstration data.** The real ledger holds no warnings yet. The walkthrough therefore first ran `24_create_dev_test_warning.py` twice, creating one warning in effect (62%) and one past warning (48%), both **labelled "development test · not a real warning"** on every screen. The script works only in local outbox mode.

| Step | Screenshot (`screenshots/<theme>_…`) |
|---|---|
| Homepage: test-warning banner, model outlook, blue weather card, hourly forecast, SAWS link, SMS button, tap-to-call contacts | `01_home` |
| Alerts: current and past warnings | `02_alerts` |
| Warning details: severity, forecast period, location, estimate, issue time, *Act now*, contacts | `03_warning_detail` |
| Acknowledged ("only records that the warning was viewed…") | `04_acknowledged` |
| After a reload, the same browser shows "You acknowledged this warning on …"; no second record (1 acknowledgement stored) | `04b_after_reload` |
| SMS alerts within Alerts | `05_sms_alerts` |
| Mobile homepage and mobile warning | `06_mobile_home`, `07_mobile_warning` |
| Officials' portal sign-in | `08_portal_sign_in` |
| Active warnings: timestamps, estimate, acknowledgements, review status | `09_portal_active` |
| Review recorded ("Monitoring" plus a note, attributed to `demo.official`) | `10_portal_review` |
| Geographic risk: ECMWF rainfall grid around the model point | `11_portal_geography` |
| History of warnings and actions, with CSV export | `12_portal_history` |

## 3. Defects found and fixed during this work

1. **Duplicate acknowledgement after a reload.** If the button was pressed before the browser returned its device identifier, a second record could be made. The button now waits ("Checking this device…").
2. **Development tests showed the red "STORM WARNING IN EFFECT" banner.** They now get an amber "not a real warning" banner.
3. **Actions recorded in the same second were listed oldest first.** They are now listed newest first, in recording order.
4. **Leftover minimum height on the homepage outlook card.** Removed.

## 4. Limitations

- Acknowledgement counts are anonymous device counts. Clearing browser storage allows another acknowledgement, so treat the counts as indicative engagement.
- No verified Matatiele or Alfred Nzo disaster-management number is listed. Only national numbers are shown.
- The use case PNG was rendered locally with PlantUML 1.2024.7 (checksum verified against Maven Central). A later re-render, intended to turn the diagram note into a legend, was blocked by the permission settings, so the committed PNG matches the committed source as it stands.
