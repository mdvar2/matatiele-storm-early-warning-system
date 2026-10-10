# Matatiele Beta scheduled SMS integration

## Added files

- `18_scheduled_sms_worker.py`: refreshes genuine ECMWF inputs through the existing
  `12_live_forecast_and_predict.py`, then validates its actual Random Forest output.
- `.github/workflows/scheduled-storm-sms.yml`: hourly check at minute 12 UTC
  (minute 12 SAST), plus manual Run workflow. Uses Python 3.12 and existing requirements.
- `tests/test_scheduled_sms_worker.py`: isolated safety and durable-ledger tests.

The dashboard, trained model, 29 features, 35% threshold, forecast pipeline and
SMS message wording are preserved. Generated CSV files remain ignored by Git.
The ZIP's compiled bytecode is deliberately excluded.

## First dry-run test

From the project directory, with existing requirements installed:

```powershell
python 18_scheduled_sms_worker.py --dry-run
```

This makes a real forecast request and runs the existing model. It updates the
existing latest-prediction CSV only after successful inference. It does not send
SMS, create GitHub issues, or require Twilio/GitHub credentials. It does not append
prediction history; the existing dashboard retains its history handling.
There are no simulated forecasts or substituted probabilities.

A fresh, valid prediction prints the probability, 35% threshold and next-hour
SAST target. A threshold crossing in dry-run prints what would happen, without
submitting anything. API/model failure rejects the saved CSV for SMS purposes.

After you choose to make these local files available on your repository's default
branch, GitHub Actions > Scheduled Matatiele Storm Check > Run workflow executes
this same dry-run. Nothing has been pushed or activated by this integration.
Scheduled runs need the model and feature/threshold files already tracked in Git.

## SMS remains disabled

The workflow hard-codes `ENABLE_REAL_SMS: 'false'` and `--dry-run`; an existing
repository variable cannot silently activate it. Local execution defaults to
 dry-run even if ENABLE_REAL_SMS is set. Live execution requires BOTH `--live`
and `ENABLE_REAL_SMS=true`, and is restricted to GitHub Actions.
Do not activate live mode until the project owner explicitly approves it.

Only after approval would the workflow activation settings be changed. Live mode
needs Issues enabled, a token with issues-write permission, and repository secrets
TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN, TWILIO_FROM_NUMBER, ALERT_TO_NUMBERS. Never
commit these values or put them in issues, screenshots, or shared logs.

## Cross-run duplicate protection and failure behavior

The workflow uses one fixed `matatiele-hourly-sms` concurrency group with
cancel-in-progress false. In live mode, the worker checks every page of repository
issues, including closed issues, for a canonical UTC prediction-hour title. It
creates the issue reservation BEFORE invoking the existing Twilio function.
The same persisted issue blocks a subsequent runner even if its filesystem and
local SMS CSV are fresh. No issue is created in dry-run.

Do not delete reservations or edit their titles. A reservation is not delivery
confirmation. Once reserved, a failed, timed-out or interrupted submission is
blocked from automatic retry and needs manual review. If GitHub confirmation is
lost after issue creation, no SMS is sent and a subsequent run finds the issue.
Missing credentials, invalid/nonfinite values, stale timestamps, a wrong source,
an expired target, a wrong threshold or API failure stop sending.
Only safe status strings are posted; credentials and recipients are excluded.

The list/create operation relies on this serialized workflow and is not an atomic
transaction for independent concurrent callers. Do not launch another live worker
outside this concurrency group. GitHub Actions is the sole real storm-warning sender. The dashboard has no storm-warning send button or function call; administrators retain the explicit Send Test SMS connectivity check, labelled NO WEATHER WARNING. Dashboard forecast refreshes never send weather warnings. Its local CSV records test submissions; it is not a shared Actions reservation store.
GitHub schedules can be delayed and are not a guaranteed emergency delivery service.
Submitted SMS is not confirmed delivery; check Twilio Console separately.

## Checks

```powershell
python -m py_compile 18_scheduled_sms_worker.py
python -m unittest discover -s tests -p test_scheduled_sms_worker.py -v
```

Tests mock all forecast, GitHub and SMS side effects. Test fixtures are only test
inputs; they never replace genuine production forecasts or enter the dashboard.

## Final Beta sender policy and configuration

Real storm warnings are reserved for `18_scheduled_sms_worker.py` inside the single
`matatiele-hourly-sms` Actions concurrency group. Do not add another warning sender
or invoke the low-level SMS warning helper independently. The worker refreshes
ECMWF, requires a fresh valid Matatiele Random Forest output, and uses the existing
35% threshold. Both live activation gates remain disabled in the workflow.

A partial submission returns `partial`, with submitted and failed/uncertain counts;
it never reports complete success. The worker marks the run unsuccessful and
retains its issue reservation for manual review. Timeout, unknown acceptance or
missing provider ID must never cause an automatic retry. Review each recipient
in Twilio Console before any recovery; issue reservations are not delivery receipts.
Do not delete reservations to force retries, which can duplicate accepted messages.

Local administrator/Twilio settings belong in ignored `.streamlit/secrets.toml`.
The committed `.streamlit/secrets.toml.example` contains empty placeholders only.
Actions uses encrypted repository secrets `TWILIO_ACCOUNT_SID`,
`TWILIO_AUTH_TOKEN`, `TWILIO_FROM_NUMBER`, and `ALERT_TO_NUMBERS`; CLI workers do
not load the local Streamlit file. Never commit the private file or secret values.

`17_validate_warning_pipeline.py` now runs only mocked worker safety tests; its
former simulated 60% warning submission is removed. It cannot submit SMS.
Successful API submission remains distinct from confirmed recipient delivery.
Live automatic SMS still requires explicit owner approval and deployment of the
reviewed local files together, including `app_config.py`.
