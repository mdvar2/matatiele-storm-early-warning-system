# Reference-image look: evidence (1 November 2026)

The dashboard follows the supplied reference design wherever the system has genuine data for it. Only the presentation changed: the model, its 29 inputs, the 35% threshold, warning logic and SMS are unchanged (worker equivalence 21/21; [model_unchanged.json](model_unchanged.json)).

| Reference element | Applied as |
|---|---|
| Dark sidebar with every section | Dashboard · Risk Analysis · Map · Safety · Alerts · Forecast · Historical Data · About. Locked open on desktop and tablet; behind ☰ on phones, where the top bar remains. The top bar hides only while the side menu is open, so navigation is always visible. |
| Sidebar picture card | "Protecting Matatiele through early warnings", with an **original drawn landscape** (no third-party image) |
| Landscape banner header | Brand · "Matatiele, Eastern Cape" · date and time, **System online / Saved data (out of date)** from the real data state, and the next refresh time |
| White cards with blue icons and bold titles | All four row-1 cards, with subtitles; the weather card now white |
| 6-hour forecast with rain, wind and storm-probability lines | ECMWF rain bars and wind line, plus the **genuine model-outlook score** for the same hours. The line is drawn only where a score exists and is labelled unvalidated beyond one hour. |
| Key weather variables · Recent predictions · SMS status | The existing genuine cards, now in one row of three |

**Not adopted, because it would need invented data or would duplicate content:**
- the illustrative numbers in the reference (62%, "SMS warning sent · Delivered (2)");
- a regional risk zone around Matatiele: the model scores one location, and the Map page holds the rainfall map;
- a public "Send Test SMS" button, which stays administrator-only;
- a photograph.

**Checks** ([light](browser_checks_light.json), [dark](browser_checks_dark.json)):
- no horizontal overflow at 1440, 820 or 390 px;
- sidebar open on desktop and tablet, top bar shown on phones;
- risk score visible without scrolling at every width (bottom at 564, 630 and 718 px).

**CSS:** the base stylesheet stays under its 40 KB budget. The banner and sidebar styles add about 4 KB, including the drawn landscape.

**Tests:** 390 passed with a network guard (0 outbound attempts), including new tests that:
- the banner status follows the real data state;
- the risk line appears only with genuine outlook scores;
- the top bar shows whenever the side menu is closed;
- the artwork is original.
