# Deployment and Configuration

This guide explains how to switch on resident SMS registration and subscriber warnings. It is for the project owner and whoever deploys the system.

> **Current state.** This code is on the `research-dashboard-ui-redesign` branch. It has **not** been pushed or deployed.
>
> - With no new configuration, the deployed system behaves exactly as before.
> - Subscriber warnings are off by default (`SUBSCRIBER_ALERTS_ENABLED` is unset).
> - SMS registration shows *not open yet* (`SMS_DELIVERY_MODE` is unset, which means `disabled`).
>
> Every step below needs the owner's accounts and approval. Never paste a secret value into chat, an issue, a commit or a log.

---

## 1. External services and their restrictions

| Service | Used for | Restriction to know |
|---|---|---|
| **Twilio** | Verification codes and warning SMS | A **trial account can only send to numbers verified in the Twilio console** (error 21608). Trial messages also begin with a "Sent from your Twilio trial account" prefix. **Public registration needs an upgraded (paid) account.** Each SMS is billed per segment of up to 160 characters; the warning and code messages are one segment each. Check Twilio's current South Africa pricing and sender-ID rules before launch. |
| **Twilio STOP handling** | Opt-out | STOP replies only work if the sender can receive replies, which depends on the sender number and the South African network. The system honours Twilio's opt-out error (21610) automatically, but the **web unsubscribe is the guaranteed route**. |
| **GitHub (private repository)** | Persistent encrypted subscriber store | Read/write via the contents API with a fine-grained token. The rate limit (5,000 requests an hour) is ample. |
| **GitHub (public repository)** | Warning ledger and public warning history | Unauthenticated reads are limited to 60 an hour per IP; the dashboard caches for 10 minutes. |
| **Streamlit Community Cloud** | Hosting the dashboard | No persistent disk, so the subscriber store **must** use the GitHub backend. |
| **Open-Meteo (ECMWF)** | Forecast | Unchanged. |

**Legal (POPIA).** Storing residents' phone numbers makes the project a *responsible party* under South Africa's Protection of Personal Information Act. Before opening public registration, confirm with the supervisor or institution:

- who the responsible party is;
- the privacy notice;
- the retention period.

The consent text is versioned (`CONSENT_VERSION` in `subscriptions.py`). If you change the wording, change the version.

## 2. Create the private subscriber store

1. Create a new **private** GitHub repository, for example `matatiele-subscribers`. Initialise it with a README so the `main` branch exists. Keep the subscriber file out of the public application repository.
2. Create a **fine-grained personal access token**:
   - **Repository access:** only that private repository.
   - **Permissions:** Contents → *Read and write*. No other permissions.
   - **Expiry:** set one, and note the date for rotation.
3. The system creates `subscribers.json` itself on first use.

## 3. Generate the keys (once)

Run each command on your own computer and store each result directly as a secret. Never commit the values.

```bash
python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"   # SUBSCRIBER_ENCRYPTION_KEY
python -c "import secrets; print(secrets.token_urlsafe(48))"                                # SUBSCRIBER_HASH_KEY
```

The **same two values** must go into Streamlit secrets and into GitHub Actions secrets. If they differ, the worker cannot read the numbers, and the deliveries fail with `number_unreadable`. Do not change the keys once subscribers exist.

## 4. Settings reference

