# 🌩️ Matatiele Smart Resilient Storm Early Warning System

## Research Project

**Smart Resilient Storm Early Warning System for Low Connectivity Environments: A Case of Matatiele**

---

## 1. Project Overview

The Matatiele Smart Resilient Storm Early Warning System is an Alpha proof-of-concept developed to demonstrate a machine-learning-based approach to next-hour storm prediction and early warning for Matatiele, South Africa.

The system uses historical weather data to train a Random Forest machine-learning model and uses live forecast data to generate operational storm predictions.

The current Alpha prototype demonstrates the complete warning workflow:

1. Retrieve live weather forecast data.
2. Prepare the required model features.
3. Run the trained Random Forest classifier.
4. Calculate the probability of storm conditions.
5. Compare the probability against the warning threshold.
6. Display the risk through the Streamlit dashboard.
7. Send an SMS warning when the warning threshold is reached.

The broader research project focuses on designing a resilient warning system suitable for low-connectivity environments.

The current Alpha validates the software, machine-learning, dashboard, and SMS-warning components of this architecture. A future full deployment would extend the system with local weather sensors, edge processing, local storage, and communication mechanisms suitable for environments where Internet connectivity is unreliable.

---

## 2. Problem Statement

Communities in rural and low-connectivity environments may have limited access to timely weather information and early-warning services.

Severe weather can create risks to:

- people;
- livestock;
- agriculture;
- infrastructure;
- transport;
- communication systems; and
- local economic activities.

The purpose of this project is therefore to investigate how machine learning and resilient warning technologies can be combined to provide useful storm early warnings for communities such as Matatiele.

---

## 3. Project Objectives

The main objectives of the project are to:

- develop a machine-learning model capable of identifying potential storm conditions;
- use historical weather information for model training;
- use live forecast information for operational predictions;
- estimate next-hour storm probability;
- classify storm risk based on the predicted probability;
- provide a simple and understandable early-warning dashboard;
- deliver SMS notifications when warning conditions are detected;
- prevent duplicate SMS warnings for the same prediction period;
- provide a controlled testing environment for demonstrating warning behaviour;
- investigate an architecture suitable for low-connectivity environments; and
- establish a foundation for future integration with local weather sensors and edge-computing devices.

---

## 4. Current Alpha Implementation

The current system is an **Alpha proof-of-concept**.

It currently implements:

- Random Forest machine learning;
- historical ERA5 weather data processing;
- live Open-Meteo / ECMWF forecast retrieval;
- next-hour storm prediction;
- storm probability estimation;
- risk-level classification;
- a configurable warning threshold;
- a Streamlit monitoring dashboard;
- prediction history;
- automatic SMS warning logic;
- Twilio SMS integration;
- duplicate-warning protection;
- manual test SMS functionality; and
- controlled Presentation Test Mode.

The Alpha demonstrates that the main prediction-to-warning workflow can operate successfully.

---

## 5. Current Alpha Architecture

```text
       Historical ERA5 Data
               |
               v
      Data Preparation
               |
               v
      Feature Engineering
               |
               v
     Random Forest Training
               |
               v
        Trained Model


LIVE OPERATION
==============

Open-Meteo / ECMWF Forecast
               |
               v
      Feature Preparation
               |
               v
      Random Forest Model
               |
               v
       Storm Probability
               |
               v
      Risk Classification
               |
               v
      35% Alert Threshold
               |
          +----+----+
          |         |
          v         v
     Dashboard    SMS Warning
                    |
                    v
                  Twilio
```

---

## 6. Machine-Learning Model

The prediction system uses a **Random Forest classifier**.

Random Forest was selected because it is suitable for classification problems involving multiple environmental variables and can model nonlinear relationships between weather conditions.

The model is trained using historical weather observations and generates a probability representing the likelihood of storm conditions.

### Model

```text
Algorithm: Random Forest Classifier
Number of Trees: 300
Prediction Type: Binary storm classification
Prediction Horizon: Next hour
```

The dashboard uses the probability generated by the Random Forest model to determine the current storm risk.

The warning threshold is currently configured at:

```text
35%
```

When the storm probability reaches or exceeds this threshold, the system treats the prediction as a storm-warning condition.

---

## 7. Risk Classification

The dashboard divides storm probability into four operational risk categories.

| Probability | Risk Level |
|---|---|
| 0–9% | LOW |
| 10–19% | ELEVATED |
| 20–34% | MODERATE |
| 35% and above | WARNING |

The **35% warning threshold** is displayed on the Prediction History graph so that the relationship between model probability and warning activation can be clearly observed.

The threshold is part of the warning decision layer and does not manually replace the Random Forest prediction.

---

## 8. Weather Data

### Historical Data

Historical weather data used during model development originates from:

