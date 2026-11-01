# Streamlit Cloud mobile navigation and runtime hotfix: evidence (01 Nov 2026)

## Root cause (reproduced on the live app, `live_before/`)

The live app (main `e434a63`) was probed at 390 × 800:

- **Error:** `AttributeError` at `16_dashboard.py` line 1227, on the call to `dashboard_theme.connection_watch_html`.
- **Styles:** the page's styles contained **none** of the new phone rules.
- **Navigation:**
  - the old top tab row was visible;
  - the new bottom bar was in normal flow (`position: static`, 200 px tall), not fixed to the bottom;
  - **More** was a 363 × 40 white button;
  - ☰ was hidden.
- **DOM:** it matched localhost (`data-testid` markers and `st-key-*` classes present). The DOM was not the cause.

**Cause:** the Streamlit Cloud process re-executed the updated `16_dashboard.py` but kept the previously imported `dashboard_theme` module in memory. Streamlit reruns the main script but reuses modules that are already imported. The new dashboard therefore ran against the old helper module:
- there was no `connection_watch_html` (the `AttributeError`);
- there was no phone CSS (duplicate navigation, bottom bar in flow, white More).

The missing ☰ was intentional in the previous version: a rule in the new dashboard hid it on phones.

## Fix

- **Fresh helper modules after an update.** `_drop_stale_project_modules()` runs at the top of `16_dashboard.py`. It fingerprints the app's `.py` files, and when the fingerprint differs from the one the loaded modules came from (or is unknown), it removes this app's modules from `sys.modules`, so the current files are imported. Only modules from the app folder are touched.
- **No crash and no traceback.** The connection watcher is wrapped: if it fails, the dashboard renders and shows a one-line note. `.streamlit/config.toml` sets `client.showErrorDetails = "none"`, so residents never see tracebacks or exception messages; those go to the server log.
- **☰ restored.** On phones the drawer holds only secondary pages and tools: Alerts, Forecast, Historical Data, About, Save for offline use, SMS service (plus refresh, and administrator sign-in with `?admin=1`). Home, Risk Analysis, Map and Safety are hidden there because they are bottom tabs. The drawer closes after a choice, on a tap outside it, and with Escape. It overlays the page without pushing it down.
- **One navigation.**
  - On phones (≤ 640 px) the old top tab row and its wrapper use `display: none` (0 height, not focusable).
  - On tablet and desktop the phone bar and phone-only drawer items use `display: none`.
  - Selectors use `data-testid` attributes and this app's own `st-key-*` keys, never generated class names.

## Local browser results (`local/checks.json`, screenshots in `local/`)

| Width | Result |
|---|---|
| 360, 390 (light and dark), 430 | 0 exceptions; exactly 1 visible bottom bar, `position: fixed`, flush with the bottom, unchanged after scrolling. Old top tabs hidden (0 height, 0 visible segmented controls). ☰ visible at (18, 16). Five items 54 px high and equal width (69 / 75 / 83 px), none truncated. More transparent like the others; the active tab is solid blue. No horizontal overflow. The last content stays clear of the bar. |
| 360, 390 | Active tab moves (Home → Risk). The More sheet (208 × 392 px) lists Alerts, Forecast, Historical Data, About, Save for offline use and SMS service, and closes after a choice. The ☰ drawer lists Alerts, Forecast, Historical Data, About, Save for offline use, SMS service and Refresh; it closes after a choice, on Escape and on an outside tap, and does not push the page. |
| 820, 1024 (tablet), 1366 (desktop) | No phone bar, no top tabs, sidebar open: unchanged. |
| Saved offline dashboard | Still embedded (19.7 KB, five tabs, genuine snapshot). |

**Breakpoint:** 640 px is kept. At 430 px the five tabs fit with room to spare (83 px each). At 820 px the sidebar layout is used.

## Tests

`test_run1.txt` and `test_run2.txt`: 414 passed, 300 subtests. Run 2 used the network guard (0 outbound attempts).

New regressions:
- a stale helper module from a previous version is replaced, and the page renders without error;
- a failing connection watcher leaves the page working;
- `showErrorDetails = "none"`;
- exactly one bottom bar and one Home control;
- ☰ is not hidden;
- the drawer holds the secondary tools;
- the drawer closing behaviour is present;
- no phone bar on desktop or tablet;
- no controlled SMS test for residents.

## Integrity

The model, 29 inputs, 35% threshold, warning, outlook and SMS logic, worker and evaluation evidence are unchanged.

## Live verification on Streamlit Community Cloud

**First deploy (`d29d066`, `live_first_deploy/`).**
- Working: no error; one fixed bar; ☰ visible; More correct.
- Found: Cloud's Streamlit marks the open sidebar with `data-collapsed="false"`, not `aria-expanded`. As a result:
  - the drawer did not close itself;
  - the tablet rule hiding the top bar could not match;
  - the drawer's download button was white with light text.

  All three were fixed in `87f3b14`.

**Final deploy (`52f1a6d`, `live_after/`).**

| Live check | 360 light | 390 light | 390 dark | 430 light | 820 tablet | 1366 desktop |
|---|---|---|---|---|---|---|
| Exception / traceback | none | none | none | none | none | none |
| Visible bottom bars | 1, fixed | 1, fixed | 1, fixed | 1, fixed | 0 | 0 |
| Old top tab row | hidden, 0 px | hidden, 0 px | hidden, 0 px | hidden, 0 px | hidden | hidden |
| ☰ visible | yes | yes | yes | yes | sidebar open | sidebar open |
| Tabs: truncated / height / width | no / 54 / 69 | no / 54 / 75 | no / 54 / 75 | no / 54 / 83 | – | – |
| Bar unchanged after scrolling | yes | yes | yes | yes | – | – |
| Horizontal overflow | no | no | no | no | no | no |
| Risk card / decision top (px) | 280 / 609 | 280 / 591 | 280 / 591 | 280 / 591 | 398 / 462 | 326 / 390 |
| Active tab, More sheet (closes after a choice) | yes | yes | – | yes | – | – |
| ☰ drawer: opens; closes after a choice, Escape, outside tap | yes | yes | – | yes | – | – |

**Platform overlay (not part of the app).** On the live site, Streamlit Community Cloud draws its own floating "hosted with Streamlit" badge and the developer's avatar in the bottom-right corner of the page that wraps the app. On phones they overlap the right end of the bottom bar (More and part of Safety): see `live_after/live_390_dark_first_screen.png`. They come from the hosting page, not the dashboard, and do not appear locally or on other hosting. Hiding or moving the platform badge was not done without the project owner's decision.
