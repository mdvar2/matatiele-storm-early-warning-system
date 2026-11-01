# Deployment Security Review: Resident SMS Registration

*Date:* 30 October 2026 · *Scope:* the resident subscription system on branch `research-dashboard-ui-redesign`, not yet deployed. It covers:

- `subscriptions.py`, `subscriber_store.py` and `subscriber_alerts.py`;
- `resident_pages.py`;
- the admin sign-in in `16_dashboard.py`;
- the worker hook and the workflow environment.

**Verdict.** The code is ready for a controlled pilot. **Public registration must stay closed** until the blockers in §1 are cleared; most of them need the project owner's accounts or the institution. Subscriber warnings remain off: `SUBSCRIBER_ALERTS_ENABLED` is unset and `SMS_DELIVERY_MODE` is unset, which means `disabled`.

## 1. Blockers before public registration

| # | Blocker | Why it blocks | Who |
|---|---|---|---|
| B1 | **Twilio account is a trial.** | A trial account sends only to verified numbers (error 21608). Residents would never receive their code. | Owner: upgrade the account; check South African sender-ID rules. |
| B2 | **Subscriber store not provisioned.** | A private repository, a fine-grained token (Contents read/write on that repository only), and two keys are needed, set **identically** in Streamlit secrets and GitHub Actions secrets. | Owner |
| B3 | **Keys need an offline backup.** | Losing `SUBSCRIBER_ENCRYPTION_KEY` makes every stored number unreadable; all residents would have to re-register. | Owner: keep both keys in a password manager. |
| B4 | **Data protection and ethics.** | Collecting members of the public's phone numbers is processing personal information under POPIA, and is likely to need research-ethics clearance. The following must be confirmed in writing: <ul><li>who the responsible party is;</li><li>the privacy notice;</li><li>the retention period (§3);</li><li>ethics approval.</li></ul> | Owner, supervisor, CUT ethics committee |
| B5 | **Strong administrator password.** | The Administration page can resend SMS and shows masked delivery data. Sign-in is now throttled (§2), but the password must be long and random (≥ 16 characters) and stored only in Streamlit secrets. | Owner |
| B6 | **Consent wording on STOP.** | The consent text says residents can reply STOP. That works only if the sender can receive replies. | Owner: confirm with Twilio, or change the wording (and `CONSENT_VERSION`). |
| B7 | **Deployment approval.** | The branch is local only. | Owner |

Not blockers, but recommended: a CAPTCHA on Subscribe; Twilio delivery webhooks (need a public endpoint, which Streamlit Cloud cannot provide); a restricted Twilio API key instead of the account auth token.

## 2. Findings and actions taken in this review

