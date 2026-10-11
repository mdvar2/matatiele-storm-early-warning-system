# 🌩️ Matatiele Smart Resilient Storm Early Warning System

**Research project:** *Smart Resilient Storm Early Warning System for Low Connectivity Environments: A Case of Matatiele*

**Status:** Academic Beta prototype · **Location:** Matatiele, Eastern Cape, South Africa

**[Explore the live dashboard](https://matatiele-storm-early-warning-system-jykpxrtek3zejgqfk5xvr.streamlit.app)**

![Python](https://img.shields.io/badge/Python-3.12-3776AB?logo=python&logoColor=white)
![Streamlit](https://img.shields.io/badge/Streamlit-Dashboard-FF4B4B?logo=streamlit&logoColor=white)
![scikit-learn](https://img.shields.io/badge/scikit--learn-Random%20Forest-F7931E?logo=scikitlearn&logoColor=white)
![Twilio](https://img.shields.io/badge/Twilio-SMS-F22F46?logo=twilio&logoColor=white)
![GitHub Actions](https://img.shields.io/badge/GitHub%20Actions-Scheduled%20Checks-2088FF?logo=githubactions&logoColor=white)

## Overview

A machine-learning research prototype designed to support earlier awareness of potential storms in Matatiele. It combines historical weather data, genuine forecasts, a Random Forest classifier trained on historical ERA5 data, interactive weather visualisations and SMS integration. The current Beta is Internet-dependent; resilient offline deployment is a future research goal.

## Key Features

- **Next-hour storm prediction:** Random Forest model using 29 live-compatible features and a **35% warning threshold**.
- **Live weather inputs:** ECMWF forecasts retrieved through Open-Meteo.
- **Interactive dashboard:** Seven Streamlit pages covering forecasts, risk, maps, history and alerts.
- **Rainfall visualisation:** Genuine ECMWF forecast-grid samples interpolated over a satellite basemap; **not live radar**.
- **SMS integration:** Twilio connectivity tests and LIVE-enabled worker warnings when fresh predictions meet the 35% threshold.
- **Scheduled checks:** Independent GitHub Actions worker runs genuine predictions in approved LIVE mode, without requiring an open dashboard.

## System Architecture

Historical ERA5 training is separate from genuine ECMWF inference. The LIVE-enabled worker applies freshness, threshold and duplicate-submission safeguards before warning submission.

```mermaid
flowchart TB
    subgraph Development["Model Development"]
        ERA5["Historical ERA5 data"] --> TRAIN["Random Forest training"]
        TRAIN --> MODEL["Saved model: 29 live-compatible features"]
    end

    subgraph Forecasting["Live Forecasting and Prediction"]
        ECMWF["ECMWF via Open-Meteo"] --> PREP["Live preprocessing"]
        PREP --> RF["Random Forest inference"]
        RF --> PROB["Next-hour storm probability"]
        PROB --> DASH["Streamlit dashboard"]
        ECMWF --> MAP["Regional forecast rainfall map: not radar"]
    end
    MODEL --> RF

    subgraph SMS["Automatic SMS Warning"]
        WORKER["Independent GitHub Actions LIVE worker"]
        VALID{"Fresh, valid prediction?"}
        VALID -->|Yes| THRESHOLD{"Storm probability >=35%?"}
        VALID -->|No| NONE["No SMS"]
        THRESHOLD -->|No| NONE
        THRESHOLD -->|Yes| RESERVE{"GitHub Issues reservation: new?"}
        RESERVE -->|No or error| NONE
        RESERVE -->|Yes| TWILIO["Twilio SMS submission: delivery unconfirmed"]
    end
    WORKER -->|Invokes pipeline independently| PREP
    PROB -->|Worker-run result| VALID
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

**Verified:** Genuine ECMWF retrieval and Random Forest inference; unattended scheduled LIVE execution (run #6, **0.00%**, below 35%, so no warning SMS); real phone receipt of the explicitly labelled **NO WEATHER WARNING** connectivity test (run #4); **77 automated tests and 28 subtests** passed.

**Not yet observed:** Automatic storm-warning submission and delivery during a genuine high-risk event. High-risk decisions, duplicate prevention, configuration validation and uncertain outcomes have been tested with mocks. A successful LIVE run below threshold does not demonstrate warning delivery, and API acceptance is not confirmed recipient delivery.

The dashboard does not independently send automatic storm warnings. Its private settings are separate from GitHub Actions secrets. See [SMS configuration and safety](README_SMS_SETUP.md) for the approved LIVE setup and safeguards.

**Future work:** Local sensors, Raspberry Pi/edge processing, offline resilience, LoRa, field validation and further assessment of forecast accuracy.

> **Research disclaimer:** This is an academic Beta prototype, not an official South African Weather Service (SAWS) warning service. Follow official weather alerts and local disaster-management guidance.
