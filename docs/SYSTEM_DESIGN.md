# System Design: Stakeholders, Use Cases, Architecture and Activities

This document is for research readers (supervisor, examiners) and maintainers. It describes the external actors, the interactive accounts that exist, and how the system works internally.

## 1. Stakeholders and roles

| Stakeholder | Role in the system | Interactive account? |
|---|---|---|
| **Residents of Matatiele** | View the next-hour storm estimate, the forecast, the map and safety advice. View current and past warnings and open their details. Acknowledge that a warning was viewed. Call emergency numbers. Register for, manage and cancel SMS warnings. | **No account.** Pages are public. SMS registration is verified by a one-time code. Acknowledgements are anonymous: one per device. |
| **Disaster-management officials** | In the decision-support portal (`?portal=officials`): <ul><li>review active warnings, their timestamps and aggregate acknowledgements;</li><li>view the forecast geography;</li><li>record a review or response status with notes;</li><li>review the history of warnings and actions.</li></ul> | **Yes.** Individual named accounts (`OFFICIAL_ACCOUNTS`, PBKDF2-hashed), so every review is attributed and timestamped. |
| **Emergency response services** (SAPS 10111, ambulance and fire 10177, 112) | Receive phone calls that residents start from the tap-to-call buttons. The system never contacts or dispatches them. | **No.** They have no workflow inside the system. |
| **Developers and administrators** | Monitor system health, subscriptions and SMS delivery (masked numbers); retry definitive delivery failures; run the on-screen warning simulation; maintain configuration and secrets. | **Yes.** Administrator password (`ADMIN_PASSWORD`). This is separate from official accounts. |
| **Telecommunications providers** (Twilio SMS gateway, mobile networks) | Deliver verification codes and warning SMS, and report delivery status and STOP opt-outs. | **No.** System-to-system integration. |
| **Weather data provider** (ECMWF via Open-Meteo) | Supplies the hourly forecast used as model input and for the map. | **No.** System-to-system integration. |

Accounts exist only for stakeholders whose workflows are implemented: officials and administrators.

## 2. Use case diagram

![Use case diagram](diagrams/use_case.png)

Source: [diagrams/use_case.puml](diagrams/use_case.puml) (PlantUML).

