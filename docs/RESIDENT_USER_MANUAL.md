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
| **Risk card**, e.g. *Low storm risk (model estimate)* | The model's estimate for the next hour, the forecast period and the time of the last update. |
| **Weather · next hour (forecast)** | Forecast temperature, conditions, rainfall and wind for Matatiele. This is a forecast, not an observation. |
| **Be prepared / Act now** | A few short safety actions that match the current risk. |
| **Get free SMS storm warnings** | Opens the SMS registration page. |
| **About this estimate and full safety advice** | Tap to open the full explanation, the area covered, the model caveat and the complete safety advice. |
| **Rainfall forecast map** | Forecast rain around Matatiele. **Map data and method** explains how it is made. It is not radar. |

The bar under the title has **Home, Forecast, Map** and **Safety**. Tap the **☰** button (top left) for **Alerts, Risk Analysis, Historical Data** and **About**.

The homepage also shows:
- a **banner** at the top saying whether a storm warning is in effect;
- **Official weather warnings (SAWS)**, a link to the South African Weather Service;
- **Emergency contacts**: tap a number to call it from a phone.

**Light or dark?** Use the **Dark theme** switch under the clock. Your choice stays when you change page or reload.

**Slow or expensive data?** Use the **Low-data text version** link. It shows the same information as plain text.

### Other pages

- **Safety:** what to do before a storm, and when a storm is close.
- **Alerts** (☰ menu): current and past storm warnings, warning details, and **SMS alerts** (register, check or cancel; see below). Who received an SMS is never shown.
- **Forecast:** a 36-hour temperature and rain chart, and the storm ingredients the model uses.
- **Map:** the storm map, with a slider through the coming forecast hours.
- **Risk Analysis** (☰ menu): the model estimate against the warning level. **Historical Data** (☰ menu): past predictions. **About** (☰ menu): how warnings work, as one diagram.

## 3. Registering for SMS warnings

You need a South African mobile number, for example `082 123 4567` or `+27 82 123 4567`. Landlines and toll-free numbers cannot receive warnings.

1. Open **☰ → Alerts**, choose **SMS alerts**, and stay on the **Subscribe** tab. (The **Get free SMS storm warnings** button on the homepage goes straight there.)
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
| The page reloaded and the code box disappeared | Your code still works. Open **Already received a code?** under the Subscribe form, enter your number and the code, and press **Verify and activate**. |

If your number is **already registered**, you receive an SMS that says so instead of a code. To check or cancel the subscription, use **Manage my subscription**.

## 4. Checking or cancelling your subscription

1. Open **☰ → Alerts** → **SMS alerts**, then the **Manage my subscription** tab.
2. Enter your registered mobile number and press **Send code**.
3. Enter the 6-digit code from the SMS and press **Confirm**.
4. Your status appears: **Active**, the area, and the date you joined.
5. To stop receiving warnings, tick **I want to stop receiving SMS storm warnings**, then press **Unsubscribe**.
6. When you are done, press **Finish**.

To protect your privacy, the page never says whether a number is registered. Only the owner of the phone receives the code. When you unsubscribe, your number is deleted from the warning list. You can register again at any time.

**Replying STOP:** if you reply STOP to a warning SMS and the SMS provider reports it, the system unsubscribes you automatically. Some sender numbers cannot receive replies, so **the web page is the reliable way to unsubscribe**.

## 5. Storm warnings on the Alerts page

1. The banner on **Home** says whether a warning is in effect (**Open the warning** goes straight to it). **☰ → Alerts** lists **Current warnings** and **Past warnings**.
2. Press **View** on a warning to see:
   - its severity;
   - the forecast period (the hour the warning covers);
   - the location;
   - the model estimate;
   - when it was issued;
   - short actions under **Act now**, with full advice one tap away.
3. Press **I have read this warning** to acknowledge it. **This only records that the warning was viewed on your device.** It does not tell anyone you are safe, and it does not ask for help. Each device can acknowledge a warning once; if you return later, the page shows when you acknowledged it.
4. If you need help, tap **10111** (police), **10177** (ambulance and fire) or **112** (any emergency from a cellphone). Calls go to national emergency services, not to this system.

A warning marked **DEVELOPMENT TEST · not a real warning** appears only on a project computer during testing or demonstrations.

## 6. What a warning SMS looks like

```
MATATIELE MODEL ALERT: 30 Oct 09:00-10:00 SAST. Storm risk 62%. If severe weather
develops, stay indoors. Avoid lightning/flooded roads. Check SAWS.
```

The SMS gives the hour of the expected storm and the model's estimate. You receive **at most one SMS per warning hour**.

## 7. Your information

- The system asks only for your mobile number and area, and records the date you gave consent.
- Your number is stored encrypted. Staff screens show only a partly hidden number.
- Your number is never published, and never shown with warnings.
- Acknowledging a warning stores only a random code kept in your browser (scrambled before it is saved) and the time. It does not store your name or number.
- When you unsubscribe, the encrypted number is deleted.
- A number that is never verified is deleted after 2 days. Records of cancelled subscriptions and of sent messages are deleted after 30 days.

## 8. If SMS registration is closed

You may see *SMS registration is not open yet*. This means the project team has not switched on the SMS service. The dashboard, safety advice and warning history still work.
