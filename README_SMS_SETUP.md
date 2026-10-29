# Matatiele Beta SMS setup and safety

## Approved LIVE configuration

The project owner has approved automatic SMS. The current workflow sets
`ENABLE_REAL_SMS: 'true'` and runs `python 18_scheduled_sms_worker.py --live`.
It runs hourly at minute 12 UTC (also minute 12 SAST) and supports manual dispatch.
GitHub schedules can be delayed; they are not a guaranteed emergency service.

The independent worker invokes `12_live_forecast_and_predict.py` to retrieve
actual ECMWF inputs through Open-Meteo and run the saved 29-feature Random Forest.
Only a fresh, valid Matatiele prediction at or above the existing **35% threshold**
is eligible for warning submission. Below threshold, no warning is sent.
It needs the tracked model, feature list and threshold artifacts; it does not need
an open Streamlit dashboard or append dashboard prediction history.

## Execution modes

| Mode | Current behaviour |
| --- | --- |
| Scheduled LIVE | Cron runs genuine inference and submits an eligible warning only after safeguards pass. |
| Manual LIVE | **Run workflow** with `send_test_sms` unselected follows the same LIVE pathway; it is not a dry-run. |
| Manual connectivity test | Explicitly select `send_test_sms`; calls `send_test_sms()` without forecast inference or a weather warning. |
| Local dry-run | `--dry-run` retrieves genuine forecasts and predicts, without SMS or GitHub ledger writes. |

Local execution defaults to dry-run even if `ENABLE_REAL_SMS` is set. LIVE execution
requires both `--live` and `ENABLE_REAL_SMS=true`, and is restricted to GitHub Actions.
Do not invoke another LIVE worker outside the workflow's concurrency group.

## Secure configuration

GitHub Actions uses encrypted repository secrets:

- `TWILIO_ACCOUNT_SID`
- `TWILIO_AUTH_TOKEN`
- `TWILIO_FROM_NUMBER`
- `ALERT_TO_NUMBERS`

For the current trial setup, use exactly the single Twilio-verified recipient in
E.164 format. The connectivity path checks configuration and recipient count;
trial recipient verification must be checked in Twilio Console. Never put phone
numbers or credentials into workflow inputs, issues, screenshots or committed files.

The workflow supplies its GitHub token and requires Issues enabled, `contents: read`
and `issues: write` permissions. Dashboard credentials are separate: local settings
belong in Git-ignored `.streamlit/secrets.toml`, using the blank
`.streamlit/secrets.toml.example` template. CLI/Actions workers use environment
configuration, not that local file. Never commit the private settings file.

## Manual connectivity test

Use **Actions > Scheduled Matatiele Storm Check > Run workflow** and explicitly
select `send_test_sms`. This submits only the existing message:

> MATATIELE SMS TEST. Notification service check only. NO WEATHER WARNING.

The worker requires manual dispatch and confirmation. It never sends a simulated
storm warning. A separate `CONNECTIVITY-TEST-RUN-` issue reservation blocks reruns
of the same Actions run, including uncertain submissions. A new manual dispatch
has a new run ID and can send another test: review Twilio before repeating it.

Successful Twilio API submission is **not confirmed recipient delivery**. Check
Twilio Console and the recipient's phone; neither a successful run nor a reservation
alone proves receipt. The dashboard retains administrator-controlled test SMS,
with simulation preview off, but cannot independently send storm warnings.

## Duplicate prevention and failure handling

- The fixed `matatiele-hourly-sms` concurrency group serializes runs with
  `cancel-in-progress: false`.
- Before warning submission, the worker searches every page of GitHub issues,
  including closed issues, for the canonical UTC forecast-hour reservation.
- It creates the reservation **before** calling Twilio. An existing reservation
  blocks repeat submission across separate runners, even with fresh local logs.
- Never delete reservations or edit their titles. They are not delivery receipts.
- Partial submissions return `partial`, with submitted and failed/uncertain counts;
  the worker fails the run and keeps the reservation for manual review.
- Timeouts, missing provider IDs and uncertain responses receive no automatic retry.
  Review each recipient in Twilio Console before recovery; forcing a retry can
  duplicate an accepted message.
- API/model failures, missing configuration, invalid/nonfinite data, stale or expired
  targets, unexpected source/location/threshold and ledger failures stop sending.
- **CAPE normalisation:** Open-Meteo interpolates ECMWF's 3-hourly CAPE to hourly values,
  which can overshoot slightly below zero. `cape_normalisation.py` sets finite CAPE in
  [-50, 0) J/kg to 0 for the current- and previous-hour model inputs; anything below
  -50, missing or non-finite stays invalid and stops the run. The prediction file and
  run record keep the original value (`cape_raw`, `cape_original_j_kg`) and the status
  (`unchanged`, `normalised`, `invalid`). The worker rejects any inconsistent report.
  The -50 J/kg cutoff is provisional and under evaluation.
  Old saved predictions are not substituted after a failed inference run.
