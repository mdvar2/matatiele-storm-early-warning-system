# Research Implementation Summary: Integrated Resident-Facing Application

*Date:* 30 October 2026 · *Branch:* `research-dashboard-ui-redesign` (local; not pushed or deployed)

## Purpose

The system previously had two limits. Its SMS warnings reached only a fixed, owner-configured recipient list. Its dashboard was mainly a research display. This work turns it into an application that residents of Matatiele can use themselves. Residents can:

- read the live next-hour storm estimate and safety advice;
- register their own mobile number for SMS warnings;
- prove they own the number, and check or cancel the subscription;
- see the public record of warnings issued.

Administrators can monitor subscriptions and delivery.

## What was built

| Area | Implementation |
|---|---|
| Visual design | Sky-themed redesign (df56cd8) with WCAG-AA hero contrast (b5b2317). Light and dark themes, mobile navigation, low-data text view. |
| Registration | South African mobile validation; Matatiele as the only area; explicit, versioned consent; 6-digit one-time codes. Codes are hashed, expire after 10 minutes and allow 5 attempts. Rate limits apply per number and globally. |
| Privacy | Numbers are encrypted at rest (Fernet) and looked up by a keyed hash (HMAC-SHA256). Only masked numbers are displayed. The encrypted number is erased on unsubscribe. No form reveals whether a number is registered. |
| Persistence | One encrypted JSON document in a private GitHub repository, with compare-and-swap updates. Streamlit Cloud has no persistent disk. Local development uses a locked file. |
| Warning integration | After the existing worker reserves a warning hour in the public ledger, it delivers the same warning to active, verified subscribers. There is one delivery per subscriber per warning hour. The feature is off by default (`SUBSCRIBER_ALERTS_ENABLED`) and can never fail or alter the existing warning. |
| Delivery tracking | Each delivery is recorded as submitted, delivered, failed or uncertain. Uncertain outcomes are never retried automatically, to avoid duplicates. Definitive failures can be retried by an administrator (at most 3 attempts in total). A STOP opt-out (Twilio 21610) unsubscribes the resident. |
| Monitoring | Subscriber counts are added to the run record, job summary and heartbeat payload. These are counts only, never numbers. |
| Administration | Password-protected page: subscription statistics, warning activity, masked deliveries, status refresh and retry, system health, recent workflow runs. |
| Public history | Genuine warnings come from the public ledger. Connectivity tests are excluded and recipients are never shown. |

**Unchanged:** the Random Forest model, the 35% threshold, the forecast pipeline, the ledger and duplicate-lock logic, the warning text, and the existing recipient path. With the feature flag off, the worker produced identical results in all 21 equivalence scenarios.

## Evidence

[integrated_application_evidence_2026-10-30/](integrated_application_evidence_2026-10-30/README.md) contains:

- automated tests: 307 passed twice, 0 network attempts, 34 subscription and end-to-end tests;
- a real-browser demonstration of the whole workflow in light, dark and mobile layouts;
- contrast measurements from the screenshots;
- four defects found and fixed during evaluation.

## Limitations and external dependencies (honest status)

1. **Not yet live.** Public registration needs the owner to:
   - create the private store repository and token;
   - generate the keys;
   - configure Streamlit and GitHub secrets;
   - approve deployment.

   See `docs/DEPLOYMENT_AND_CONFIGURATION.md`.
2. **Twilio trial account.** It can message only verified numbers (error 21608). Public use requires an upgraded, paid account and a review of South African sender rules.
3. **STOP replies** depend on the sender's ability to receive replies. The web unsubscribe is the guaranteed route.
4. **Delivery status** is refreshed on administrator request, by polling. There is no webhook, because Streamlit Cloud cannot receive callbacks.
5. **POPIA.** The responsible party, the privacy notice and the retention period must be confirmed before public launch.
6. **No real delivery was tested.** Real SMS delivery to residents has not been exercised, by design: no SMS was sent without approval. The real-world test is the trial step in the deployment guide.
7. **The warning is a model estimate.** As before, it is a research model estimate, not an official SAWS warning, and it has not been independently validated as a calibrated probability.
