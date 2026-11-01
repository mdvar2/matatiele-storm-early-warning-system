# Administrator and System Maintenance Manual

This manual is for the project team members who operate the Matatiele Smart Resilient Storm Early Warning System. They monitor warnings and SMS delivery, help residents, and keep the system running.

For first-time setup, see [DEPLOYMENT_AND_CONFIGURATION.md](DEPLOYMENT_AND_CONFIGURATION.md).

---

## 1. System overview

| Component | File(s) | Runs where |
|---|---|---|
| Dashboard (residents and administrators) | `16_dashboard.py`, `resident_pages.py`, `dashboard_theme.py` | Streamlit Community Cloud |
| Hourly forecast, prediction and warning worker | `18_scheduled_sms_worker.py`, `12_live_forecast_and_predict.py`, `sms_alert.py` | GitHub Actions, `scheduled-storm-sms.yml` |
| Resident subscriptions (registration, verification, unsubscribe) | `subscriptions.py` | Dashboard |
| Encrypted subscriber store | `subscriber_store.py` | One JSON file in a **private** GitHub repository |
| Warning delivery to subscribers | `subscriber_alerts.py` | Called by the worker after a warning hour is reserved |
| Public warning ledger (duplicate prevention and public history) | `[SMS-LEDGER] …` GitHub issues | Public repository |
| Run records and heartbeats (monitoring) | `run_record.py`, `19_publish_run_record.py`, `20_send_heartbeat.py` | GitHub Actions |

**Warning rule (unchanged).** The Random Forest model estimates the probability of a storm in the next hour. A warning is issued when this is **≥ 35%**. The model and the threshold are not configurable from the dashboard.

**Hourly sequence:**

1. Fetch the ECMWF forecast and run the model.
2. If the probability is ≥ 35%, reserve the hour in the public ledger. If the hour is already reserved, stop: this prevents duplicates.
3. Send the warning to the existing configured recipients (`ALERT_TO_NUMBERS`).
4. If `SUBSCRIBER_ALERTS_ENABLED` is `true`, deliver the same warning to every **active, verified** subscriber.
5. Record the counts in the run record (`subscriber_alerts`, `subscriber_recipients`, `subscriber_submitted`, `subscriber_failed`, `subscriber_uncertain`). No phone numbers are recorded.

A subscriber failure never stops the worker, and never changes the prediction or the ledger.

## 2. Signing in

1. In the sidebar, open **Administrator Access**, enter the administrator password (`ADMIN_PASSWORD`) and press **Unlock Admin Controls**.
2. **Administrator controls** then appear in the sidebar:
   - **Warning simulation (on screen only):** previews the warning screens. It does **not** send SMS, and does not change predictions, the ledger or subscriber records. While it is active, a banner labels every page as a simulation.
   - **Administration:** opens the monitoring page.
3. After **10 wrong passwords in 15 minutes**, sign-in is locked for everyone for the rest of that window, and *Too many failed sign-in attempts* is shown. Wait 15 minutes. Use a long random password (16 characters or more).
4. Press **Log Out** when you finish. The Administration page is never available to residents. If a session loses admin access, it returns to the Dashboard.

## 3. The Administration page

| Section | What it shows | What to look for |
|---|---|---|
| **Banner** | In development outbox mode, a yellow *DEVELOPMENT MODE* banner. | It must **not** appear in production. |
| **SMS delivery mode** | Disabled, Dev outbox, or Twilio (live). | Production is *Twilio (live)*. |
| **Subscriber store** | *local file* or *private GitHub repository*. | Production must be *private GitHub repository*; Streamlit Cloud does not keep local files. |
| **Encryption** | Whether the encryption and hash keys are configured. | Must be *Configured*. |
| **Prediction data** | Freshness of the live prediction. | *Stale* means the forecast has not been updated recently. |
| **Active / Awaiting verification / Unsubscribed** | Subscriber counts. | A large *Awaiting verification* count may mean codes are not arriving. |
| **Warnings sent to subscribers** | Number of warning hours delivered to subscribers. | |
| **Warning activity** | Each warning: ledger key, time, forecast hour, probability. | |
| **SMS deliveries (numbers masked)** | One row per subscriber per warning: masked number, status, provider status, attempts. | Failed and uncertain rows. |
| **System health** | Prediction freshness, last forecast update, regional data, model file, threshold. | |
| **Recent scheduled checks** | The latest GitHub Actions runs of the hourly workflow. | Failed runs, gaps. |

