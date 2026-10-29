# RO3 operational verification: first externally triggered production run (#103)

**Date:** 29 October 2026 · **Run:** #103 (ID 40954774977, job 123731913384) · **Code:** `8c4ccf1` · **Trigger:** Cloudflare Worker `matatiele-storm-trigger`, cron `5 * * * *`

## Evidence classes

| Label | Meaning |
|---|---|
| **VERIFIED: API/log** | Read directly from the GitHub REST API or Cloudflare logs during this session |
| **VERIFIED: owner-observed** | Observed by the project owner in the GitHub job summary (signed in) or on the Healthchecks.io dashboard, and reported to the researcher. These views are not accessible to the anonymous API used here. |
| **INFERRED** | Follows from verified facts and the code |
| **UNVERIFIED** | Not yet demonstrated in production |

## 1. Dispatch chain

| Fact | Value | Class |
|---|---|---|
| Cloudflare invocation | cron `5 * * * *`, slot `2026-10-29T21:05:36Z`, outcome `ok`, log `outcome=dispatched`, no exceptions, no token in logs | VERIFIED: API/log (`wrangler tail`) |
| GitHub run created | 21:05:38 UTC, `workflow_dispatch`, `scheduled-storm-sms.yml`, `main` at `8c4ccf1` | VERIFIED: API/log |
| Run conclusion | `success`; job 21:05:42–21:06:33 UTC (about 51 s) | VERIFIED: API/log |
| Connectivity-test step | `skipped` (only runs when `send_test_sms` is true) | VERIFIED: API/log |
| Annotations | Platform notices only (Node.js 20 deprecation for `actions/checkout@v4` and `actions/setup-python@v5`; Ubuntu 26 migration notice). No worker, probe or heartbeat warnings. | VERIFIED: API/log |
| `trigger_source` | `external_scheduler` | VERIFIED: owner-observed |

## 2. Forecast, model and decision (run record in the job summary)

| Field | Value | Class |
|---|---|---|
| `outcome` / `worker_exit_code` | `completed` / `0` | VERIFIED: owner-observed (exit 0 also implied by the step conclusion, API) |
| Forecast retrieval | successful | VERIFIED: owner-observed |
| Model inference | successful | VERIFIED: owner-observed |
| Prediction validation | successful | VERIFIED: owner-observed |
| Storm probability / threshold | `0.0` / `0.35` | VERIFIED: owner-observed |
| Warning decision | `below_threshold` | VERIFIED: owner-observed |
| SMS submission | Not required (below threshold) | VERIFIED: owner-observed |
| Duplicate prevention | Not exercised (`not_applicable` when below threshold) | INFERRED from the decision and the code |
| Ledger and labels after the run | Unchanged: issues #1 and #2 only; no `sms-lock:` or `sms-probe:` labels | VERIFIED: API/log |

## 3. Monitoring

| Check | State | Class |
|---|---|---|
| HB-1 execution | Healthy, recent ping | VERIFIED: owner-observed |
| HB-2 valid forecast | Healthy, recent ping | VERIFIED: owner-observed |
| HB-3 failure | Healthy, recent ping | VERIFIED: owner-observed |
| HB-4 warning failure | Not pinged; it is fail-only and pinged only when an eligible warning fails | INFERRED from the design |
| Heartbeat steps | Both `success`, with no heartbeat warning annotations | VERIFIED: API/log |

## 4. What this run demonstrates and what it does not

**Demonstrated (one run):**
- The Cloudflare cron fires at minute 05 UTC and dispatches the production workflow with an accepted token. GitHub starts the run within seconds.
- The run executes the genuine forecast, Random Forest inference and validation on the deployed code. It records `trigger_source = external_scheduler`, reaches a correct below-threshold decision, and doesn't start the connectivity test.
- The R2 heartbeats reach Healthchecks.io, and the R3 monitoring steps complete without warnings.

**Not demonstrated. These remain UNVERIFIED and high-risk:**

| Gap | Why it matters | What would establish it |
|---|---|---|
| **Warning delivery** | No production run has had a probability of 0.35 or more since automatic SMS was enabled. The ledger reservation, the atomic label lock, Twilio submission, the status comment and the HB-4 path have run only in mocked tests and the original connectivity tests. | The first genuine eligible warning, with its run record (`reservation_lock = created`, `sms_submission = sent`), Twilio console delivery status, and the recipients' confirmation |
| **Delivery to residents** | Twilio acceptance is not handset delivery; trial-account and recipient limits apply | Delivery receipts and recipient acknowledgement |
| **Sustained scheduler reliability** | One successful invocation says nothing about hourly regularity, Cloudflare or GitHub outages, token expiry or API rate limits | `python 21_measure_execution_coverage.py --fetch --since 2026-10-29T21:00:00Z` over 14 days or more, compared with the 21.4% slot-coverage and 25.6% freshness baselines |
| **Offline and low-connectivity resilience** | The design depends on GitHub, Cloudflare, Open-Meteo, Twilio and mobile networks. Nothing has been tested under connectivity loss at the residents' end or during provider outages. | Field testing and documented fallback behaviour (outside this run's scope) |
| **Duplicate prevention in production** | Proven only in simulation and tests | First eligible warning hour with both the external :05 and GitHub :12 runs (expected: one SMS; the second run `already_reserved`) |

## 5. Follow-up from this run
- The Node.js 20 deprecation notice applies to `actions/checkout@v4` and `actions/setup-python@v5`. A local, unpushed change upgrades both to `@v7` (Node.js 24, same inputs). That change needs the owner's approval to deploy, and one observed run afterwards.
- The scheduler token expires after 90 days; renew it with `npx wrangler secret put GITHUB_DISPATCH_TOKEN`.
