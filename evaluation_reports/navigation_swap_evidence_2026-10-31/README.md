# Navigation swap: evidence (31 October 2026)

Navigation placement only. The Risk Analysis and Forecast pages, icons, styling, themes, model, forecast retrieval, 35% threshold, warning logic and SMS are unchanged.

| | Before | After |
|---|---|---|
| Top bar | Home · Forecast · Map · Safety | Home · **Risk Analysis** · Map · Safety |
| ☰ side menu | Alerts · Risk Analysis · Historical Data · About | Alerts · **Forecast** · Historical Data · About |

**Why:** Risk Analysis shows the machine-learning storm-risk assessment at the centre of RO3, so it gets a top-bar place. Forecast remains as supporting weather information.

## Browser checks ([light](browser_checks_light.json), [dark](browser_checks_dark.json))

At 1440, 820 and 390 px in both themes:

| Step | What was confirmed |
|---|---|
| Home | Top bar and side menu in the new order; Home highlighted |
| Tap **Risk Analysis** (top bar) | The Risk Analysis page opens; Risk Analysis highlighted; no side-menu item highlighted |
| Open ☰, tap **Forecast** | The Forecast page opens; Forecast highlighted in the side menu; no top-bar item highlighted |
| Tap **Map** (top bar) | Map highlighted |
| Browser refresh | The dashboard opens on Home with Home highlighted, as before: the open page is kept per session, not in the link |

There was no horizontal overflow at any step.

## Tests

- **Full suite:** 366 passed, 0 failed, 0 skipped (281 subtests), run twice. The second run used a process-wide network guard, with 0 outbound attempts.
- **Updated navigation test:**
  - checks the exact order of both menus;
  - checks highlighting in both after each move;
  - checks that both pages are unchanged;
  - checks that a fresh session (refresh) opens on Home.
- **Other checks:** worker equivalence 21/21; model, feature list and threshold identical to `main`.