Full phone numbers never appear anywhere in the dashboard. Rows show only masked numbers such as `+27 82 *** **67`.

### Delivery statuses

| Status | Meaning | Action |
|---|---|---|
| `submitted` | Accepted by Twilio; final result not yet known. | Press **Refresh delivery statuses** later. |
| `delivered` | Twilio confirmed delivery to the handset. | None. |
| `failed` | Definitive failure (invalid or unreachable number, landline, trial-account restriction, opt-out). | See §4. |
| `uncertain` / `pending` | The outcome is unknown, e.g. a network timeout while submitting. The message may or may not have been sent. | **Never resent automatically**, to avoid duplicate warnings. Check the message in the Twilio console. |
| `outbox` | Development mode only: written to the local outbox, not sent. | None. |

Delivery statuses are not pushed to the dashboard; there is no webhook. **Refresh delivery statuses** asks Twilio for the latest status of up to 100 `submitted` messages.

### SMS provider health and the controlled live test

The Administration page ends with **SMS provider health and controlled live test**. No secret, token or phone number is shown.

| Row | Meaning |
|---|---|
| SMS provider (Twilio) | *Configured* when `TWILIO_ACCOUNT_SID`, `TWILIO_AUTH_TOKEN` and a valid E.164 `TWILIO_FROM_NUMBER` are set. |
| Account type | *Trial* or *Full*, after **Check provider account** (one request to Twilio). A trial account can message verified numbers only. |
| Controlled live test | *Disabled* (`SMS_LIVE_TEST_ENABLED` not `true`), *provider not configured*, *no valid test recipient*, or *Ready*. |
| Public subscriber delivery | `SUBSCRIBER_ALERTS_ENABLED` as this deployment sees it. The hourly worker reads its own GitHub Actions variable. |
| Last controlled test | Time and result: *Accepted by provider*, *passed to the mobile network*, *Delivered to handset (confirmed by the provider)*, *Failed*, or *Outcome uncertain*. |

**SMS modes.**
1. **Simulation** (default): no provider request; messages are labelled *TEST ONLY — NOT A REAL WARNING*.
2. **Controlled live test**: one real SMS, to one allowlisted test phone, by an administrator, after confirmation.
3. **Public subscriber delivery**: `SUBSCRIBER_ALERTS_ENABLED`, disabled by default (§7).

**To run a controlled live test.**
1. Set, as private secrets (Streamlit secrets or the environment, never in the repository): `SMS_LIVE_TEST_ENABLED = "true"` and `SMS_TEST_RECIPIENT` = one E.164 number you are authorised to message (on a trial account it must be a verified number). The Twilio secrets must also be set.
2. Sign in, open **Administration**, check that *Controlled live test* reads *Ready*, and that the warning simulation is off.
3. Press **Send controlled SMS test**, read *"This will send one real SMS to the configured test recipient. Continue?"*, and press **Yes, send one SMS** (or **Cancel**).
4. The result shows *Accepted by provider*: this is **not** delivery. After a minute, press **Refresh test delivery status**; only *Delivered to handset (confirmed by the provider)* means the handset received it.
5. Set `SMS_LIVE_TEST_ENABLED` back to `false` when finished.

The message reads *MATATIELE SMS PROVIDER TEST. Controlled check only. NOT A WEATHER WARNING.* There is no field for typing a number, so a test cannot be sent to anyone else. The SMS log records the attempt as `configured-test-recipient`, never the number. Each attempt is reserved in the log before the provider is called: an interrupted request is shown as *Outcome uncertain*, and is never repeated automatically.

**Duplicate prevention (warnings).** The hourly worker reserves each warning hour in the public ledger before any SMS. A delivery record per warning and subscriber is reserved before sending. A repeated run therefore never sends twice, and a provider failure never deletes the warning record.

## 4. Handling failed notifications

1. Press **Refresh delivery statuses**.
2. For a `failed` row, read the provider status or error:

