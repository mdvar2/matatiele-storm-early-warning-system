# Offline page hotfix: evidence (01 Nov 2026)

## Root cause (reproduced)

- **Deployed app.** On Streamlit Community Cloud the app runs inside an iframe at `/~/+/`.
  - A top-level request for `/app/static/offline.html` returns the platform's own page, not the file. That page is blank, or shows the "app has gone to sleep" screen (`deployed_probe/deployed_plain.png`, `awake_plain.png`).
  - The dashboard link resolved to `/~/+/app/static/offline.html`, which returns HTTP 400 (`deployed_probe/deployed_prefixed.png`).
  - Inside the iframe, `app/static/status.json` is served normally (`awake_status.png`).
  - The page never reached the browser, so nothing it could do (including its use of localStorage) could make it render.
- **Locally,** the old page rendered blank until its script had run, and showed nothing at all if the script failed.

## Fix

- `static/offline.html` is a plain-HTML shell that is visible without JavaScript:
  - the title, and "No saved warning information yet";
  - the instruction to open the page while connected;
  - safety advice;
  - emergency numbers 10111, 10177 and 112;
  - a status and timestamp area.
- The page's script tolerates empty, corrupt, partial and old-schema data, and the whole script is wrapped in try/catch.
- **Save for offline use** (Dashboard) downloads a self-contained copy, about 11 KB, with the genuine latest status embedded. It needs no server, service worker or storage, so it works on Community Cloud.
- `static/sw.js` caches only the real page and valid status files, and marks saved copies so the page can say they are saved information.

## Browser scenarios (headless Chrome via CDP, local server)

| Scenario | Result | Evidence |
|---|---|---|
| A: first visit, nothing saved | "No saved warning information yet", advice and numbers visible | `browser/A_first_visit.png` |
| B: online after the dashboard ran | "Connected — latest information saved on this device", 3%, LOW RISK, NO WARNING TRIGGERED (matches the dashboard) | `browser/B_online_saved.png` |
| C: network disabled, reload | "No connection: showing the last saved information", same data | `browser/C_network_disabled.png` |
| D / D2: reload offline, close and reopen offline | Same as C | `browser/offline_checks.json` |
| E: corrupt storage, no server status | "No saved warning information yet" (not blank) | `browser/E_corrupt_storage.png` |
| E2: partial old record | Renders the score, "Warning service not reachable…" | `browser/offline_checks.json` |
| F: Save for offline use → file opened with network disabled, reopened | Served as `attachment; filename="matatiele-storm-info-….html"`, 10.8 KB. Shows "Offline — saved information", "Last saved: 01 Nov 2026 02:50 SAST", 3%, LOW RISK, NO WARNING TRIGGERED | `browser/F_saved_file_offline.png`, `browser/download_checks.json` |
| G: saved copy two days old | "Saved information may be out of date." | `browser/G_stale_copy.png` |

Headless Chrome does not write downloads to disk. For scenario F, the file the button requested (`/media/<hash>.html`) was fetched, saved, and opened from `file://` with networking disabled.

## Automated tests

`test_run1.txt` and `test_run2.txt` hold the full suite results: 397 passed, 287 subtests. Run 2 used a process-wide network guard and logged 0 outbound attempts.

## Limits

- The saved information cannot receive new warnings while fully offline; residents save again when they have signal.
- No model inference runs offline.
- The payload has no personal data, subscriber data or credentials.
- The hosted page (`/app/static/offline.html`) works on self-hosted or local deployments only.
