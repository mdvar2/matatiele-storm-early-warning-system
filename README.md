# 🌩️ Matatiele Smart Resilient Storm Early Warning System

**Research project:** *Smart Resilient Storm Early Warning System for Low Connectivity Environments: A Case of Matatiele*

**Status:** Academic Beta prototype · **Location:** Matatiele, Eastern Cape, South Africa

**[Explore the live dashboard](https://matatiele-storm-early-warning-system-jykpxrtek3zejgqfk5xvr.streamlit.app)**

## Overview

A machine-learning research prototype designed to support earlier awareness of potential storms in Matatiele. It combines historical weather data, genuine forecasts, a Random Forest classifier, interactive weather visualisations and SMS integration. The current Beta is Internet-dependent; resilient offline deployment is a future research goal.

## Key Features

- **Next-hour storm prediction:** Random Forest model using 29 live-compatible features and a **35% warning threshold**.
- **Live weather inputs:** ECMWF forecasts retrieved through Open-Meteo.
- **Interactive dashboard:** Seven Streamlit pages covering forecasts, risk, maps, history and alerts.
- **Rainfall visualisation:** Satellite-based map with interpolated regional forecast rainfall; **not live radar**.
- **SMS integration:** Administrator-controlled Twilio test messages; real automatic storm-warning SMS remains disabled.
- **Scheduled checks:** Independent GitHub Actions worker runs genuine predictions in safe dry-run mode.

## System Architecture

Historical model training is separate from live prediction. Forecast rainfall maps and Random Forest storm probabilities are different outputs.

```mermaid
%%{init: {"themeVariables": {"fontSize": "12px"}, "flowchart": {"nodeSpacing": 16, "rankSpacing": 22, "padding": 8, "diagramPadding": 8, "useMaxWidth": true}}}%%
flowchart TB
    subgraph Training["Historical model development"]
        ERA5["ERA5 reanalysis"] --> PREP["Preprocessing and engineered next-hour labels"]
        PREP --> TRAIN["29-feature Random Forest training"]
        TRAIN --> MODEL["Saved model and selected 35% threshold"]
    end

    subgraph Inference["Genuine live inference and weather display"]
        ECMWF["ECMWF forecasts via Open-Meteo"] --> INPUT["Unit conversion and 29-feature preparation"]
        MODEL --> RF["Random Forest inference"]
        INPUT --> RF
        RF --> RESULT["Validated next-hour probability"]
        RESULT --> DASH["Dashboard risk display and CSV history"]
        ECMWF --> REGIONAL["Actual regional precipitation samples"]
        REGIONAL --> MAP["Interpolated rainfall map and six-hour weather chart"]
    end

    subgraph Notifications["Guarded SMS decision pathways"]
        RESULT --> WARN{"Fresh prediction at or above 35%?"}
        WARN -->|No| NONE["No warning submission"]
        ADMIN["Administrator-confirmed test SMS; no weather warning"] --> TWILIO["Twilio submission; delivery not confirmed"]
        WARN -->|Worker path| MODE{"Live mode approved and enabled?"}
        MODE -->|"No - current configuration"| DRY["Dry-run output; no SMS or issue writes"]
        MODE -->|"Future live path"| LEDGER["Serialized GitHub issue reservation"]
        LEDGER -->|"New reservation only"| TWILIO
    end
```

## Getting Started

**1. Clone the repository**

```powershell
git clone https://github.com/mdvar2/matatiele-storm-early-warning-system.git
cd matatiele-storm-early-warning-system
```

**2. Set up Python 3.12 and install dependencies**

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
```

**3. Start the dashboard**

```powershell
python -m streamlit run 16_dashboard.py
```

Open `http://localhost:8501`. Internet access is needed to retrieve current forecasts.

**Optional: Test the scheduled forecast check without sending SMS**

```powershell
python 18_scheduled_sms_worker.py --dry-run
```

Administrator SMS features require private settings in `.streamlit/secrets.toml`, created from `.streamlit/secrets.toml.example`. **Never commit passwords, Twilio credentials or recipient numbers.** See [SMS configuration and safety](README_SMS_SETUP.md).

## Beta Status and Limitations

**Verified:** Genuine forecast/model inference, a manually received Twilio test SMS, 73 automated safety tests and successful GitHub Actions dry-runs.

**Not yet verified:** Real unattended storm-warning delivery. Automatic SMS remains **disabled**; the dashboard cannot send storm warnings, and the independent worker is the designated future automatic sender.

**Future work:** Local sensors, Raspberry Pi/edge deployment, offline resilience, field validation and further assessment of forecast accuracy.

> **Research disclaimer:** This is an academic Beta prototype, not an official South African Weather Service (SAWS) warning service. Follow official weather alerts and local disaster-management guidance.