| Area | Finding | Status |
|---|---|---|
| **Number enumeration** | The Subscribe form said "already subscribed". | **Fixed.** Every number gets the same reply and next step; only the phone's owner receives an "already subscribed" SMS. Manage was already safe. Tests: `test_subscribe_does_not_reveal_registered_numbers`, `test_manage_does_not_reveal_unregistered_numbers`. |
| **Admin brute force** | Unlimited password attempts. | **Fixed.** Ten failures in 15 minutes lock sign-in for every session on the server. A new browser session cannot reset the count. Test: `test_repeated_wrong_passwords_lock_sign_in_for_every_session`. |
| **SMS cost abuse** ("SMS pumping") | Only per-number and hourly global limits existed, allowing up to 1,440 codes a day. | **Fixed.** Global daily cap of 300 codes, plus 60 an hour, plus per-number limits of 1 a minute, 3 an hour and 6 a day. Test: `test_global_daily_cap_bounds_sms_cost`. |
| **Development mode in production** | Outbox mode shows codes on screen. Against the real store, this would let anyone verify any number. | **Fixed.** Outbox mode is refused when `SUBSCRIBER_STORE=github`. Test: `test_development_outbox_can_never_use_the_real_store`. |
| **Store growth** | Nothing except the event log was ever deleted. The GitHub contents API also returns no content for files over 1 MB, which would have broken the store as it grew. | **Fixed.** Retention rules apply on every write (§3), and files over 1 MB are read in raw form. Tests: `test_retention_deletes_unverified_cancelled_and_old_records`, `test_github_store_reads_files_over_one_megabyte`. |
| **Concurrency** | Many residents, plus the worker, writing at once. | **Verified.** Local file: whole-transaction lock. GitHub: compare-and-swap on the file SHA with retries. Ten residents registering, verifying and unsubscribing concurrently, while two worker runs race on one warning: no lost updates and no duplicate SMS. Tests: `test_concurrent_requests_local_file_store`, `test_concurrent_requests_github_store` (conflicts really occurred and were resolved), and a 3-process × 40-thread stress run. Under very heavy contention the GitHub store can return "please try again"; it never loses or corrupts data. |
| **Restarts** | State held in the browser session. | **Verified.** Every action reads and writes the persistent store, so a restart between any two steps preserves state. Test: `test_full_lifecycle_survives_restarts_between_every_step`. The browser walkthrough restarts the server between entering the code and verifying it. |
| **Encryption** | Fernet (AES-128-CBC with HMAC-SHA256) for numbers; HMAC-SHA256 with a separate key for lookup; masked numbers for display. | Adequate. Keys are only in secrets, never in the repository. Without the keys, a copy of the store reveals no numbers. |
| **Secrets** | Streamlit holds the Twilio credentials, store token and both keys; GitHub Actions holds the same set. | Acceptable. Anyone with access to the Streamlit app settings can read them, so limit collaborators. Nothing secret is printed, logged, or written to run records (counts only). |
| **Repository permissions** | The token needs Contents read/write on the private store repository only. | Use a fine-grained token with an expiry date, and rotate it before expiry (admin manual §6). |
| **Deletion** | Unsubscribing removes the encrypted number immediately; retention deletes the rest later (§3). | **Residual risk:** the GitHub backend commits every change, so *previous versions* of the file, including encrypted numbers of people who have left, remain in the private repository's Git history. They are unreadable without the key. Full erasure requires recreating the repository (§4). Disclose this in the privacy notice. |
| **Failure recovery** | — | GitHub unreachable: residents see "temporarily unavailable"; the worker records `subscriber_alerts: failed`; the existing warning is unaffected. Worker crash mid-delivery: rows stay `pending` and are never resent automatically (no duplicates). The admin can check them in the Twilio console. Corrupt store: restore an earlier version from the private repository's history. Lost keys: residents must re-register (B3). |
| **Model and warning integrity** | — | No change to the model, features, 35% threshold, forecast pipeline, ledger or warning text. With subscriber alerts off, the worker gives identical results in all 21 equivalence scenarios. The simulation never reaches subscribers (`test_simulation_never_reaches_subscribers`). |

## 3. Retention (applied automatically on every write)

| Data | Deleted after |
|---|---|
| A number that was never verified (pending) | 2 days |
| An unsubscribed record (already without its number) | 30 days |
| Delivery records, which hold masked numbers, and alert copies | 30 days. The public ledger remains the permanent warning record. |
| Verification rate-limit timestamps | 1 day |
| Event log | Most recent 300 entries |

## 4. Procedure for full erasure from Git history (owner, optional)

1. Download the current `subscribers.json` from the private store repository.
2. Create a new private repository and upload the file as its first commit.
3. Point `SUBSCRIBER_STORE_REPO` at the new repository in **both** Streamlit and GitHub, and issue a new token scoped to it.
4. Delete the old repository.

The keys stay the same.

## 5. Addendum: warning interactions and the officials' portal

| Area | Assessment |
|---|---|
| **Official authentication** | Each official has an individual account, with a PBKDF2-SHA256 hash (310,000 iterations) kept in the `OFFICIAL_ACCOUNTS` secret. No plain passwords are stored. Unknown usernames take the same time to check as known ones. Sign-in locks for 15 minutes after 10 failures, across all sessions. The portal appears only at `?portal=officials`: a URL parameter alone grants nothing, and the administrator password does not open it. |
| **Attribution** | Every review status and note is stored with the official's username and a UTC timestamp, in an append-only actions list that is not deleted automatically. |
| **No dispatch** | The portal records decisions taken outside the system. No status triggers a message, a call or a dispatch (`test_no_dispatch_status_exists`). |
| **Acknowledgements** | One per device and warning. The server stores only a keyed hash of a random identifier held in the browser's local storage. Acknowledgements are anonymous and say nothing about anyone's safety; the wording is tested. **Limitation:** clearing browser storage or using another browser allows another acknowledgement, so counts are *indicative engagement*, not verified people. |
| **Genuine data only** | Warnings come from the public ledger the worker writes. Development test warnings exist only in local outbox mode, which is refused against the real store, and are labelled "not a real warning" on every screen. The simulation creates no warnings or records (`test_simulation_creates_no_warning_events`). |
| **Emergency numbers** | Only the national numbers 10111, 10177 and 112, checked against SAPS and government sources. No local number is listed until one is verified (open item for the owner). |
| **New blocker** | **B8:** before officials use the portal, confirm with the municipality who is authorised, create their accounts, and agree how long operational records are kept. |