- Only safe status information is posted publicly; credentials and recipients are
  excluded. The issue list/create operation relies on workflow serialization and
  is not atomic for independent concurrent senders.
- **Reservation lock (R3):** after the issue search and before creating the issue,
  the worker creates a repository label `sms-lock:<forecast-hour key>`. Label names
  are unique, so GitHub rejects a second creation (`already_exists`) and that run
  sends nothing. If the label API is unavailable the worker falls back to the issue
  ledger alone (`reservation_lock: unavailable` in the run record). If issue creation
  fails after the lock, the worker deletes the label before any SMS so a later run can
  retry (`released`).
- **Abandoned-lock recovery:** each lock's description names its holder run. A lock with
  no ledger issue whose holder run has **completed** (or is an earlier attempt of the same
  run) was abandoned before any SMS, because SMS is only sent after the issue exists. A
  later run then re-checks the ledger and takes over through a next-generation label
  (`#gen2`, `#gen3`, also atomic): `reservation_lock: recovered`. If the holder may still
  be running, or this cannot be proven, the run stays suppressed (`already_exists`,
  `held_holder_unknown`). This needs the read-only `actions: read` permission.
- **Permission probe:** every run creates and deletes a throwaway `sms-probe:<run>` label
  and reads its own run status; the job summary and heartbeats show
  `lock_label_permission` and `run_status_permission` (`ok` expected). It never touches
  `sms-lock:` labels or ledger issues. Never delete `sms-lock:` labels by hand.

GitHub Actions is the sole storm-warning sender. Dashboard refreshes never send
weather warnings. Local CSV logs and GitHub reservations remain separate stores;
do not add another independent weather-warning sender.

## Safe local checks

```powershell
python 18_scheduled_sms_worker.py --dry-run
python -m pytest tests/ -q
```

Dry-run updates the latest prediction CSV only after successful genuine inference;
it sends no SMS, requires no Twilio/GitHub credentials and creates no reservations.
Tests mock provider and GitHub operations. Historical replay tests use genuine saved
evaluation outputs, not current forecasts, and skip when that local file is absent.
`17_validate_warning_pipeline.py` runs mocked safety tests only; it cannot send SMS.

## Operational monitoring (run records and heartbeats)

Monitoring never sends SMS, never changes a warning decision and cannot fail the job.

- **Run record (R1):** every worker run writes a sanitised record; the job summary shows
  it. `RUN_RECORD_PUBLISH: 'false'` keeps it out of public issues.
- **Heartbeats (R2):** `20_send_heartbeat.py` reports each run to Healthchecks.io,
  which raises alerts on its own clock, independently of the GitHub schedule.

| Repository secret | Check | Meaning of an alert |
| --- | --- | --- |
| `HC_EXECUTION_URL` | HB-1 | No run for 10 h, or a run started but never finished |
| `HC_FORECAST_URL` | HB-2 | No validated forecast and prediction for 12 h |
| `HC_FAILURE_URL` | HB-3 | A run failed (category in the ping body); clears on the next success |
| `HC_WARNING_URL` | HB-4 | **An eligible genuine warning was not accepted by the provider.** Never cleared automatically: review, then acknowledge manually |

Secrets hold full ping URLs (`https://hc-ping.com/<uuid>`); never commit them. A missing
secret skips that check. To switch heartbeats off, delete the secrets. Heartbeat bodies
contain enumerated statuses only: no probability, message text, numbers or identifiers.

- **External hourly trigger (R3, active since 29 October 2026):** GitHub's cron ran only
  about 21% of hours. The Cloudflare Worker in `ops/external-trigger/` starts this
  workflow at minute 5 of every hour through `workflow_dispatch` with `trigger_source=external_scheduler`;
  the GitHub cron stays as a backup. The worker refuses `--test-sms` from that source.
  Each run record and heartbeat records `trigger_source` (`github_schedule`,
  `external_scheduler`, `manual`). Measure coverage with
  `python 21_measure_execution_coverage.py --fetch`.

## Verified Beta evidence and remaining limits

- Scheduled LIVE run **#6** succeeded with a genuine **0.00%** prediction, below
  35%; no storm-warning SMS was sent.
- Manual connectivity-test run **#4** resulted in confirmed phone receipt of the
  explicitly labelled **NO WEATHER WARNING** message.
- **77 tests and 28 subtests** passed, covering thresholds, configuration,
  duplicate protection, partial submissions and uncertain outcomes.

A genuine high-risk automatic warning submission/delivery has not yet been observed;
that pathway is covered by controlled mocked tests. These results do not establish
forecast accuracy or guaranteed emergency delivery. The academic Beta remains
Internet-dependent. Sensors, edge processing, offline resilience, LoRa and Matatiele
field validation remain future work. This is not an official SAWS warning service.
