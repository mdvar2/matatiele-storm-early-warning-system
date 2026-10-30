# Integrated Resident Application: End-to-End Test Evidence (30 October 2026)

**Branch:** `research-dashboard-ui-redesign`. It is based on `origin/main` 98676fc and contains the redesign commits df56cd8 and b5b2317 plus the integration commit. Nothing was pushed or deployed.

**Safety:** no real SMS was sent. Automated tests replace Twilio, GitHub and the network with mocks. The browser demonstration ran in development *outbox* mode, which writes messages to a local file.

## 1. Automated tests (fully mocked, no network)

| Suite | Result |
|---|---|
| Full regression `python -m pytest tests/`, run twice | **307 passed, 270 subtests passed**, both runs ([run 1](full_regression_run1.txt), [run 2](full_regression_run2.txt)) |
| Network guard: outbound connection attempts during the full suite | **0** |
| Stability | Five further full runs after the final changes: four completed (307 passed, 45–51 s). One run stalled at about 55% and was stopped after 10 minutes. Three follow-up runs with a 90-second hang detector (`-o faulthandler_timeout=90`) all passed with no stall, so the cause could not be reproduced. All store lock and retry loops are bounded by deadlines. |
| Worker behaviour equivalence with subscriber alerts off (`behaviour_equivalence_check_r3.py`) | **21/21 scenarios identical** |
| Subscription and end-to-end tests ([verbose list](subscription_and_e2e_tests_verbose.txt)) | 34 passed, 20 subtests |
| Files written into the real `outputs/` by the tests | none |

### Required chain and the test that proves each link

| Link | Test(s) |
|---|---|
| Registration (SA mobile validation, Matatiele area, explicit consent) | `Validation::test_south_african_mobile_numbers`, `Lifecycle::test_subscribe_requires_consent_valid_number_and_area` |
| Verification (6-digit code; expiry, lockout, rate limits) | `Lifecycle::test_verification_activates_and_records_consent`, `test_wrong_expired_and_locked_codes`, `test_rate_limits` |
| Subscription activation and status view | `SmsJourney::test_subscribe_verify_manage_unsubscribe_through_the_dashboard` (the real dashboard in Streamlit AppTest) |
| Warning decision → SMS submission | `WorkerIntegration::test_flag_on_warns_subscribers_once_per_hour` (the real worker; mocked forecast, ledger and Twilio) |
| Duplicate prevention | the same test (a second run in the same hour sends nothing), `Delivery::test_only_active_verified_subscribers_receive_once` |
| Delivery-status tracking | `Delivery::test_delivery_status_tracking` |
| Failure handling (definitive vs uncertain; STOP; admin retry limit) | `Delivery::test_failures_uncertainty_and_stop`, `test_definitive_failure_can_be_retried_by_admin_with_limit`, `WorkerIntegration::test_subscriber_failure_never_breaks_the_existing_warning` |
| Unsubscription enforcement | `Delivery::test_unsubscribed_numbers_never_receive`, `Lifecycle::test_manage_and_unsubscribe_erases_number`, `SmsJourney::test_warning_reaches_only_active_verified_subscribers_then_stops_after_unsubscribe` |
| Unverified numbers never receive warnings | `Delivery::test_only_active_verified_subscribers_receive_once`, the `SmsJourney` warning test |
| Simulation sends nothing and changes no prediction | `SmsJourney::test_simulation_never_reaches_subscribers` (plus the existing simulation tests) |
| Feature off ⇒ worker unchanged | `WorkerIntegration::test_flag_off_leaves_worker_behaviour_unchanged`, `WorkerHook::test_disabled_by_default`, the equivalence check |
| Privacy (encryption; no full numbers on public or admin pages; no number enumeration) | `Storage::test_numbers_are_encrypted_and_never_stored_in_clear`, `test_wrong_key_cannot_read_numbers`, `SmsJourney::test_public_pages_never_show_phone_numbers`, `test_administration_is_protected_and_shows_masked_data_only`, `Lifecycle::test_manage_does_not_reveal_unregistered_numbers`, `test_subscribe_does_not_reveal_registered_numbers` |
| Persistent store (concurrency; GitHub compare-and-swap) | `Storage::test_concurrent_writers_never_lose_updates`, `GitHubBlob::test_contents_api_compare_and_swap`. A separate stress run had 3 processes × 40 threads write to one file: 120/120 writes, no errors. |
| Registration closed when SMS is not configured | `SmsJourney::test_registration_closed_when_sms_not_configured` |
| Public warning history lists only genuine warnings | `LedgerHistory::test_only_genuine_warning_records_are_listed`, `SmsJourney::test_warning_history_lists_genuine_warnings` |

