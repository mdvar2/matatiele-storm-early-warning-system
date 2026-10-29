# External hourly trigger (R3): prepared, NOT active

GitHub's `schedule` event is best effort. Between 10 and 29 October 2026 the
`'12 * * * *'` cron ran in 95 of 443 hourly slots (21.4%), with a median gap of
4.8 h. This folder contains an external trigger that asks GitHub to run the
existing workflow every hour. **Nothing here is deployed.** Activation needs the
project owner's approval, a new token and a third-party account.

## How it works

```
Cloudflare Cron (minute 5, UTC) --POST workflow_dispatch--> GitHub Actions
   inputs: send_test_sms=false, trigger_source=external_scheduler, scheduled_for=<slot>
GitHub cron (minute 12)          --schedule event-------->  same workflow (backup)
```

* The trigger only starts the workflow. Forecasting, the 0.35 threshold, recipients,
  SMS sending and duplicate prevention stay inside the unchanged GitHub workflow.
* The trigger cannot request the connectivity SMS: its inputs are fixed, and the
  worker refuses `--test-sms` when `trigger_source=external_scheduler`.
* Two runs per hour (external at :05, GitHub backup at :12) cannot send two warnings
  for the same forecast hour: runs are serialised by the `matatiele-hourly-sms`
  concurrency group, and each forecast hour is reserved by an issue plus an atomic
  `sms-lock:<key>` label. See the test evidence in `tests/test_r3_trigger.py`.
* A failed dispatch is retried once (5xx or network error only). A duplicated
  dispatch is harmless for the same reason.

## Option comparison

| | Cloudflare Workers Cron (recommended) | cron-job.org (simpler alternative) |
|---|---|---|
| Cost | Free plan includes Cron Triggers (check current limits) | Free, donation-funded |
| Where the token lives | Encrypted Worker secret; not visible after saving | Stored in the cron-job.org job's request header |
| Logic | Code in this folder: fixed inputs, input validation, one retry, no token logging; unit-tested | A plain HTTP request configured in a web form |
| Failure visibility | Failed invocations listed in Cron Events; worker throws on failure | Execution history and optional failure e-mails |
| Setup effort | Node.js + `wrangler` CLI, Cloudflare account | Web form only |
| Public endpoint | None (`workers_dev = false`, no fetch handler) | None on our side |

Either way, GitHub Actions remains the only SMS sender, and the GitHub cron stays as a
backup. Healthchecks.io HB-1 (R2) alerts if runs stop, whichever scheduler fails.

## Token (both options)

Create a **fine-grained personal access token** (GitHub → Settings → Developer settings):

* Resource owner: the repository owner; **Only select repositories:** this repository only.
* Repository permissions: **Actions: Read and write** (Metadata: read is added
  automatically). Nothing else.
* Expiry: set one (for example 90 days) and record the renewal date. An expired token
  causes `rejected_http_401`; the GitHub cron backup keeps running.
* Never commit the token, paste it into issues or put it in `wrangler.toml`.

## Option A: Cloudflare Worker (after approval)

```bash
cd ops/external-trigger
node --test                                   # offline tests, fetch mocked
npx wrangler login
npx wrangler secret put GITHUB_DISPATCH_TOKEN # paste the token when prompted
npx wrangler deploy
```

Check: Cloudflare dashboard → Workers → `matatiele-storm-trigger` → Cron Events show
`outcome=dispatched`; GitHub Actions shows `workflow_dispatch` runs at about :05, and
their run records show `trigger_source: external_scheduler`.

**Disable:** delete the cron trigger (or the Worker) in Cloudflare, then revoke the token.

## Option B: cron-job.org (after approval)

Create one job:

* URL: `https://api.github.com/repos/mdvar2/matatiele-storm-early-warning-system/actions/workflows/scheduled-storm-sms.yml/dispatches`
* Schedule: every hour at minute 5; time zone UTC.
* Method `POST`. Headers: `Authorization: Bearer <token>`,
  `Accept: application/vnd.github+json`, `X-GitHub-Api-Version: 2022-11-28`,
  `Content-Type: application/json`.
* Body: `{"ref":"main","inputs":{"send_test_sms":"false","trigger_source":"external_scheduler"}}`
  (cron-job.org cannot insert the slot time, so `scheduled_slot_utc` shows `not_available`).
* Success = HTTP 204. Enable failure notifications.

## Measuring the effect

Coverage is not claimed as improved until it is measured:

```bash
python 21_measure_execution_coverage.py --fetch --since <activation time>
```

Compare `slot_coverage` and `freshness_75min` for all events with the 21.4% and 25.6%
baseline over at least 14 days. The runs API does not show dispatch inputs, so external
and manual dispatches are separated with `trigger_source` in run records or HB-1 payloads.
