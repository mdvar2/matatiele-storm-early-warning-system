# System Logs panel: evidence (31 October 2026)

**Location:** Alerts, then **System log**. Events are stored in SQLite (`system_log.py`; `outputs/system_log.sqlite`, which Git ignores). The panel shows timestamp, severity, delivery method and status, following the reference panel.

## What is logged (only events the system observes)

| Event | Severity | Delivery method |
|---|---|---|
| Model risk level changes (real score and target hour) | LOW / ELEVATED / MODERATE / HIGH | Dashboard |
| Warning records: genuine, or a labelled development test | HIGH | Dashboard + public warning record, or Dashboard (development test) |
| SMS record status (simulated, queued, accepted, delivered, failed, unknown) | INFO / WARNING | SMS, or SMS (simulation outbox) |
| Forecast data unreachable or out of date / current again | WARNING / NORMAL | Dashboard |
| Administrator demonstrations: connectivity failure (this session only), on-screen warning simulation | WARNING / INFO | Administrator demonstration |

**Safeguards:**
- Each event appears once (keys and stored state), however often the page reruns.
- No phone numbers or subscriber identifiers are stored; SMS keys are hashed.
- The on-screen warning simulation **never** changes the logged risk level. This was found during the browser demonstration and fixed, and a test now covers it.
- The demonstration outage affects only the administrator's session and is labelled as a demonstration.
- On the hosted app the SQLite file is reset when the app restarts. The public warning record (and `[RUN-LOG]` once merged) is permanent.

## Demonstration (`screenshots/`)

This was run on a local copy in SMS simulation mode, with:
- a fictional test subscriber and a labelled development test warning;
- an administrator switching the connectivity-failure demonstration and the warning simulation on and off.

The log recorded seven events: the development test warning (HIGH), its simulated SMS (INFO), the genuine risk level (LOW, model risk score 2%), and the four demonstration on/off events ([browser_checks.json](browser_checks.json)). There was no overflow at 1440 px (light and dark) or 390 px. Nothing was sent.

## Tests

- **Full suite:** 377 passed with network access blocked (0 outbound attempts).
- **Other checks:** worker equivalence 21/21; model, features and threshold identical to `main`.
- **New tests:**
  - the SQLite store records each keyed event once and lists newest first;
  - SMS log rows carry no numbers;
  - the risk level and a data outage are logged from real observations, and no warning is invented;
  - administrator demonstrations are logged and labelled;
  - the simulation does not alter the logged risk level.