| Error | Meaning | Action |
|---|---|---|
| `recipient_opted_out` (Twilio 21610) | The resident replied STOP. The system has **already unsubscribed** them. | None. Never resend. |
| `trial_unverified_number` (21608) | The Twilio account is a **trial** and can only message verified numbers. | Upgrade the Twilio account (see the deployment guide). |
| `invalid_number`, `not_a_mobile`, `landline_or_unreachable`, `unreachable_route`, `provider_reported_undelivered` | The number cannot receive SMS. | Retrying will probably fail again. The resident can unsubscribe and register a different number. |
| `number_unreadable` | The stored number could not be decrypted, usually because the encryption key differs between Streamlit and GitHub Actions. | Fix the key configuration (deployment guide §4). |

3. To resend one definitive failure, choose it in **Retry selected delivery** and press the button. Each delivery can be sent at most **3 times in total**. Retries are refused for opted-out or unsubscribed residents.

## 5. Helping residents

- **"I did not get a code":** check the number, the delivery mode, and the Twilio console. Codes expire after 10 minutes. The limits are 1 code per minute, 3 per hour and 6 per day per number, and 60 codes per hour across the whole system.
- **"Please remove me":** ask the resident to use **Manage my subscription**, or to reply STOP. Administrators cannot see full numbers, so they cannot look a resident up by number. This is deliberate.
- **Privacy questions:** the store keeps the encrypted number, a keyed hash for lookup, the masked number, the area, consent version and time, status changes, and delivery outcomes. Unsubscribing deletes the encrypted number. Retention is automatic: never-verified numbers are deleted after 2 days; cancelled records, delivery records and alert copies after 30 days; rate-limit timestamps after 1 day. With the GitHub store, earlier versions of the file (including encrypted numbers) remain in the private repository's Git history. They are unreadable without the key; for full erasure, see the procedure in `evaluation_reports/RO3_deployment_security_review_2026-10-30.md` §4.

## 6. Routine maintenance

| Task | How often | How |
|---|---|---|
| Check that hourly runs succeed | Daily | Recent scheduled checks on the Administration page, or the repository's Actions tab. Healthchecks.io heartbeats alert on missed runs. |
| Review failed or uncertain deliveries | After each warning | Administration page, §4 |
| Twilio balance and account status | Weekly | Twilio console |
| Rotate the store token | Before it expires | Create a new fine-grained token, then update `SUBSCRIBER_STORE_TOKEN` in **both** Streamlit secrets and GitHub Actions secrets. |
| Back up the subscriber store | Monthly | The private repository keeps every version in its Git history. Restrict access to that repository. |
| Run the tests | Before every change | `python -m pytest tests/ -q` (fully mocked; no SMS and no network) |

**Abuse limits:** at most 60 verification codes an hour and 300 a day across the whole system, and 1 a minute, 3 an hour and 6 a day per number. When a limit is reached, residents see *The service is receiving too many requests*.

**Development outbox mode** is refused when `SUBSCRIBER_STORE=github`, because it shows codes on screen.

**Never** change the encryption or hash keys while subscribers exist. With new keys, the stored numbers can no longer be read or looked up. Rotating keys requires a migration script, which is not provided.

## 7. Switching subscriber warnings on and off

- **On:** in the repository, go to Settings → Secrets and variables → Actions → Variables, and set `SUBSCRIBER_ALERTS_ENABLED` = `true`.
- **Off (emergency stop):** set it to `false` or delete it. The next hourly run skips subscribers and records `subscriber_alerts: disabled`. Residents can still register.
- **Close registration:** set `SMS_DELIVERY_MODE` to `disabled` in Streamlit secrets. **Alerts → SMS alerts** then says registration is not open.

## 8. Officials' decision-support portal

Officials sign in at the dashboard address with `?portal=officials`. The portal is never linked from the resident pages. Each official has an individual account, and the administrator password does not open the portal.

**Creating an account** (owner or administrator):
1. Run `python 23_create_official_account.py`, then type the username and password. The password is not shown or saved.
2. Add the printed line (`username:pbkdf2_sha256$...`) to the `OFFICIAL_ACCOUNTS` secret in Streamlit, one line per official.
3. To remove an account, delete its line.

