# UI Refinement and Light/Dark Theme: Evidence (30 October 2026)

**Branch:** `research-dashboard-ui-redesign` (local; not pushed or deployed). This round changed presentation only. The model, the 35% threshold, forecast retrieval, warning logic, SMS configuration, warning records, acknowledgements, official authentication and storage are unchanged: `git diff` on those files is empty, and the worker equivalence check is 21/21.

## What changed

| Area | Change |
|---|---|
| Icons | No emoji anywhere in the interface. Streamlit controls use Material Symbols; HTML cards, tiles, diagrams, contact buttons and the risk card use one Lucide-style outline set (`icons.py`), drawn as CSS masks so each icon follows the text colour in both themes. |
| Theme | A **Dark theme** switch in the header (labelled, with on/off state). One design-token system (`dashboard_theme.theme_css`) applies the choice to every page, the officials' portal, Streamlit's widgets, the themed HTML tables and the charts. The choice is kept across pages (session), refreshes (`?theme=` in the link) and later visits (local storage in this browser). First visits follow the device setting. |
| Palette | Light: soft off-white background, white cards, navy text, blue accent. Dark: deep navy background, blue-grey cards, light text, blue accent. Restrained shadows. Streamlit's base theme is pinned to light in `.streamlit/config.toml`, so the tokens are the only theme source. |
| Tables | Canvas tables (which cannot follow a page theme) are replaced by themed, scrollable HTML tables: Historical Data, the officials' portal, the admin page and the SMS log. |
| Accessibility | Visible focus ring on links, buttons, inputs and switches. Text contrast of at least 4.5:1 in both themes, checked by a test. Severity is shown by icon shape and words as well as colour. Risk-scale labels meet 4.5:1. Reduced-motion preferences are respected. |
| Hierarchy | Home reads top to bottom: warning status → next-hour model estimate → forecast conditions → safety actions and the Safety link. Navigation is unchanged: Home, Forecast, Map and Safety, plus the ☰ menu with Alerts, Risk Analysis, Historical Data and About. |

## Tests

| Check | Result |
|---|---|
| Full suite, two consecutive runs | **342 passed, 274 subtests** ([run 1](full_regression_run1.txt), [run 2](full_regression_run2.txt)); 0 network attempts |
| New UI tests | <ul><li>the switch applies dark mode on all 8 pages, writes `?theme=`, survives a refresh, and switches back;</li><li>the portal uses the same theme;</li><li>the order in which the theme is chosen;</li><li>the stylesheet switches the dark layer explicitly;</li><li>contrast in both themes;</li><li>no emoji on any page or in the portal;</li><li>charts use theme colours;</li><li>no duplicated components (existing test, still passing).</li></ul> |
| Browser walkthrough ([script](browser_walkthrough.py)) | Light: 47/47 checks; dark: 43/43 ([light](ui_light.json), [dark](ui_dark.json)). Covers every page at 1440 / 820 / 390 px with no horizontal overflow; the real switch changes the theme, and the theme is kept after a page change and after a reload *without* `?theme`; the officials' portal after sign-in; a warning with tap-to-call buttons on a phone. No server errors. |

## Screenshots (`screenshots/<theme>_<width>_…`)

- `01_home`, `02_forecast`, `03_map`, `04_safety` (top bar), and `05_alerts`, `06_risk`, `07_history`, `08_about` (☰ menu), at 1440, 820 and 390 px;
- `09_switch_after_refresh`: the theme kept after a reload;
- `10_portal_active`, `11_portal_history`: the officials' portal;
- `12_warning_detail`: a labelled development-test warning on a phone.

## Remaining limitations

1. **Brief flash on a first reload:** a visitor whose remembered theme is dark, opening a link without `?theme`, may see one light render before the browser reports the choice.
2. **Streamlit's own settings menu (⋮):** its separate theme option still exists. Choosing it there changes only Streamlit's widgets and can conflict with the switch. The switch is the supported control.
3. **Map basemaps:** the satellite and street tiles are the same in both themes. The "Low data" basemap is plain.
4. **Two icon sets:** Streamlit controls use Material Symbols, while HTML content uses the Lucide-style set. Both are outline styles of similar weight, but they are not identical.
5. **Automated scope:** the walkthrough is automated (headless Chrome). It has not been tested with a screen reader or on physical tablets.