```text
ERA5
```

The historical datasets are used for:

- cleaning;
- preprocessing;
- feature engineering;
- storm labelling;
- training;
- testing; and
- evaluation of the Random Forest classifier.

### Live Forecast Data

The Alpha system uses:

```text
Open-Meteo / ECMWF forecast data
```

for operational next-hour prediction.

The live forecast variables displayed on the dashboard include weather measurements such as:

- temperature;
- dew point;
- cloud cover;
- precipitation;
- showers;
- CAPE;
- wind speed;
- wind gust; and
- mean sea-level pressure.

The exact feature set used by the machine-learning model is prepared by the project's feature-processing pipeline.

---

## 9. Dashboard

The user interface is developed using **Streamlit**.

The dashboard is designed to provide a simple early-warning interface rather than exposing unnecessary machine-learning complexity to the end user.

The main dashboard displays:

- live forecast status;
- Random Forest status;
- current risk level;
- last update time;
- storm probability;
- alert threshold;
- temperature;
- wind gust;
- next-hour storm risk;
- forecast input time;
- prediction valid time;
- current forecast conditions;
- warning-delivery status;
- prediction history; and
- SMS notification status.

The interface uses visual risk indicators to make warning information easier to understand.

---

## 10. Prediction History

The system maintains a prediction history showing previous storm predictions.

The history includes information such as:

- prediction time;
- storm probability;
- prediction status;
- temperature;
- CAPE; and
- wind gust.

The Prediction History graph uses a fixed:

```text
0% – 100%
```

probability scale.

A visible line at:

```text
35%
```

shows the warning threshold.

This makes it possible to visually identify when a predicted storm probability approaches or exceeds the warning level.

---

## 11. SMS Warning System

The system integrates with **Twilio** for SMS delivery.

When the Random Forest prediction reaches the configured warning threshold, the notification pipeline can automatically send an SMS warning to configured recipients.

The SMS warning can include information such as:

- storm probability;
- warning threshold;
- prediction validity period;
- temperature;
- rainfall;
- CAPE;
- wind gust; and
- location.

### Automatic Warning Logic

```text
Random Forest Prediction
          |
          v
   Storm Probability
          |
          v
Probability >= 35% ?
       /       \
     NO         YES
     |           |
     v           v
No SMS      Check Duplicate
                 |
                 v
          Warning already sent?
              /       \
            YES        NO
             |          |
             v          v
          Do not      Send SMS
          resend       warning
```

---

## 12. Duplicate-Warning Protection

The system includes duplicate-warning protection.

This prevents the same storm warning from being repeatedly sent for the same prediction period.

For example:

```text
First warning attempt:
Status: SENT

Second attempt for same prediction:
Status: DUPLICATE
SMS not sent again
```

This feature reduces unnecessary repeated alerts and SMS usage.

---

## 13. Presentation Test Mode

The dashboard contains a controlled **Presentation Test Mode**.

This mode exists because real storm conditions cannot be guaranteed during a system demonstration.

When enabled, the interface can demonstrate how the system responds to a simulated storm-warning condition.

Example test values include:

```text
Storm Probability: 60%
Warning Threshold: 35%
Temperature: 23.5 °C
Precipitation: 8.4 mm
CAPE: 1450 J/kg
Wind Gust: 18.0 m/s
```

Because:

```text
60% >= 35%
```

the interface demonstrates a storm-warning state.

### Important

Presentation Test Mode:

- does NOT retrain the Random Forest model;
- does NOT modify the real live forecast;
- does NOT change the production model;
- does NOT represent an actual weather warning; and
- is clearly identified as a controlled simulation.

Its purpose is only to demonstrate the warning workflow safely.

---

## 14. Test SMS

The dashboard also provides a:

```text
Send Test SMS
```

function.

This allows SMS configuration to be verified without waiting for a real storm prediction.

A test SMS is different from an automatic storm warning.

The button is intended for:

- configuration testing;
- demonstrations;
- verifying Twilio connectivity; and
- confirming that the destination phone can receive messages.

---

## 15. Automatic Warning Pipeline Validation

A controlled validation script is included to test the automatic warning pipeline.

The validation checks:

1. SMS configuration.
2. Simulated storm conditions.
3. Warning-threshold logic.
4. Automatic SMS delivery.
5. Duplicate-warning protection.

A successful test produces a result similar to:

```text
VALIDATION RESULT
=================

SUCCESS

Automatic SMS warning delivery works.
Duplicate-warning protection works.

The automatic notification pipeline passed the test.
```

The validation process does not modify the trained Random Forest model or live forecast files.

---

## 16. Low-Connectivity Research Focus

The research project specifically targets:

**low-connectivity environments.**

The current Alpha still depends on Internet connectivity for certain services, particularly:

- retrieving live forecast information; and
- communicating with the Twilio SMS service.

Therefore, the current implementation should not be described as a completely offline system.

Instead, it serves as a proof-of-concept for the machine-learning and warning workflow that could later be deployed using a more resilient architecture.

---

## 17. Intended Full Low-Connectivity Architecture

A future deployment could use local weather sensors and edge computing.

```text
       Local Weather Sensors
                |
                v
         Edge Device
                |
                v
      Local Data Processing
                |
                v
      Random Forest Model
                |
                v
       Storm Probability
                |
                v
       Warning Decision
                |
         +------+------+
         |             |
         v             v
    Local Display    GSM / SMS
         |
         v
    Local Storage
         |
         v
Cloud Synchronisation
when connectivity returns
```

In this architecture, the trained machine-learning model could operate locally on an edge device.

Local sensors could provide weather observations without requiring continuous access to an Internet weather API.

---

## 18. Proposed Sensor Integration

With suitable hardware and funding, the full system could be extended with local environmental sensors.

Potential measurements could include:

- temperature;
- humidity;
- atmospheric pressure;
- rainfall;
- wind speed;
- wind direction; and
- other storm-related atmospheric measurements.

The sensor data could be collected by a local edge-computing device and processed close to the community where the warning is required.

This would reduce dependence on continuous Internet connectivity.

### Important

Local weather sensors are part of the **proposed future architecture** and are **not currently implemented in the Alpha prototype**.

---

## 19. Resilience Strategy

The intended resilient design would reduce reliance on continuous cloud connectivity.

A future system could:

- collect weather measurements locally;
- store observations locally;
- execute the trained Random Forest model on an edge device;
- generate warnings locally;
- deliver warnings through available communication channels;
- continue collecting data during Internet outages; and
- synchronise stored information when connectivity becomes available again.

This architecture is intended to make the warning system more appropriate for rural and low-connectivity environments.

---

## 20. Project Structure

The project contains scripts for the different stages of the machine-learning and operational pipeline.

Example structure:

```text
Matatiele_System/
│
├── 01_load_data.py
├── 02_clean_data.py
├── 03_create_labels.py
├── 04_merge_data.py
├── 05_feature_engineering.py
├── 06_prepare_model_data.py
├── 07_train_random_forest.py
├── 08_evaluate_threshold.py
├── 09_predict_storm.py
├── 10_predict.py
├── 11_auto_update_and_predict.py
├── 12_live_forecast_and_predict.py
├── 14_train_live_compatible_random_forest.py
├── 15_evaluate_live_threshold.py
├── 16_dashboard.py
├── 17_validate_warning_pipeline.py
├── sms_alert.py
├── requirements.txt
└── README.md
```

Additional generated datasets, models, prediction files, logs, and configuration files may also exist in the project directory.

---

## 21. Installation

### Requirements

The system requires:

```text
Python 3.x
```

Install the project dependencies using:

```powershell
pip install -r requirements.txt
```

The project uses Python libraries associated with:

- data processing;
- machine learning;
- Streamlit;
- forecast retrieval;
- graphing;
- model persistence; and
- SMS communication.

---

## 22. Running the Dashboard

Navigate to the project directory:

```powershell
cd "C:\path\to\219010727_Gwinya"
```

Then run:

```powershell
streamlit run 16_dashboard.py
```

Streamlit should open the dashboard in a browser.

The local address is normally:

```text
http://localhost:8501
```

---

## 23. Updating the Live Forecast

The dashboard provides an:

```text
Update Live Forecast
```

control.

This triggers the operational workflow used to retrieve updated forecast information and generate a new next-hour prediction.

The resulting prediction is then reflected in the dashboard and prediction history.

---

## 24. Twilio Configuration

The SMS system requires Twilio configuration.

The following values are required:

```text
TWILIO_ACCOUNT_SID
TWILIO_AUTH_TOKEN
TWILIO_FROM_NUMBER
ALERT_TO_NUMBERS
```

Example PowerShell configuration:

```powershell
$Env:TWILIO_ACCOUNT_SID="YOUR_ACCOUNT_SID"
$Env:TWILIO_AUTH_TOKEN="YOUR_AUTH_TOKEN"
$Env:TWILIO_FROM_NUMBER="+1XXXXXXXXXX"
$Env:ALERT_TO_NUMBERS="+27XXXXXXXXX"
```

Then start the dashboard from the same environment:

```powershell
streamlit run 16_dashboard.py
```

---

## 25. Security

Twilio credentials must **never** be hard-coded directly into source code that will be submitted or uploaded to a public repository.

Do not include real values for:

```text
TWILIO_ACCOUNT_SID
TWILIO_AUTH_TOKEN
```

in the README or source code.

Credentials should be stored using:

