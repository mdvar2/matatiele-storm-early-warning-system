# How storm early warning systems look: design notes

A short review of interface patterns in real warning systems, and how this system applies them.

| Pattern | Seen in | Applied here |
|---|---|---|
| **Storm map with coloured risk areas** (blue → green → yellow → red) and a **timeline** to step through the coming hours | FASTA nowcasting app (NCAS / University of Leeds): satellite storm locations up to 6 h ahead, updated every 30 min | **Map** page: genuine ECMWF forecast rain as soft colour zones, plus a forecast-hour slider (next 35 h). A ring at Matatiele shows the storm-model level. |
| **Hourly list**: time, weather icon, temperature, wind, chance of rain | Storm Alert Wx-type weather apps | Homepage **Next hours** strip (genuine ECMWF hourly values) |
| **Colour-coded warning levels** (impact and likelihood) | SAWS impact-based warnings: yellow / orange / red, levels 1-10 | Green / amber / red status banner and risk card. The app links to SAWS, the only official source. |
| **Warning content**: event, severity, urgency, area, time, *instruction* | Common Alerting Protocol (CAP), WMO | Warning details: severity, forecast period, location, estimate, issue time, **Act now** actions |
| **Reach people where they are**: SMS, app, web, low-data | WMO *Early Warnings for All* (pillar 3: dissemination and communication) | SMS alerts, a mobile-first layout, the low-data text page, tap-to-call emergency numbers |
| **Short labels, icons, one primary action** | All of the above | Icon chips, collapsible technical detail, one menu button (☰) |

**What this system does not claim:** the map is a **forecast**, not radar or satellite nowcasting such as FASTA. Coloured areas appear only where ECMWF forecasts rain, and dry hours stay clear.

Sources:
- [NCAS: Real-time storm information for Africa (FASTA)](https://ncas.ac.uk/?p=4475)
- [University of Leeds: an early warning system for storms](https://fluids.leeds.ac.uk/an-early-warning-system-for-storms/)
- [eNCA: Understanding SA's weather warnings alert system](https://www.enca.com/news-top-stories/understanding-sas-weather-warnings-alert-system)
- [WMO: Common Alerting Protocol](https://wmo.int/node/25918)
- [WMO: Early Warnings for All](https://wmo.int/activities/early-warnings-all)