What the diagram includes, and what it deliberately leaves out:
- It shows **external actors and their goals only**.
- "View warning details" is **one use case** shared by residents and officials (the officials' review *includes* it), so there is no duplicated alert-review use case.
- Forecast retrieval, preprocessing, model inference, risk classification, duplicate prevention and SMS submission are **not** user use cases. They appear as the single time-triggered use case *Issue automatic storm warning*, detailed in §3 and §4.
- MQTT, LoRa and edge processing are future research and are not part of this system.

## 3. Architecture

```mermaid
flowchart LR
  subgraph External
    OM[ECMWF forecast<br/>via Open-Meteo]
    TW[Twilio SMS gateway<br/>and mobile networks]
    GH[(GitHub: public warning ledger<br/>issues and run records)]
    PS[(Private GitHub repository:<br/>subscribers.json, operations.json)]
    ES[Emergency services<br/>10111 / 10177 / 112]
  end
  subgraph Worker["Hourly worker (GitHub Actions)"]
    W1[Fetch forecast] --> W2[Preprocess:<br/>29 live features, CAPE checks] --> W3[Random Forest inference] --> W4{Probability<br/>at least 35%?}
    W4 -- yes --> W5[Reserve hour in ledger<br/>duplicate prevention] --> W6[Send SMS: configured recipients<br/>and verified subscribers]
    W4 -- no --> W7[Record run: no warning]
  end
  subgraph App["Streamlit application"]
    R[Resident pages:<br/>Home, Alerts, Forecast, Map, Safety]
    O[Officials' decision-support portal]
    A[Administration]
  end
  OM --> W1
  OM --> App
  W5 --> GH
  W6 --> TW
  W6 --> PS
  GH --> R
  GH --> O
  R <--> PS
  O <--> PS
  A <--> PS
  R --> TW
  R -. tap-to-call .-> ES
  TW --> Residents((Residents' phones))
```

| Store | Contents | Who writes |
|---|---|---|
| Public warning ledger (GitHub issues) | One issue per warning hour; no personal data | Worker |
| `subscribers.json` (private) | Encrypted numbers, keyed hashes, consent, delivery outcomes, warning copies with probability | Dashboard (residents) and worker |
| `operations.json` (private) | Acknowledgements (keyed device hashes per warning); officials' review statuses and notes (name and time) | Dashboard (residents and officials) |

## 4. Activity diagrams

### 4.1 Hourly storm assessment and warning (automatic)

```mermaid
flowchart TD
  S([Hourly trigger]) --> F[Retrieve ECMWF forecast for Matatiele]
  F --> V{Forecast complete<br/>and current?}
  V -- no --> X[Record failure; no warning;<br/>heartbeat alerts maintainers] --> E([End])
  V -- yes --> P[Build 29 live-compatible features;<br/>CAPE normalisation checks]
  P --> M[Random Forest: next-hour storm probability]
  M --> C{Probability at least 35%?}
  C -- no --> N[Record run: below threshold] --> E
  C -- yes --> L{Hour already reserved<br/>in public ledger?}
  L -- yes --> D[Stop: duplicate prevented] --> E
  L -- no --> R[Reserve hour: ledger issue]
  R --> T[Submit SMS to configured recipients]
  T --> Q{Subscriber warnings enabled?}
  Q -- no --> E
  Q -- yes --> U[Send once to each active,<br/>verified subscriber]
  U --> K[Record delivery outcomes<br/>counts only in run record] --> E
```

### 4.2 Resident interaction with a warning

```mermaid
flowchart TD
  A([Resident opens app]) --> H[Home: warning banner,<br/>model estimate, weather, contacts]
  H --> W{Warning in effect?}
  W -- yes --> O[Open warning]
  W -- no --> L[Alerts: current and past warnings] --> O
  O --> D[Details: severity, forecast period,<br/>location, estimate, actions]
  D --> K{Acknowledge?}
  K -- yes --> AK{Already acknowledged<br/>on this device?}
  AK -- no --> REC[Record one acknowledgement:<br/>keyed device hash and time]
  AK -- yes --> SHOW[Show the earlier acknowledgement time]
  D --> CALL[Tap to call 10111, 10177 or 112]
  D --> SMS[Register for SMS:<br/>number, consent, code] --> ACT[Active subscriber]
```

### 4.3 Official review of a warning

```mermaid
flowchart TD
  A([Official opens ?portal=officials]) --> S{Signed in?}
  S -- no --> P[Username and password] --> T{Valid and not locked?}
  T -- no --> P
  T -- yes --> V
  S -- yes --> V[Active warnings: timestamps,<br/>estimate, acknowledgements, status]
  V --> G[Geographic risk:<br/>ECMWF rainfall grid around Matatiele]
  V --> R[Warning details]
  R --> U[Set review status and note]
  U --> Rec[Record with official's name and time]
  Rec --> H[History and actions; CSV export]
  H --> Out([Decisions are acted on through<br/>the official's own channels:<br/>no dispatch from this system])
```

### 4.4 Workflow shown on the About page

The About page shows the main **resident-facing** warning workflow as one line. The officials' portal is a separate interface (see 4.3) and is not a stage in this workflow. SMS is optional, and its badge shows the real state: *not enabled*, *development outbox* or *configured*. Expandable sections explain how the model and system work (nine steps, verified against the project scripts) and the low-connectivity design.

```mermaid
flowchart LR
  F[External forecast<br/>ECMWF via Open-Meteo] --> M[Random Forest<br/>model-estimated storm risk] --> D{35% warning decision}
  D -- at or above 35% --> W[Warning information<br/>Alerts page and public record]
  W -. optional, only when enabled and configured .-> S[SMS communication]
```