- environment variables;
- a local `.env` file excluded from version control; or
- another secure secrets-management mechanism.

Example `.gitignore` entries:

```text
.env
.streamlit/secrets.toml
__pycache__/
*.pyc
```

Any credentials accidentally exposed publicly should be rotated.

---

## 26. SMS Configuration Persistence

Environment variables entered only into a temporary terminal session may disappear when that terminal or VS Code session is closed.

For development, credentials can instead be loaded from a local configuration mechanism such as a `.env` file.

Example:

```text
TWILIO_ACCOUNT_SID=YOUR_ACCOUNT_SID
TWILIO_AUTH_TOKEN=YOUR_AUTH_TOKEN
TWILIO_FROM_NUMBER=YOUR_TWILIO_NUMBER
ALERT_TO_NUMBERS=YOUR_DESTINATION_NUMBER
```

The `.env` file must remain private and should not be included in the submitted public source repository.

---

## 27. System Testing

The system has been tested at several levels.

### Machine-Learning Testing

The Random Forest model is evaluated using historical weather data.

### Live Forecast Testing

The operational pipeline retrieves forecast data and transforms it into the format required by the trained model.

### Dashboard Testing

The Streamlit dashboard displays:

- model status;
- live forecast information;
- storm probability;
- risk classification;
- prediction history; and
- warning status.

### SMS Testing

The SMS subsystem can be tested independently using the Send Test SMS control.

### Automatic Warning Testing

The automatic warning pipeline can be tested using the controlled validation script.

### Duplicate Protection Testing

Repeated attempts to send the same prediction warning are blocked.

### Presentation Testing

Presentation Test Mode demonstrates the warning state without modifying the real machine-learning model or live forecast.

---

## 28. Current Limitations

The current Alpha prototype has several limitations.

### Internet Dependency

Live forecast retrieval currently requires Internet connectivity.

### Twilio Dependency

Twilio SMS delivery requires connectivity to the Twilio service.

### Sensor Integration

Local weather sensors have not yet been integrated.

### Edge Computing

The Random Forest model currently runs on the development computer rather than a dedicated field edge device.

### Geographic Scope

The system is designed around the Matatiele case study and has not yet been validated for wider geographic deployment.

### Alpha Development Stage

The system remains a research proof-of-concept and should not replace official meteorological warning services.

---

## 29. Future Improvements

Future development could include:

- integration of local weather sensors;
- deployment on a Raspberry Pi or similar edge-computing device;
- local/offline weather-data storage;
- offline prediction capability;
- automatic synchronisation when Internet connectivity returns;
- direct GSM/SMS communication;
- reduced dependence on cloud-based services;
- integration of additional storm indicators;
- expanded historical storm datasets;
- improved probability calibration;
- additional model evaluation;
- support for multiple communities;
- multilingual warning messages;
- configurable warning recipients;
- improved warning escalation levels;
- mobile-friendly dashboard deployment; and
- field testing in Matatiele.

---

## 30. Relationship Between the Alpha and the Research Proposal

The current Alpha should be understood as a validation of the core concept.

### Current Alpha

```text
ERA5 historical data
        +
Live ECMWF forecast data
        ↓
Random Forest
        ↓
Storm probability
        ↓
Risk assessment
        ↓
Dashboard
        ↓
SMS warning
```

### Intended Full System

```text
Local sensors
      ↓
Edge processing
      ↓
Random Forest
      ↓
Local warning decision
      ↓
Dashboard / GSM / SMS
      ↓
Local storage
      ↓
Cloud synchronisation when available
```

The Alpha therefore validates the main intelligence and warning pipeline before investment in the physical sensor and edge-computing infrastructure required for full deployment.

---

## 31. Important Disclaimer

This project is an academic Alpha proof-of-concept.

It is **not an official meteorological warning service** and should not be used as a replacement for warnings issued by recognised weather authorities.

Presentation Test Mode produces simulated warning conditions for demonstration purposes only.

The purpose of the project is to demonstrate the technical feasibility of combining machine learning, weather data, resilient system design, and automated warning delivery.

---

## 32. Conclusion

The Matatiele Smart Resilient Storm Early Warning System demonstrates an end-to-end machine-learning early-warning workflow.

The Alpha prototype combines:

```text
Historical Weather Data
        +
Live Forecast Data
        +
Random Forest Machine Learning
        +
Next-Hour Prediction
        +
Risk Classification
        +
Dashboard Visualisation
        +
Automatic SMS Warning
```

The current implementation demonstrates the software-based warning pipeline, while the proposed future architecture extends the system toward local sensing, edge processing, offline operation, and resilient communication.

This provides a foundation for the research objective of developing a:

**Smart Resilient Storm Early Warning System for Low Connectivity Environments: A Case of Matatiele.**
