# Final Review Evidence: Integrated Resident Application (30 October 2026)

**Branch:** `research-dashboard-ui-redesign` (local; not pushed or deployed). This builds on [integrated_application_evidence_2026-10-30](../integrated_application_evidence_2026-10-30/README.md).

**Safety:** no real SMS was sent. Tests replace Twilio, GitHub and the network with mocks; the walkthrough ran in development *outbox* mode against a temporary store.

## 1. Automated tests

| Check | Result |
|---|---|
| Full suite `python -m pytest tests/`, two consecutive runs after all changes | **316 passed, 270 subtests passed**, both runs ([run 1](full_regression_run1.txt), [run 2](full_regression_run2.txt)) |
| Network connection attempts during the suite (network guard) | **0** |
| Worker equivalence with subscriber alerts off | **21/21 identical** |
| Files written into the real `outputs/` | none |
| 90-second hang detector (`faulthandler_timeout=90`) | not triggered |

New tests added in this review:

| Requirement | Test |
|---|---|
| Lifecycle survives an application restart between every step | `RestartAndConcurrency::test_full_lifecycle_survives_restarts_between_every_step` |
| A code entered after a page reload or restart still verifies | `SmsJourney::test_code_still_works_after_reload_or_restart` |
| 10 residents register, verify and unsubscribe concurrently while two worker runs race on one warning (local file store) | `test_concurrent_requests_local_file_store` |
| The same scenario on the GitHub store, where compare-and-swap conflicts occurred and were resolved | `test_concurrent_requests_github_store` |
| Store files over 1 MB | `test_github_store_reads_files_over_one_megabyte` |
| Retention deletes unverified, cancelled and old records | `test_retention_deletes_unverified_cancelled_and_old_records` |
| Admin sign-in lockout, shared by all sessions | `test_repeated_wrong_passwords_lock_sign_in_for_every_session` |
| Global daily SMS cap | `test_global_daily_cap_bounds_sms_cost` |
| Development outbox refused against the real store | `test_development_outbox_can_never_use_the_real_store` |

## 2. Browser walkthrough with a server restart

[`browser_walkthrough.py`](browser_walkthrough.py) ran in headless Chrome with real mouse and keyboard input, in light and dark themes, using a genuine live forecast. Every check passed in both themes, with no server errors ([light](journey_light.json), [dark](journey_dark.json)).

| Step | Result | Screenshot |
|---|---|---|
| Resident opens the dashboard and checks the current risk (risk card, forecast weather tile, SMS button) | ✔ | `screenshots/*_01_homepage.png` |
| Weather map | ✔ | `*_02_weather_map.png` |
| Homepage SMS button → registration: number and consent | ✔ | `*_03_registration_form.png` |
| Verification code sent (masked number) | ✔ | `*_04_verification_code_sent.png` |
| **Server stopped and restarted.** The session was reset, but the code still verified via *Already received a code?* → **Active** | ✔ | `*_05_verified_active_after_restart.png` |
| An eligible warning reaches the subscriber. The worker hook was called with a **test probability of 62%**, because the real forecast was dry. | `sent: 1` | outbox ([light](dev_outbox_light.redacted.jsonl)) |
| Manage → ownership code → subscriber status | ✔ | `*_06_subscriber_status.png` |
| Unsubscribe → confirmation and *Unsubscribed on* date | ✔ | `*_07_unsubscribed.png` |
| Next warning after unsubscribing | `no_active_subscribers` (nothing sent) | — |
| Public warning history | ✔ No genuine warnings yet; the ledger contains only connectivity tests, which are excluded. | `*_08_warning_history.png` |
| Administrator sign-in → monitoring page; no full number in the page text | ✔ | `*_09_administrator.png` |
| Mobile (390 px): homepage and SMS Alerts | ✔ | `*_10_mobile_homepage.png`, `*_11_mobile_sms_alerts.png` |

The outbox holds exactly three messages per run: the verification code, the warning, and the ownership code. No message was sent after unsubscribing.

**Screenshot note.** In `dark_01_homepage.png` the satellite tiles had not finished loading when the image was taken. The same map renders fully in `*_02_weather_map.png`.

## 3. Defects found and fixed in this review

1. Store growth: no retention, and GitHub returns no content for files over 1 MB.
2. Admin sign-in had no attempt limit.
3. There was no global daily cap on verification SMS.
4. Development outbox mode could run against the real store.
5. A resident could not finish verifying after a page reload or restart.
6. "No code waiting" and "wrong code" read differently, which revealed pending codes.
7. The unsubscribe confirmation disappeared immediately.

See the [security review](../RO3_deployment_security_review_2026-10-30.md).