## 2. Browser demonstration of the full workflow

[`browser_journey.py`](browser_journey.py) drove the complete local application in headless Chrome, using real mouse and keyboard input, in light and dark themes. The app ran in outbox mode with a temporary store and keys, and fetched a genuine live forecast. Every step passed in both themes, with no server errors ([light](journey_light.json), [dark](journey_dark.json)).

| # | Step | Screenshot (light / dark) |
|---|---|---|
| 1 | Dashboard (genuine live forecast); hero subtitle | `screenshots/light_01_dashboard.png` / `dark_01_…` |
| 2 | SMS Alerts → Subscribe form (number, area, consent) | `…_02_sms_subscribe_form.png` |
| 3 | Code sent (masked number); code read from the development outbox | `…_03_sms_enter_code.png` |
| 4 | Verified → **Active** | `…_04_sms_active.png` |
| 5 | Worker subscriber hook delivers one warning; administrator signs in; Administration page | `…_05_admin_monitoring.png` |
| 6 | Manage my subscription → ownership code → status | `…_06_manage_status.png` |
| 7 | Unsubscribe → **Unsubscribed**, number removed | `…_07_unsubscribed.png` |
| 8 | Warning History (public ledger) | `…_08_warning_history.png` |
| 9 | Safety Advice | `…_09_safety_advice.png` |
| 10–12 | Mobile (390 px): dashboard, SMS Alerts, low-data text view | `…_10…`, `…_11…`, `…_12…` |

The development outbox ([light](dev_outbox_light.redacted.jsonl), [dark](dev_outbox_dark.redacted.jsonl)) shows exactly three messages per run: verification code, warning, and ownership code. Codes are redacted in these copies. The outbox lists the number only in masked form.

**What was not genuine in the demonstration.** The real forecast was dry, so step 5 called the worker's subscriber hook (`subscriber_alerts.run_for_worker`) directly with a **test probability of 62%**. This exercised the delivery path; it was not a real warning. The public Warning History correctly shows *no warnings issued yet*: the real ledger contains only two connectivity-test entries, which are deliberately excluded.

**Administrator privacy check.** The full number never appears in the admin page text. The deliveries table is drawn on a canvas, and the screenshot shows only `+27 82 *** **67`.

## 3. Hero subtitle contrast (fix b5b2317), measured from the screenshots

| Screenshot | Text colour | Background | Contrast |
|---|---|---|---|
| light dashboard | rgb(7, 42, 82) | rgb(134, 201, 243) | **7.98:1** |
| light SMS page | rgb(7, 42, 82) | rgb(142, 204, 244) | **8.27:1** |
| dark dashboard | rgb(243, 248, 254) | rgb(6, 17, 37) | **17.65:1** |

All exceed WCAG AA (4.5:1). Before the fix, the subtitle measured 3.87:1.

## 4. Defects found and fixed during this evaluation

1. **Number enumeration on Subscribe.** The form said *"already subscribed"*, which revealed whether a number was registered. Now the form reply and next step are identical for every number, and only the phone's owner receives an "already subscribed" SMS.
2. **Windows store lock race.** Under load, a lock file still being deleted raised `PermissionError`. Lock acquisition and release now retry.
3. **Unsubscribed card.** It used the "unknown" (?) icon and showed the subscription date. It now uses its own 🔕 style and shows the *Unsubscribed on* date.
4. **Admin metric truncated** ("Developmen…"). The label is now *Dev outbox*.