| Setting | Streamlit secrets (dashboard) | GitHub Actions (worker) | Value |
|---|---|---|---|
| `SMS_DELIVERY_MODE` | ✔ | already set to `twilio` in the workflow | `disabled` (default), `outbox` (local development only), `twilio` |
| `TWILIO_ACCOUNT_SID`, `TWILIO_AUTH_TOKEN`, `TWILIO_FROM_NUMBER` | ✔ | ✔ (existing secrets) | Twilio account |
| `SUBSCRIBER_STORE` | ✔ `github` | already set to `github` in the workflow | `file` (local default) or `github` |
| `SUBSCRIBER_STORE_REPO` | ✔ | **repository variable** | `owner/private-repo` |
| `SUBSCRIBER_STORE_TOKEN` | ✔ | **secret** | fine-grained token from §2 |
| `SUBSCRIBER_ENCRYPTION_KEY`, `SUBSCRIBER_HASH_KEY` | ✔ | **secrets** | from §3 |
| `SUBSCRIBER_STORE_FILE`, `SUBSCRIBER_STORE_BRANCH` | optional | – | defaults `subscribers.json`, `main` |
| `SUBSCRIBER_ALERTS_ENABLED` | – | **repository variable** | `true` to send warnings to subscribers |
| `ADMIN_PASSWORD` | ✔ (existing) | – | administrator sign-in |

In **Streamlit Cloud**, add the settings under App → Settings → Secrets (TOML):

```toml
SMS_DELIVERY_MODE = "twilio"
SUBSCRIBER_STORE = "github"
SUBSCRIBER_STORE_REPO = "owner/matatiele-subscribers"
SUBSCRIBER_STORE_TOKEN = "…"           # paste in the Streamlit console only
SUBSCRIBER_ENCRYPTION_KEY = "…"
SUBSCRIBER_HASH_KEY = "…"
TWILIO_ACCOUNT_SID = "…"
TWILIO_AUTH_TOKEN = "…"
TWILIO_FROM_NUMBER = "…"
```

In **GitHub**, go to the application repository → Settings → Secrets and variables → Actions:

- **Secrets:** `SUBSCRIBER_STORE_TOKEN`, `SUBSCRIBER_ENCRYPTION_KEY`, `SUBSCRIBER_HASH_KEY`.
- **Variables:** `SUBSCRIBER_STORE_REPO`, and `SUBSCRIBER_ALERTS_ENABLED` (set this only when you are ready).

## 5. Recommended rollout

1. **Merge and deploy the branch** (owner approval). Nothing changes for residents yet, because registration is disabled.
2. **Rehearse locally** in development mode. No SMS is sent.
   ```bash
   SMS_DELIVERY_MODE=outbox streamlit run 16_dashboard.py
   ```
   Codes and warnings go to `outputs/subscribers/dev_outbox.jsonl` and are shown on screen under a *DEVELOPMENT MODE* banner. Local development keys are generated automatically in `outputs/subscribers/dev_keys.json`, which is git-ignored.
3. **Trial test with Twilio.** Set the Streamlit secrets with `SMS_DELIVERY_MODE = "twilio"`. This opens the registration form on the public dashboard, so keep the trial period short. Register **only a Twilio-verified number**, receive the code, and confirm the subscription is active.
4. **Enable subscriber warnings:** set the variable `SUBSCRIBER_ALERTS_ENABLED` = `true`. Warnings are sent only when the model reaches 35%; nothing is sent on dry hours. Check the next run's summary for `subscriber_alerts`.
5. **Upgrade the Twilio account** before announcing registration to the public. Until then, codes to unverified numbers fail. The resident sees *The verification SMS could not be sent*.
6. **Announce** registration to residents, with the [Resident User Manual](RESIDENT_USER_MANUAL.md).

**Emergency stop:** set `SUBSCRIBER_ALERTS_ENABLED` to `false` (stops warnings) or `SMS_DELIVERY_MODE` to `disabled` (closes registration). Neither affects forecasts or the dashboard.

## 6. Verifying a deployment

- **Run the tests:** `python -m pytest tests/ -q`. All tests are mocked and send no SMS.
- **Administration page:**
  - SMS delivery mode *Twilio (live)*;
  - Subscriber store *private GitHub repository*;
  - Encryption *Configured*;
  - no *DEVELOPMENT MODE* banner.
- **After hourly runs with the flag on:** on dry hours (below 35%) the subscriber step does not run, so the run summary shows `subscriber_alerts: not_attempted`. On a warning hour it shows `sent`, `partial`, `no_active_subscribers`, `not_configured` or `failed`, with counts only.
