# Final RO3-aligned UI, image and live-state refinement: evidence (1 November 2026)

This is presentation only; no new system functionality was added. The following are unchanged:
- the model and its 29 inputs; the model files are identical to `main` ([model_unchanged.json](model_unchanged.json));
- the 35% threshold and warning logic; worker equivalence is 21/21 ([equivalence_r3.txt](equivalence_r3.txt));
- the outlook, offline page, relays, SMS simulation and history;
- the evidence: `25_build_model_evidence.py --check` passes.

## Changes

| Area | Change |
|---|---|
| Header | The supplied Matatiele storm artwork (`static/matatiele_storm_banner.jpg`, 124 KB; 32 KB phone version) replaces the drawn landscape. A blue overlay is used in light mode and a dark overlay in dark mode. The header is 120–150 px tall on desktop and 130 px on phones. Hovering shows "Illustrative artwork of Matatiele, not current weather", and no caption implies live weather. |
| Sidebar card | Text only, "Protecting Matatiele through earlier warnings", so the image is not repeated |
| Live state | The **System online** pulse appears only when the latest forecast and model result are current. When data is stale, the header shows "Saved data · last update …" with no pulse. The header says **Next refresh in ~N min**, updated by the existing one-minute rerun. An **Updated** label and a brief green glow appear when a newer genuine result arrives. All animation is off under `prefers-reduced-motion`. |
| Storm-risk card | A score, the category, a "35% warning threshold" label and one line with the target period and update time. The note reads "Model risk score — not a calibrated probability; not a guarantee." The gauge is 190 px on phones. |
| Warning decision | Same states. On phones the subtitle and footer are hidden, leaving one explanation line. |
| Outlook | "Model outlook — unvalidated beyond one hour"; the chart is shorter (170 px) |
| 6-hour chart | The legend is grouped as **ECMWF forecast** (rain bars, wind line) versus **Random Forest outlook** (a dashed red line with diamond markers), so the sources cannot be confused. The chart is 200 px tall. |
| Actions | View warnings · Safety advice · Emergency contacts · SMS service · **Offline access**. They form a two-column grid on phones. The low-data line names both low-connectivity options. |
| Cards | Desktop padding reduced; phone padding reduced by about 20–30% |
| Phone navigation | The top bar fits on one line, and the status strip is hidden (the header shows the status) |
| Safety | "Be prepared" uses compact tiles: five columns on desktop, three on tablet, two on phones. "Act now" keeps the full advice with less padding. The contacts are unchanged. |
| Historical Data | The table is collapsible; the chart is unchanged |
| About (RO3) | Rows are grouped as **Implemented** (smart, early warning, resilient, low connectivity), **Implemented as simulation** (SMS and community relays, not field-tested), **Exploratory, unvalidated** (2–12 hour outlook) and **Future / deployment-dependent** (public SMS, sensors, LoRa, sirens, Cell Broadcast, field validation) |

## Phone first screen (390 × 800 and 360 × 800; [dark](mobile_checks_dark.json), [light](mobile_checks_light.json))

| Width | Header | Risk score bottom | Warning decision bottom | Visible without scrolling |
|---|---|---|---|---|
| 390 | 130 px | inside the screen | 720 px | risk score **and** warning decision |
| 360 | 130 px | inside the screen | 739 px | risk score **and** warning decision |

Before this change, the decision badge ended at 854 px on a 390 × 800 screen, below the first screen.

## Other checks

- **Pulse:** active when data is current, and computed animation `none` under reduced motion (both widths and themes).
- **Offline page:** with the network cut, it reads "No connection: showing the last saved information. Saved … SAST" (390 and 360 px).
- **Overflow:** none on any page at 1440, 820, 390 or 360 px in either theme ([dark](all_pages_checks_dark.json), [light](all_pages_checks_light.json)).
- **Desktop pages:** Dashboard, Risk Analysis, Safety and Alerts were reached through the sidebar and have the correct headings ([checks](desktop_checks_dark.json)).
- **Tests:** 391 passed, with a network guard (0 outbound attempts).

## Screenshots

- `screenshots/before/`: commit `2d41593`. These are desktop Dashboard, Risk Analysis, Safety and Alerts (dark and light), and the phone Dashboard and Safety (dark).
- `screenshots/after/`:
  - the same desktop pages;
  - phone first screens and the open navigation (dark and light, 390 and 360 px);
  - the full phone Dashboard and Safety pages;
  - the offline page with the network cut.

**Capture note:** the first desktop "after" run navigated through the top bar, which is hidden while the side menu is open, so its non-Home desktop images were discarded. The desktop pages were recaptured through the sidebar for both the old commit (a temporary checkout) and the new code.

## Remaining limitations

- The base CSS is at its 40 KB budget. The header and sidebar styles add about 6 KB, and the header image adds 124 KB on desktop (32 KB on phones). It is cached by the browser and never loaded by the low-data view.
- Streamlit's development "Deploy" link appears in the local screenshots only.
- The 2–12 hour outlook remains unvalidated, and the community relays have not been field-tested.
