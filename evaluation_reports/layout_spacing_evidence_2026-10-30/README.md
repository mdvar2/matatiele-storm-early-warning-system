# Map and About Layout: Before and After (30 October 2026)

Presentation-only changes. The model, the 35% threshold, forecast retrieval, warning logic, SMS configuration, authentication and warning or acknowledgement storage are unchanged. The protected files show no diff, and the worker equivalence check is 21/21.

## Measurements

Headless Chrome, measured identically before and after ([script](browser_measurements.py); [before](before_light.json), [after](after_light.json); the dark theme gives the same numbers):

| Viewport | Map top (px) | Map height (px) | Map visible without scrolling (px) | Horizontal overflow |
|---|---|---|---|---|
| Desktop 1440 × 900 | 566 → **459** | 360 → **560** | 334 → **441** | none |
| Tablet 820 × 900 | 796 → **504** | 360 → **560** | 104 → **396** | none |
| Phone 390 × 800 | 860 → **687** | 360 → **560** | 0 → **113** | none |

## What changed

- **Empty band on every page (found while measuring):** when the ☰ menu was closed, a CSS minimum width still reserved 275 px of empty space on the left of every page on desktop and tablet. The width now applies only while the menu is open. This was the largest single gain on tablets.
- **Top spacing:** the top padding is 3.1 rem instead of 4.5 rem, and section headings are tighter. Text sizes and touch targets are unchanged.
- **Map page:**
  - a light page title replaces the heavy heading bar;
  - the basemap selector and forecast-hour slider share one row;
  - the overlay switch sits under the map, beside the legend it controls;
  - the map is 560 px instead of 360 px;
  - the legend and the "drag, zoom, tap" hint form one compact strip;
  - on phones the status chips scroll in one row instead of stacking.

  The map data, forecast values and overlays are unchanged.
- **About page diagram:**
  - It now reads: main pipeline (Forecast → Random Forest → Warning decision → Warning record), then three separate branches from the warning record (Residents: warning view → acknowledgement; Officials: portal → review and audit history; SMS delivery, optional).
  - The officials' portal is no longer shown after SMS.
  - Every lane has a text badge (*Active*, *Optional · not enabled / development outbox / configured*, *Future research · not implemented*), so the status is not shown by colour alone.
  - Steps are compact cards with the icon beside the text. On phones they form a two-column grid instead of a long single column.

## Tests

- **Full suite:** 343 passed, 274 subtests, run twice ([1](full_regression_run1.txt), [2](full_regression_run2.txt)). No network access.
- **New test, `test_workflow_diagram_structure`:**
  - the pipeline order;
  - each branch is a single lane starting from the warning record;
  - the officials are never after SMS;
  - the SMS badge reflects the configuration;
  - future research is labelled.

## Remaining limitations

- **Phones:** the map starts about 690 px down, because the header (title, clock, theme switch, two-row navigation, status chips) remains above it. Only the first 113 px of the map show without scrolling.
- **Fixed map height:** the map is 560 px on every device, because Streamlit's map component takes a fixed height rather than one that follows the viewport.
- **Hidden status chips:** on phones the status chips scroll sideways, so the last chip is partly hidden until swiped.
