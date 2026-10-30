# Matatiele Storm Early Warning: Resident User Manual

This guide is for people who live or work in Matatiele and want to use the storm warning dashboard and its free SMS warnings.

> **Important.** This is an academic research prototype. It is **not** an official South African Weather Service (SAWS) warning service. Always follow official SAWS warnings and the instructions of local disaster management.

---

## 1. What the system does

Every hour, the system downloads a real weather forecast for Matatiele (ECMWF, via Open-Meteo). A computer model then estimates the chance of a storm in the **next hour**.

- If the chance is **35% or higher**, the system issues a storm warning. Registered residents receive it by SMS.
- If the chance is below 35%, no warning is sent.

The dashboard always shows the latest estimate. It also shows when the forecast was last updated.

## 2. The dashboard

Open the dashboard link in any web browser, on a phone or a computer. The main page shows:

| Item | Meaning |
|---|---|
| **Status strip** (under the title) | Whether the forecast is live, when it was updated, and where the data comes from. |
| **Status card**, e.g. *Low storm risk (model estimate)* | The model's verdict for the next hour, with the forecast period, the estimate, the last update and the area covered. |
| **Be prepared / Act now** | Short safety advice that matches the current risk. |
| **Get free SMS storm warnings for Matatiele** | Opens the SMS registration page. |
| **Rainfall forecast map** and **Forecast weather** | Forecast rain around Matatiele, and the forecast temperature, cloud, wind and pressure. These are forecasts, not observations. |

On a phone, the page buttons (Dashboard, Safety Advice, SMS Alerts, …) appear under the title. On a computer, they appear in the left-hand menu.

**Slow or expensive data?** Use the **Low-data text version** link. It shows the same information as plain text.

### Other pages

- **Safety Advice:** what to do before, during and after a storm.
- **SMS Alerts:** register for, check or cancel SMS warnings (see below).
- **Warning History:** every genuine storm warning the system has issued. It never shows who received an SMS.
- **Live Forecast, Weather Map, Risk Analysis, Historical Data:** more detail for interested users.
- **About:** how the system works, and its limits.

## 3. Registering for SMS warnings

You need a South African mobile number, for example `082 123 4567` or `+27 82 123 4567`. Landlines and toll-free numbers cannot receive warnings.

1. Open **SMS Alerts** and stay on the **Subscribe** tab.
2. Enter your mobile number.
3. Check that the warning area is **Matatiele (town and immediate surroundings)**. This is currently the only area.
4. Read the agreement and tick **I agree to receive SMS storm warnings…**.
5. Press **Send verification code**.
6. You will receive an SMS with a **6-digit code**. Type it into **Verification code** and press **Verify and activate**.
7. The page shows **Your subscription is active**, with your number partly hidden (for example `+27 82 *** **67`).

You will now receive an SMS whenever the model warns of a storm in Matatiele.

### Problems with the code

| Message | What to do |
|---|---|
| *That code is not correct* | Check the SMS and type the 6 digits again. |
| *The code has expired* | Codes last 10 minutes. Press **Send a new code**. |
| *Too many wrong attempts* | After 5 wrong tries the code stops working. Press **Send a new code**. |
| *Please wait a minute…* | You can ask for a new code once a minute, up to 3 times an hour. |
| *Too many codes were requested…* | Try again later (the limit is 6 codes per day per number). |
| No SMS arrives | Check that the number is correct, or press **Use a different number** to change it. |

If your number is **already registered**, you receive an SMS that says so instead of a code. To check or cancel the subscription, use **Manage my subscription**.

## 4. Checking or cancelling your subscription

1. Open **SMS Alerts**, then the **Manage my subscription** tab.
2. Enter your registered mobile number and press **Send code**.
3. Enter the 6-digit code from the SMS and press **Confirm**.
4. Your status appears: **Active**, the area, and the date you joined.
5. To stop receiving warnings, tick **I want to stop receiving SMS storm warnings**, then press **Unsubscribe**.
6. When you are done, press **Finish**.

To protect your privacy, the page never says whether a number is registered. Only the owner of the phone receives the code. When you unsubscribe, your number is deleted from the warning list. You can register again at any time.

**Replying STOP:** if you reply STOP to a warning SMS and the SMS provider reports it, the system unsubscribes you automatically. Some sender numbers cannot receive replies, so **the web page is the reliable way to unsubscribe**.

## 5. What a warning SMS looks like

```
MATATIELE MODEL ALERT: 30 Oct 09:00-10:00 SAST. Storm risk 62%. If severe weather
develops, stay indoors. Avoid lightning/flooded roads. Check SAWS.
```

The SMS gives the hour of the expected storm and the model's estimate. You receive **at most one SMS per warning hour**.

## 6. Your information

- The system asks only for your mobile number and area, and records the date you gave consent.
- Your number is stored encrypted. Staff screens show only a partly hidden number.
- Your number is never published, and never shown on the Warning History page.
- When you unsubscribe, the encrypted number is deleted.

## 7. If SMS registration is closed

You may see *SMS registration is not open yet*. This means the project team has not switched on the SMS service. The dashboard, safety advice and warning history still work.
