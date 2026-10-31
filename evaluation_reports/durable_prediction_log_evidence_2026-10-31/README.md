# Durable prediction log: evidence (31 October 2026)

**Finding:**
- **Production:** run records are not published. `RUN_RECORD_PUBLISH` was `'false'`, so each hourly worker run's record (including the model score) went only to the GitHub Actions job summary, and no `[RUN-LOG]` issue exists.
- **Dashboard:** the Home log could only use the dashboard's own `prediction_history.csv`, which is lost whenever the hosted app restarts.

## Changes (development branch)

| Change | Effect |
|---|---|
| `.github/workflows/scheduled-storm-sms.yml`: `RUN_RECORD_PUBLISH: 'true'` | Each hourly run posts its sanitised record (no phone numbers, message content or provider identifiers) to the public `[RUN-LOG] YYYY-MM` issue. **Takes effect only after merging into `main`.** |
| `prediction_log.py` | Reads the recent `[RUN-LOG]` comments from the public GitHub API. It keeps only records with a validated score (0–1), one per target hour, and adds the dashboard's own runs for hours the worker did not record. |
| Home **Recent predictions** and **Historical Data** | Use these records, with a **Recorded by** column: Hourly worker or Dashboard. They say when the run log is unreachable. A failed request is cached for 10 minutes, so GitHub is not called on every rerun. |

The model, its features, the 35% threshold, warning logic and SMS are unchanged:
- the model, features and threshold are identical to `main`;
- worker equivalence is 21/21.

## Checks

- **Live read-only call to the public API:** 0 records, as expected while publishing is off on `main`.
- **Tests:** 373 passed, run twice, the second with network access blocked (0 outbound attempts). One unguarded run had a single failure while a browser capture was loading the machine; it passed on re-run.
- **New tests:**
  - record parsing and filtering, so a connectivity test or an invalid score is never shown;
  - only this month's `[RUN-LOG]` issue and recent comments are fetched;
  - worker records take precedence over dashboard runs;
  - the fallback when the log is unreachable;
  - a round trip: what `19_publish_run_record.py` posts is what the reader parses.
- **Browser:** 1440, 820 and 390 px in both themes, with no horizontal overflow. The rows currently show "Dashboard", because no worker records exist yet.
