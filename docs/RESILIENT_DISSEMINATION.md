# Resilient dissemination: reaching residents when networks fail

**The constraint.** No technology delivers a message to a phone that has no signal: not SMS, not the dashboard, not an app. During severe storms, towers can lose power or become congested. This system is therefore designed to:
1. **warn early**, while networks still work;
2. **leave residents with information that works offline**;
3. **reach people through others** when their own phone cannot.

## 1. Early storm alerts from a 12-hour outlook

| Part | What it does |
|---|---|
| `outlook.py` | Applies the unchanged Random Forest to each of the next 12 ECMWF forecast hours. It builds **exactly** the live script's 29 inputs (same conversions, CAPE normalisation and model location). `tests/test_outlook.py` checks this for every hour, with zero difference in inputs and identical scores. |
| `27_outlook_alert.py` (workflow step after the worker) | If any hour **2 to 12 hours ahead** reaches 35%, an early alert is due for that 6-hour SAST block (night, morning, afternoon or evening). It creates a public `[OUTLOOK] OUTLOOK-V1-<date>-<block>` record once. If subscriber SMS is on, it sends: "MATATIELE EARLY STORM ALERT: model outlook shows raised storm risk from about HH:MM SAST today (score NN%). Not certain. Prepare now…". There is one message per alert and subscriber. The step never fails the job and never changes the next-hour warning. |
| Home → **Storm-risk outlook** | A bar chart of the scores 2 to 12 hours ahead with the 35% line, and an EARLY ALERT badge when one is due |
| Alerts → **Early alerts** | Lists the public `[OUTLOOK]` records |
| System log | Records each early alert |

**Switches (repository variables):**
- `OUTLOOK_ALERTS_ENABLED=true`: create early-alert records.
- `SUBSCRIBER_ALERTS_ENABLED=true`: also send SMS.

Both are off by default.

**Scientific limits:**
- The model was evaluated **one hour ahead only**. Outlook scores are unvalidated, and forecast skill falls with lead time.
- Every display and message says "not certain".
- The validated next-hour warning (35%, the public ledger) is unchanged and separate.

## 2. Offline page

| Part | What it does |
|---|---|
| `static/offline.html` (served at `/app/static/offline.html`; link on Home) | A small self-contained page showing the last risk score and level, the warning decision, warnings in effect, any early alert, safety advice and tap-to-call emergency numbers |
| `static/sw.js` (service worker), `manifest.webmanifest`, `icon.svg` | After one visit with signal, the phone keeps the page and the last status. With no connection the page still opens, says it is offline, and shows when it was saved. It can be added to the home screen. |
| `offline_page.py` → `static/status.json` | Written by the dashboard from the **genuine** output and real data state. The administrator's simulation and connectivity demonstration never reach it. It contains no personal data and is ignored by Git. |

**Limit:** the offline page cannot receive new warnings without a connection. It keeps the last one and the advice.

## 3. Community relays

| Part | What it does |
|---|---|
| Registration (Alerts → SMS alerts) | An optional box: "I am a community relay (ward councillor, community leader or volunteer) and agree to pass storm warnings on to people nearby". This is stored as `role: relay`. |
| Messages | Relays receive the same warnings and early alerts with " COMMUNITY RELAY: please warn people near you (in person, loudhailer, bell)." added. Residents' messages are unchanged. |
| Warning details → **Announcement for community relays and radio** | A short script a relay can read out, or community radio can broadcast |

**Limit:** recruiting relays and radio stations is outside the software.

## Not implemented (outside parties or hardware)

- **Cell Broadcast:** only government (NDMC, SAWS) and mobile operators can issue it.
- **Offline sirens:** LoRa or solar sirens need hardware.
- **Public SMS:** needs a non-trial provider account, POPIA compliance and ethics clearance, and the project owner's approval.
