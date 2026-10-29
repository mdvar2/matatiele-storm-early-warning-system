# External hourly trigger (R3): prepared, NOT active

GitHub's `schedule` event is best effort. Between 10 and 29 October 2026 the
`'12 * * * *'` cron ran in 95 of 443 hourly slots (21.4%), with a median gap of
4.8 h. This folder contains an external trigger that asks GitHub to run the
existing workflow every hour. **Nothing here is deployed.** Activation needs the
project owner's approval, a new token and a Cloudflare account.

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
  `sms-lock:<key>` label. See `tests/test_r3_trigger.py` and `tests/test_lock_recovery.py`.
* A failed dispatch is retried once (5xx or network error only). A duplicated
  dispatch is harmless for the same reason.

## Recommendation: Cloudflare Workers Cron

cron-job.org is simpler to set up (a web form), but Cloudflare is the better fit here,
because of what the token can do. A fine-grained token with **Actions: write**
can start workflows, and it can also **disable workflows, cancel runs and delete run logs**.
A leaked token could therefore silently stop the warning system. (Healthchecks HB-1
would alert after about 10 hours without a run.)

| | Cloudflare Workers Cron (recommended) | cron-job.org |
|---|---|---|
| Cost | Free plan: 5 Cron Triggers per account, 100,000 requests/day, 10 ms CPU per cron run (this Worker waits on one HTTP call; waiting is not CPU time) | Free |
| Token custody | Encrypted Worker secret, cannot be read back after saving | Typed into the job's header settings; storage of headers not documented in its FAQ |
| Behaviour | Tested code in this folder: fixed inputs, slot timestamp (`scheduled_for`, needed for `dispatch_delay_seconds`), one bounded retry, token never logged | Plain request; no slot timestamp; 30 s timeout; job auto-deactivates after 25 consecutive failures |
| Failure visibility | Cron Events list failed invocations (the Worker throws on any failed dispatch) | Execution history; optional failure e-mails |
| Setup | Cloudflare account; `npx wrangler` (Node.js is installed) | Web form |
| Public endpoint | None (`workers_dev = false`, `preview_urls = false`, no fetch handler) | None on our side |

In both cases GitHub Actions remains the only SMS sender, and the GitHub cron stays as backup.

## Activation: exact minimum steps (Cloudflare)

**0. Check the lock permissions first.** Open the job summary of the first run on the
current commit. It must show `lock_label_permission = ok` and
`run_status_permission = ok`. If either one isn't `ok`, stop and report it. Warnings remain
safe (the issue ledger still applies), but the lock is not active.

**1. Create the token** at <https://github.com/settings/personal-access-tokens/new>:
* Token name: `matatiele-external-trigger`. Expiration: 90 days (note the date).
* Resource owner: `mdvar2`. Repository access: **Only select repositories** →
  `matatiele-storm-early-warning-system`.
* Repository permissions: **Actions → Read and write**. Leave everything else as
  *No access* (Metadata: read is added automatically).
* Generate it and keep the page open. Don't paste the token anywhere else.

**2. Deploy the Worker** (in this folder):
```bash
cd ops/external-trigger
node --test                     # 9 offline tests, all must pass
npx wrangler login              # opens the browser; free Cloudflare account
npx wrangler deploy             # creates the Worker and its ":05" cron trigger
npx wrangler secret put GITHUB_DISPATCH_TOKEN   # paste the token at the prompt
```
If a :05 run happens between `deploy` and `secret put`, it reports `not_configured`
and does nothing.

**3. Verify** after the next :05 UTC:
* GitHub → Actions: a new `workflow_dispatch` run of *Scheduled Matatiele Storm Check*.
* That run's summary shows `trigger_source = external_scheduler` and a `scheduled_slot_utc`.
* Cloudflare → Workers → `matatiele-storm-trigger` → Cron Events: `outcome=dispatched`.

**Disable at any time:** set `crons = []` in `wrangler.toml` and run `npx wrangler deploy`
(or delete the Worker in the dashboard), then revoke the token on GitHub. The GitHub
cron keeps running.

**Renew before expiry:** create a new token as in step 1, then run `npx wrangler secret put GITHUB_DISPATCH_TOKEN`.
An expired token shows `rejected_http_401` in Cron Events, and the GitHub cron backup continues.

## Alternative: cron-job.org

Create one job:

* URL: `https://api.github.com/repos/mdvar2/matatiele-storm-early-warning-system/actions/workflows/scheduled-storm-sms.yml/dispatches`
* Schedule: every hour at minute 5; time zone UTC. Method `POST`.
* Headers: `Authorization: Bearer <token>`, `Accept: application/vnd.github+json`,
  `X-GitHub-Api-Version: 2022-11-28`, `Content-Type: application/json`.
* Body: `{"ref":"main","inputs":{"send_test_sms":"false","trigger_source":"external_scheduler"}}`
  (`scheduled_slot_utc` will show `not_available`).
* Success = HTTP 204. Enable failure notifications.

## Measuring the effect

Coverage is not claimed as improved until it is measured:

```bash
python 21_measure_execution_coverage.py --fetch --since <activation time>
```

Compare `slot_coverage` and `freshness_75min` across all events with the 21.4% and
25.6% baseline over at least 14 days. The runs API does not show dispatch inputs, so
use `trigger_source` from run records or HB-1 payloads to separate external from manual runs.