**What officials can do:**
- review active warnings, their timestamps and aggregate acknowledgements;
- view the ECMWF rainfall forecast around Matatiele;
- set a review or response status (*Under review, Monitoring, Response coordinated outside this system, Closed - no further action*) and add notes;
- review the history of warnings and actions, and download the actions as CSV.

Every record carries the official's username and the time. The portal does **not** dispatch or contact emergency services.

**Sign-in lockout:** after 10 wrong attempts in 15 minutes, sign-in is locked for 15 minutes for every session, counted separately from the administrator lockout.

**Records** are kept in `operations.json`, beside the subscriber file (or in the same private repository), and are not deleted automatically.

**Acknowledgement counts** are anonymous device counts. They indicate engagement; they are not counts of people, and are not proof of safety. A resident who clears their browser storage can acknowledge again, so treat the counts as indicative.

**Demonstrations on a development computer:** `SMS_DELIVERY_MODE=outbox python 24_create_dev_test_warning.py` creates one warning labelled *development test - not a real warning*, through the worker's real subscriber hook. It refuses to run against the real store and never touches the public ledger.

## 9. Troubleshooting

| Symptom | Likely cause |
|---|---|
| Run record shows `subscriber_alerts: not_configured` | Twilio secrets are missing from the workflow environment. |
| `subscriber_alerts: failed` with `subscriber_error: StoreError` | Store repository, token or keys are missing or wrong. |
| Admin page: *Subscriber store unavailable* | The same, in Streamlit secrets. |
| *SMS registration is temporarily unavailable* | Store or Twilio configuration is incomplete in Streamlit secrets. |
| Alerts says *the public warning record could not be reached* | The GitHub API could not be reached or is rate-limited. It retries after 10 minutes. |
| A resident received two SMS for one warning | Their number is also in `ALERT_TO_NUMBERS`, the original fixed recipient list. Remove it from one of the two lists. |
| *Send controlled SMS test* is greyed out | *Controlled live test* is not *Ready* (see the reason in that row), or the warning simulation is on. |
| Controlled test: *Failed* | The provider rejected it. On a trial account, the test number must be verified in the Twilio console. |
| Controlled test: *Outcome uncertain* | The request was interrupted. Check the Twilio console before trying again. |
| Controlled test stays *Accepted by provider* | The handset has not confirmed yet, or the network does not return delivery receipts. It is not reported as delivered. |
| *Save for offline use* is greyed out | The offline page template (`static/offline.html`) is missing from the deployment. |
| Saved offline dashboard shows an old time | The last retrievals failed, so the last good snapshot is offered. Fix the forecast connection; the snapshot is refreshed after the next successful run. |

## 10. Offline dashboard (saved snapshot)

- **What residents get.** **Save for offline use** (Home, and in More on phones) downloads one self-contained HTML page with the latest snapshot embedded. It opens from the phone's files with no connection, on any hosting, with tabs Home, Outlook, Alerts, Safety and More. It shows *OFFLINE — SAVED INFORMATION* and the time saved.
- **How the snapshot is prepared.** Each dashboard run builds a resident-safe snapshot from the genuine model output (never the on-screen simulation or the connectivity demonstration). It is written to `static/status.json` **only after a valid, current result**. A failed retrieval, out-of-date or partial data leaves the last good snapshot in place, and residents are offered that one. No administrator action is needed.
- **Content rules.** Allowed: saved time, forecast period, risk score and category, 35% threshold, warning decision, genuine warning and early alert, the 12-hour model outlook, a weather and forecast snapshot, safety advice and the national emergency numbers. Never: subscriber records, residents' phone numbers, credentials, API keys, officials' information or private logs. Tests check this.
- **Stale data.** The page computes the data age on the phone. After 2 hours it adds *Saved information may be out of date*, and outlook hours that have passed are faded and marked historical. Nothing is recalculated offline.
- **Connection lost while the dashboard is open.** The page shows *Connection lost — live updates paused* with **Open saved offline dashboard**, which needs no server. A failed retrieval ends the loading state, keeps the last data and labels it out of date; no warning decision is made from it. *Connection restored · latest data retrieved* appears only after a new successful retrieval.
- **Limits.** The offline dashboard does not receive new forecasts, model results or warnings, and the map is not available offline. SMS is a separate channel: it reaches phones without mobile data, but the sending system must be connected to the SMS provider.

