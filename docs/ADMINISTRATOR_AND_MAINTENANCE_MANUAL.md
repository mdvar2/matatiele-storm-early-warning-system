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
3. Press **Log Out** when you finish. The Administration page is never available to residents. If a session loses admin access, it returns to the Dashboard.

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
- **Privacy questions:** the store keeps the encrypted number, a keyed hash for lookup, the masked number, the area, consent version and time, status changes, and delivery outcomes. Unsubscribing deletes the encrypted number.

## 6. Routine maintenance

| Task | How often | How |
|---|---|---|
| Check that hourly runs succeed | Daily | Recent scheduled checks on the Administration page, or the repository's Actions tab. Healthchecks.io heartbeats alert on missed runs. |
| Review failed or uncertain deliveries | After each warning | Administration page, §4 |
| Twilio balance and account status | Weekly | Twilio console |
| Rotate the store token | Before it expires | Create a new fine-grained token, then update `SUBSCRIBER_STORE_TOKEN` in **both** Streamlit secrets and GitHub Actions secrets. |
| Back up the subscriber store | Monthly | The private repository keeps every version in its Git history. Restrict access to that repository. |
| Run the tests | Before every change | `python -m pytest tests/ -q` (fully mocked; no SMS and no network) |

**Never** change the encryption or hash keys while subscribers exist. With new keys, the stored numbers can no longer be read or looked up. Rotating keys requires a migration script, which is not provided.

## 7. Switching subscriber warnings on and off

- **On:** in the repository, go to Settings → Secrets and variables → Actions → Variables, and set `SUBSCRIBER_ALERTS_ENABLED` = `true`.
- **Off (emergency stop):** set it to `false` or delete it. The next hourly run skips subscribers and records `subscriber_alerts: disabled`. Residents can still register.
- **Close registration:** set `SMS_DELIVERY_MODE` to `disabled` in Streamlit secrets. The SMS Alerts page then says registration is not open.

## 8. Troubleshooting

| Symptom | Likely cause |
|---|---|
| Run record shows `subscriber_alerts: not_configured` | Twilio secrets are missing from the workflow environment. |
| `subscriber_alerts: failed` with `subscriber_error: StoreError` | Store repository, token or keys are missing or wrong. |
| Admin page: *Subscriber store unavailable* | The same, in Streamlit secrets. |
| *SMS registration is temporarily unavailable* | Store or Twilio configuration is incomplete in Streamlit secrets. |
| Warning History says *temporarily unavailable* | The GitHub API could not be reached or is rate-limited. It retries after 10 minutes. |
| A resident received two SMS for one warning | Their number is also in `ALERT_TO_NUMBERS`, the original fixed recipient list. Remove it from one of the two lists. |
