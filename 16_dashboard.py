from pathlib import Path

from datetime import datetime

from zoneinfo import ZoneInfo

import subprocess

import sys



import altair as alt

import pandas as pd

import streamlit as st



from sms_alert import (
    sms_is_configured,
    send_storm_sms,
    send_test_sms,
    send_simulated_storm_sms,
)



# ============================================================

# PATHS

# ============================================================



BASE_DIR = Path(__file__).resolve().parent



MODEL_DIR = BASE_DIR / "outputs" / "model_live"



PREDICTION_FILE = (

    MODEL_DIR / "live_forecast_prediction.csv"

)



THRESHOLD_FILE = (

    MODEL_DIR / "live_selected_threshold.txt"

)



HISTORY_FILE = (

    MODEL_DIR / "prediction_history.csv"

)



SMS_LOG_FILE = (

    MODEL_DIR / "sms_alert_log.csv"

)



LIVE_SCRIPT = (

    BASE_DIR / "12_live_forecast_and_predict.py"

)





# ============================================================

# PAGE CONFIGURATION

# ============================================================



st.set_page_config(

    page_title=(

        "Matatiele Smart Resilient "

        "Storm Early Warning System"

    ),

    page_icon="⛈️",

    layout="wide",

    initial_sidebar_state="expanded",

)





# ============================================================

# CUSTOM WEATHER THEME

# ============================================================



st.markdown(

    """

    <style>



    .stApp {

        background:

            linear-gradient(

                180deg,

                #cceeff 0px,

                #e7f7ff 350px,

                #f5fbff 750px,

                #ffffff 100%

            );



        color: #083b68;

    }





    [data-testid="stMainBlockContainer"] {

        max-width: 1250px;

        padding-top: 2rem;

        padding-bottom: 4rem;

    }





    [data-testid="stHeader"] {

        background:

            rgba(

                204,

                238,

                255,

                0.95

            );



        border-bottom:

            1px solid #b7dff3;

    }





    [data-testid="stSidebar"] {

        background:

            linear-gradient(

                180deg,

                #1686c7 0px,

                #1686c7 95px,

                #e9f7ff 95px,

                #f7fcff 100%

            );



        border-right:

            1px solid #acd8ef;

    }





    [data-testid="stSidebar"] > div {

        background: transparent;

    }





    [data-testid="stSidebar"] h1,

    [data-testid="stSidebar"] h2,

    [data-testid="stSidebar"] h3 {

        color: #073e6b !important;

    }





    [data-testid="stSidebar"] p,

    [data-testid="stSidebar"] label {

        color: #174d74;

    }





    h1,

    h2,

    h3 {

        color: #184f7a !important;

    }





    p,

    span,

    div {

        font-family:

            "Segoe UI",

            Arial,

            sans-serif;

    }





    .main-title {

        font-size: 2.35rem;

        font-weight: 800;

        color: #064b87;

        margin-bottom: 0;

        line-height: 1.15;

    }





    .main-subtitle {

        color: #48789c;

        font-size: 1rem;

        margin-top: 0.55rem;

        margin-bottom: 1.8rem;

    }





    .simulation-banner {

        background: #fff3cd;

        border: 2px solid #e5a400;

        border-radius: 14px;

        padding: 18px 24px;

        margin-bottom: 1.4rem;

        color: #734d00;

        font-weight: 650;

    }





    [data-testid="stMetric"] {

        background:

            rgba(

                255,

                255,

                255,

                0.96

            );



        border:

            1px solid #b8dcef;



        border-radius:

            14px;



        padding:

            16px 18px;



        box-shadow:

            0 4px 13px

            rgba(

                42,

                109,

                151,

                0.07

            );

    }





    [data-testid="stMetricLabel"] {

        color: #356b90;

        font-weight: 600;

    }





    [data-testid="stMetricValue"] {

        color: #184f79;

        font-weight: 750;

    }





    .stButton > button {

        width: 100%;



        background:

            linear-gradient(

                135deg,

                #158cd4,

                #0875c2

            );



        color: white;



        border: none;



        border-radius: 10px;



        font-weight: 700;



        padding: 0.7rem 1rem;



        box-shadow:

            0 4px 10px

            rgba(

                0,

                102,

                170,

                0.18

            );

    }





    .stButton > button:hover {

        background:

            linear-gradient(

                135deg,

                #087ac3,

                #055f9f

            );



        color: white;



        border: none;

    }





    [data-testid="stExpander"] {

        background:

            rgba(

                255,

                255,

                255,

                0.92

            );



        border:

            1px solid #badced;



        border-radius: 11px;

    }





    [data-testid="stDataFrame"] {

        background: white;



        border:

            1px solid #badced;



        border-radius: 12px;



        overflow: hidden;

    }





    hr {

        border-color:

            #add5eb !important;

    }





    ::-webkit-scrollbar {

        width: 9px;

    }





    ::-webkit-scrollbar-track {

        background: #edf8fe;

    }





    ::-webkit-scrollbar-thumb {

        background: #7ebce1;

        border-radius: 10px;

    }



    </style>

    """,

    unsafe_allow_html=True,

)





# ============================================================

# TIMEZONE

# ============================================================



SAST = ZoneInfo(

    "Africa/Johannesburg"

)





# ============================================================

# HELPER FUNCTIONS

# ============================================================



def run_prediction():



    if not LIVE_SCRIPT.exists():



        st.error(

            f"Prediction script not found:\n"

            f"{LIVE_SCRIPT}"

        )



        return False



    try:



        result = subprocess.run(

            [

                sys.executable,

                str(LIVE_SCRIPT),

            ],

            cwd=BASE_DIR,

            capture_output=True,

            text=True,

            timeout=120,

        )



        if result.returncode != 0:



            st.error(

                "The live prediction script failed."

            )



            if result.stdout:



                st.code(

                    result.stdout

                )



            if result.stderr:



                st.code(

                    result.stderr

                )



            return False



        return True



    except subprocess.TimeoutExpired:



        st.error(

            "The live forecast request timed out."

        )



        return False



    except Exception as error:



        st.error(

            f"Prediction error: {error}"

        )



        return False





def save_history(

    prediction

):



    history_row = (

        prediction.copy()

    )



    if HISTORY_FILE.exists():



        history = pd.read_csv(

            HISTORY_FILE

        )



        history = pd.concat(

            [

                history,

                pd.DataFrame(

                    [history_row]

                ),

            ],

            ignore_index=True,

        )



    else:



        history = pd.DataFrame(

            [history_row]

        )



    if "prediction_for" in history.columns:



        history = (

            history

            .drop_duplicates(

                subset=[

                    "prediction_for"

                ],

                keep="last",

            )

        )



    history.to_csv(

        HISTORY_FILE,

        index=False,

    )





def get_risk_level(

    probability,

    threshold

):



    percent = (

        probability

        *

        100

    )



    threshold_percent = (

        threshold

        *

        100

    )



    if percent >= threshold_percent:



        return "WARNING"



    if percent >= 20:



        return "MODERATE"



    if percent >= 10:



        return "ELEVATED"



    return "LOW"





def get_risk_colours(

    risk_level

):



    if risk_level == "WARNING":



        return {

            "background":

                "#ffe3e8",



            "border":

                "#df5267",



            "text":

                "#b71935",



            "dot":

                "🔴",

        }



    if risk_level == "MODERATE":



        return {

            "background":

                "#fff0df",



            "border":

                "#ed9846",



            "text":

                "#bd5a10",



            "dot":

                "🟠",

        }



    if risk_level == "ELEVATED":



        return {

            "background":

                "#fff8d5",



            "border":

                "#d5b638",



            "text":

                "#8d7100",



            "dot":

                "🟡",

        }



    return {

        "background":

            "#e5f8ed",



        "border":

            "#5fc78a",



        "text":

            "#07843e",



        "dot":

            "🟢",

    }





def status_card(

    title,

    value,

    background,

    border,

    text_colour,

    subtitle=""

):



    subtitle_html = ""



    if subtitle:



        subtitle_html = (

            f"<div style='"

            f"font-size:0.78rem;"

            f"color:#5f819a;"

            f"margin-top:5px;"

            f"'>"

            f"{subtitle}"

            f"</div>"

        )



    html = (

        f"<div style='"

        f"background:{background};"

        f"border:1px solid {border};"

        f"border-radius:14px;"

        f"padding:18px;"

        f"min-height:109px;"

        f"box-shadow:0 4px 13px rgba(42,109,151,0.07);"

        f"'>"



        f"<div style='"

        f"font-size:0.82rem;"

        f"color:#356b90;"

        f"margin-bottom:8px;"

        f"'>"

        f"{title}"

        f"</div>"



        f"<div style='"

        f"font-size:2rem;"

        f"font-weight:800;"

        f"color:{text_colour};"

        f"line-height:1.15;"

        f"'>"

        f"{value}"

        f"</div>"



        f"{subtitle_html}"



        f"</div>"

    )



    st.markdown(

        html,

        unsafe_allow_html=True,

    )





# ============================================================

# LOAD THRESHOLD

# ============================================================



if THRESHOLD_FILE.exists():



    threshold = float(

        THRESHOLD_FILE

        .read_text(

            encoding="utf-8"

        )

        .strip()

    )



else:



    threshold = 0.35





# ============================================================

# SMS CONFIGURATION

# ============================================================



sms_configured = (

    sms_is_configured()

)





# ============================================================

# SIDEBAR

# ============================================================



st.sidebar.title(

    "System Controls"

)





# ------------------------------------------------------------

# UPDATE LIVE FORECAST

# ------------------------------------------------------------



if st.sidebar.button(

    "🔄 Update Live Forecast",

    use_container_width=True,

    type="primary",

):



    with st.spinner(

        "Getting the latest ECMWF forecast "

        "and running the Random Forest..."

    ):



        success = (

            run_prediction()

        )



    if success:



        st.sidebar.success(

            "Forecast updated successfully."

        )



        st.rerun()





st.sidebar.divider()





# ------------------------------------------------------------

# LOCATION

# ------------------------------------------------------------



st.sidebar.subheader(

    "Location"

)



st.sidebar.write(

    "📍 Matatiele"

)



st.sidebar.caption(

    "Eastern Cape / KwaZulu-Natal border region"

)





st.sidebar.divider()





# ------------------------------------------------------------

# ALERT SETTINGS

# ------------------------------------------------------------



st.sidebar.subheader(

    "Alert Settings"

)



st.sidebar.metric(

    "Storm Warning Threshold",

    f"{threshold * 100:.0f}%"

)





# ============================================================

# PRESENTATION TEST MODE

# ============================================================



st.sidebar.subheader(

    "System Testing"

)





test_mode = st.sidebar.toggle(

    "🧪 Presentation Test Mode",

    value=False,

    help=(

        "Demonstrates how the warning interface "

        "responds when the storm threshold is exceeded. "

        "It does not alter the trained model "

        "or the real live forecast."

    ),

)





if test_mode:



    st.sidebar.warning(

        "SIMULATION ACTIVE\n\n"

        "Not a live weather warning.",

        icon="🧪",

    )





# ============================================================

# SMS STATUS

# ============================================================



st.sidebar.divider()



st.sidebar.write(

    "📱 SMS Notifications"

)





if sms_configured:



    st.sidebar.success(

        "ONLINE",

        icon="✅",

    )



else:



    st.sidebar.warning(

        "NOT CONFIGURED",

        icon="⚠️",

    )





# ============================================================

# TEST SMS

# ============================================================



if sms_configured:



    if st.sidebar.button(

        "📲 Send Test SMS",

        use_container_width=True,

    ):



        with st.sidebar.spinner(

            "Sending test SMS..."

        ):



            test_sms_result = (

                send_test_sms()

            )



        if test_sms_result.get(

            "sent",

            False

        ):



            st.sidebar.success(

                test_sms_result.get(

                    "message",

                    "Test SMS sent."

                )

            )



        else:



            st.sidebar.error(

                test_sms_result.get(

                    "message",

                    "Test SMS failed."

                )

            )





st.sidebar.divider()





# ============================================================

# TECHNICAL DETAILS

# ============================================================



with st.sidebar.expander(

    "Technical Details"

):



    st.write(

        "**Algorithm:** Random Forest"

    )



    st.write(

        "**Trees:** 300"

    )



    st.write(

        "**Features:** 29"

    )



    st.write(

        "**Historical source:** ERA5"

    )



    st.write(

        "**Live source:** Open-Meteo / ECMWF"

    )



    st.write(

        "**Prediction horizon:** Next hour"

    )



    st.write(

        "**K Index:** Excluded from live model"

    )



    st.write(

        "**Research focus:** "

        "Low-connectivity environments"

    )



    st.write(

        "**Current stage:** "

        "Alpha proof-of-concept"

    )



    st.write(

        "**Future deployment:** "

        "Local sensors + edge processing"

    )





# ============================================================

# CLEAN USER-FACING HEADER

# ============================================================



st.markdown(

    "<div class='main-title'>"

    "⛈️ Matatiele Smart Resilient "

    "Storm Early Warning System"

    "</div>",

    unsafe_allow_html=True,

)





st.markdown(

    "<div class='main-subtitle'>"

    "Machine-learning based next-hour storm monitoring "

    "and early warning."

    "</div>",

    unsafe_allow_html=True,

)





# ============================================================

# SIMULATION MODE BANNER

# ============================================================



if test_mode:



    st.markdown(

        "<div class='simulation-banner'>"

        "🧪 <strong>SIMULATION MODE — "

        "NOT A LIVE WEATHER WARNING</strong>"

        "<br><br>"

        "This mode demonstrates how the system responds "

        "when the warning threshold is exceeded. "

        "The trained Random Forest model and real live "

        "forecast remain unchanged."

        "</div>",

        unsafe_allow_html=True,

    )





# ============================================================

# CHECK PREDICTION FILE

# ============================================================



if not PREDICTION_FILE.exists():



    st.warning(

        "No live prediction has been generated yet."

    )



    st.info(

        "Use Update Live Forecast in the sidebar "

        "to generate the first prediction."

    )



    st.stop()





# ============================================================

# LOAD REAL LIVE PREDICTION

# ============================================================



prediction_df = pd.read_csv(

    PREDICTION_FILE

)





if prediction_df.empty:



    st.error(

        "The live prediction file is empty."

    )



    st.stop()





latest = (

    prediction_df

    .iloc[-1]

    .copy()

)





# ============================================================

# SAVE LIVE HISTORY

# ============================================================



save_history(

    latest.to_dict()

)





# ============================================================

# TIMES

# ============================================================



forecast_time = pd.to_datetime(

    latest[

        "forecast_input_time"

    ],

    utc=True,

)





prediction_time = pd.to_datetime(

    latest[

        "prediction_for"

    ],

    utc=True,

)





forecast_time_sast = (

    forecast_time

    .to_pydatetime()

    .astimezone(

        SAST

    )

)





prediction_time_sast = (

    prediction_time

    .to_pydatetime()

    .astimezone(

        SAST

    )

)





last_updated = datetime.now(

    SAST

)





# ============================================================

# REAL LIVE VALUES

# ============================================================



real_storm_probability = float(

    latest[

        "storm_probability"

    ]

)





real_storm_prediction = int(

    latest[

        "storm_prediction"

    ]

)





real_temperature_c = float(

    latest[

        "temperature_c"

    ]

)





real_dewpoint_c = float(

    latest[

        "dewpoint_c"

    ]

)





real_pressure_msl_hpa = float(

    latest[

        "pressure_msl_hpa"

    ]

)





real_surface_pressure_hpa = float(

    latest[

        "surface_pressure_hpa"

    ]

)





real_precipitation_mm = float(

    latest[

        "precipitation_mm"

    ]

)





real_showers_mm = float(

    latest[

        "showers_mm"

    ]

)





real_cape = float(

    latest[

        "cape"

    ]

)





real_cloud_cover_percent = float(

    latest[

        "cloud_cover_percent"

    ]

)





real_wind_speed_ms = float(

    latest[

        "wind_speed_ms"

    ]

)





real_wind_gust_ms = float(

    latest[

        "wind_gust_ms"

    ]

)





# ============================================================

# DISPLAY VALUES

# ============================================================



if test_mode:



    storm_probability = 0.60

    storm_prediction = 1



    temperature_c = 23.5

    dewpoint_c = 18.4



    pressure_msl_hpa = 1005.5

    surface_pressure_hpa = 850.2



    precipitation_mm = 8.4

    showers_mm = 6.9



    cape = 1450.0



    cloud_cover_percent = 94.0



    wind_speed_ms = 9.8

    wind_gust_ms = 18.0



else:



    storm_probability = (

        real_storm_probability

    )



    storm_prediction = (

        real_storm_prediction

    )



    temperature_c = (

        real_temperature_c

    )



    dewpoint_c = (

        real_dewpoint_c

    )



    pressure_msl_hpa = (

        real_pressure_msl_hpa

    )



    surface_pressure_hpa = (

        real_surface_pressure_hpa

    )



    precipitation_mm = (

        real_precipitation_mm

    )



    showers_mm = (

        real_showers_mm

    )



    cape = (

        real_cape

    )



    cloud_cover_percent = (

        real_cloud_cover_percent

    )



    wind_speed_ms = (

        real_wind_speed_ms

    )



    wind_gust_ms = (

        real_wind_gust_ms

    )





# ============================================================

# RISK LEVEL

# ============================================================



risk_level = get_risk_level(

    storm_probability,

    threshold,

)





risk_colours = get_risk_colours(

    risk_level

)





# ============================================================
# SMS LOGIC
# ============================================================

sms_result = {
    "status": "not_required",
    "sent": False,
    "message": "Storm probability is below threshold.",
}

if test_mode:
    st.info(
        "SIMULATION ONLY - NOT A LIVE WEATHER WARNING\n\n"
        f"Simulated storm probability: {storm_probability * 100:.1f}% "
        f"(threshold: {threshold * 100:.0f}%).\n\n"
        "The simulated alert is sent automatically once per prediction hour "
        "when Presentation Test Mode is enabled."
    )
    if sms_configured:
        sms_result = send_simulated_storm_sms(
            prediction_for=latest["prediction_for"],
            storm_probability=storm_probability,
            threshold=threshold,
            location="Matatiele",
        )
        if sms_result["status"] == "sent":
            st.success(sms_result["message"])
        elif sms_result["status"] == "duplicate":
            st.info(sms_result["message"])
        else:
            st.warning(sms_result.get("message", "Simulation SMS unavailable."))
    else:
        st.warning("Twilio is not configured. Simulation SMS unavailable.")

elif real_storm_probability >= threshold:
    sms_result = send_storm_sms(
        prediction_for=latest["prediction_for"],
        storm_probability=real_storm_probability,
        threshold=threshold,
        temperature_c=real_temperature_c,
        precipitation_mm=real_precipitation_mm,
        cape=real_cape,
        wind_gust_ms=real_wind_gust_ms,
        location="Matatiele",
    )


# ============================================================

# TOP STATUS CARDS

# ============================================================



top1, top2, top3, top4 = (

    st.columns(4)

)





# ------------------------------------------------------------

# LIVE FORECAST

# ------------------------------------------------------------



with top1:



    status_card(

        title=

            "Live Forecast",



        value=

            "ONLINE",



        background=

            "#e7f7ef",



        border=

            "#67c993",



        text_colour=

            "#087f42",

    )





# ------------------------------------------------------------

# RANDOM FOREST

# ------------------------------------------------------------



with top2:



    if test_mode:



        status_card(

            title=

                "Random Forest",



            value=

                "TEST MODE",



            background=

                "#fff7d9",



            border=

                "#dfbd43",



            text_colour=

                "#9a7600",

        )



    else:



        status_card(

            title=

                "Random Forest",



            value=

                "READY",



            background=

                "#e9f4ff",



            border=

                "#79b8e8",



            text_colour=

                "#1169a7",

        )





# ------------------------------------------------------------

# CURRENT RISK LEVEL

# ------------------------------------------------------------



with top3:



    risk_display = (

        f"{risk_colours['dot']} "

        f"{risk_level}"

    )



    status_card(

        title=

            "Current Risk Level",



        value=

            risk_display,



        background=

            risk_colours[

                "background"

            ],



        border=

            risk_colours[

                "border"

            ],



        text_colour=

            risk_colours[

                "text"

            ],

    )





# ------------------------------------------------------------

# LAST UPDATED

# ------------------------------------------------------------



with top4:



    status_card(

        title=

            "Last Updated",



        value=

            last_updated.strftime(

                "%H:%M"

            ),



        background=

            "#f4f9fd",



        border=

            "#acd5ed",



        text_colour=

            "#0d507e",



        subtitle=

            "SAST",

    )





# ============================================================

# MAIN WARNING BANNER

# ============================================================



if storm_prediction == 1:



    if test_mode:



        st.error(

            "🧪 SIMULATED STORM WARNING\n\n"

            "A storm would be predicted for the next hour "

            "under these test conditions.\n\n"

            f"Simulated storm probability: "

            f"{storm_probability * 100:.1f}%\n\n"

            "This is a demonstration only and is NOT "

            "a live weather warning."

        )



    else:



        st.error(

            "⚠️ STORM WARNING\n\n"

            "Storm conditions are predicted during "

            "the next hour.\n\n"

            f"Current model probability: "

            f"{storm_probability * 100:.1f}%"

        )





elif storm_probability >= 0.20:



    st.warning(

        "🟠 MODERATE STORM RISK\n\n"

        "Atmospheric conditions are becoming "

        "more favourable for storms.\n\n"

        f"Current probability: "

        f"{storm_probability * 100:.1f}%"

    )





else:



    st.success(

        "✅ NORMAL CONDITIONS\n\n"

        "No storm is currently predicted "

        "during the next hour.\n\n"

        f"Current probability: "

        f"{storm_probability * 100:.1f}%"

    )





# ============================================================

# PRIMARY METRICS

# ============================================================



metric1, metric2, metric3, metric4 = (

    st.columns(4)

)





with metric1:



    st.metric(

        (

            "Simulated Probability"

            if test_mode

            else

            "Storm Probability"

        ),



        f"{storm_probability * 100:.1f}%"

    )





with metric2:



    st.metric(

        "Alert Threshold",

        f"{threshold * 100:.0f}%"

    )





with metric3:



    st.metric(

        "Temperature",

        f"{temperature_c:.1f} °C"

    )





with metric4:



    st.metric(

        "Wind Gust",

        f"{wind_gust_ms:.1f} m/s"

    )





# ============================================================

# NEXT-HOUR STORM RISK

# ============================================================



st.subheader(

    "Next-Hour Storm Risk"

)





risk_percent = int(

    min(

        max(

            storm_probability

            *

            100,

            0

        ),

        100

    )

)





st.progress(

    risk_percent,



    text=(

        f"{risk_level} — "

        f"{storm_probability * 100:.1f}%"

    ),

)





risk1, risk2, risk3, risk4 = (

    st.columns(4)

)





with risk1:



    st.caption(

        "🟢 LOW"

    )



    st.caption(

        "0–9%"

    )





with risk2:



    st.caption(

        "🟡 ELEVATED"

    )



    st.caption(

        "10–19%"

    )





with risk3:



    st.caption(

        "🟠 MODERATE"

    )



    st.caption(

        "20–34%"

    )





with risk4:



    st.caption(

        "🔴 WARNING"

    )



    st.caption(

        "35%+"

    )





# ============================================================

# FORECAST INFORMATION

# ============================================================



st.divider()





time1, time2, time3 = (

    st.columns(3)

)





with time1:



    st.subheader(

        "Forecast Input"

    )



    st.write(

        forecast_time_sast.strftime(

            "%d %B %Y"

        )

    )



    st.write(

        forecast_time_sast.strftime(

            "%H:%M SAST"

        )

    )





with time2:



    st.subheader(

        (

            "Simulation Valid For"

            if test_mode

            else

            "Prediction Valid For"

        )

    )



    st.write(

        prediction_time_sast.strftime(

            "%d %B %Y"

        )

    )



    st.write(

        prediction_time_sast.strftime(

            "%H:%M SAST"

        )

    )





with time3:



    st.subheader(

        "Forecast Horizon"

    )



    st.write(

        "Next 1 hour"

    )



    st.caption(

        (

            "Controlled warning demonstration"

            if test_mode

            else

            "Random Forest classification"

        )

    )





# ============================================================

# WEATHER CONDITIONS

# ============================================================



st.divider()





st.header(

    (

        "Simulated Storm Conditions"

        if test_mode

        else

        "Current Forecast Conditions"

    )

)





if test_mode:



    st.info(

        "The weather values below are predefined "

        "test values and are not from the live "

        "ECMWF forecast."

    )





weather1, weather2, weather3 = (

    st.columns(3)

)





with weather1:



    st.metric(

        "🌡️ Temperature",

        f"{temperature_c:.1f} °C"

    )





with weather2:



    st.metric(

        "💧 Dew Point",

        f"{dewpoint_c:.1f} °C"

    )





with weather3:



    st.metric(

        "☁️ Cloud Cover",

        f"{cloud_cover_percent:.0f}%"

    )





weather4, weather5, weather6 = (

    st.columns(3)

)





with weather4:



    st.metric(

        "🌧️ Precipitation",

        f"{precipitation_mm:.3f} mm"

    )





with weather5:



    st.metric(

        "⛈️ Showers",

        f"{showers_mm:.3f} mm"

    )





with weather6:



    st.metric(

        "⚡ CAPE",

        f"{cape:.1f} J/kg"

    )





weather7, weather8, weather9 = (

    st.columns(3)

)





with weather7:



    st.metric(

        "💨 Wind Speed",

        f"{wind_speed_ms:.1f} m/s"

    )





with weather8:



    st.metric(

        "🌬️ Wind Gust",

        f"{wind_gust_ms:.1f} m/s"

    )





with weather9:



    st.metric(

        "🌎 MSL Pressure",

        f"{pressure_msl_hpa:.1f} hPa"

    )





# ============================================================

# WARNING DELIVERY

# ============================================================



st.divider()





st.header(

    "Warning Delivery"

)





delivery1, delivery2, delivery3 = (

    st.columns(3)

)





# ------------------------------------------------------------

# DASHBOARD WARNING

# ------------------------------------------------------------



with delivery1:



    with st.container(

        border=True

    ):



        st.caption(

            "Dashboard Warning"

        )



        if test_mode:



            st.warning(

                "SIMULATED WARNING",

                icon="🧪"

            )



            st.caption(

                "The warning interface is "

                "being demonstrated."

            )



        else:



            st.success(

                "ACTIVE",

                icon="✅"

            )



            st.caption(

                "Visual warnings displayed "

                "automatically."

            )





# ------------------------------------------------------------

# SMS SERVICE

# ------------------------------------------------------------



with delivery2:



    with st.container(

        border=True

    ):



        st.caption(

            "SMS Service"

        )



        if sms_configured:



            st.success(

                "ONLINE",

                icon="📱"

            )



            st.caption(

                "Twilio SMS delivery configured."

            )



        else:



            st.warning(

                "NOT CONFIGURED",

                icon="⚠️"

            )



            st.caption(

                "Configure Twilio before "

                "SMS warnings can be sent."

            )





# ------------------------------------------------------------

# SMS DECISION

# ------------------------------------------------------------



with delivery3:



    with st.container(

        border=True

    ):



        st.caption(

            "Current SMS Decision"

        )



        sms_status = (

            sms_result.get(

                "status",

                "unknown"

            )

        )



        if sms_status == "simulation":



            st.warning(

                "SIMULATION ONLY",

                icon="🧪"

            )



            st.caption(

                "A real warning SMS is not "

                "automatically sent during "

                "presentation test mode."

            )





        elif sms_status == "sent":



            st.success(

                "SMS SENT",

                icon="✅"

            )



            st.caption(

                sms_result.get(

                    "message",

                    ""

                )

            )





        elif sms_status == "duplicate":



            st.info(

                "ALREADY SENT",

                icon="ℹ️"

            )



            st.caption(

                "Duplicate warning prevented."

            )





        elif sms_status == "failed":



            st.error(

                "SEND FAILED",

                icon="❌"

            )



            st.caption(

                sms_result.get(

                    "message",

                    ""

                )

            )





        elif sms_status == "not_configured":



            st.warning(

                "NOT CONFIGURED",

                icon="⚠️"

            )





        else:



            st.success(

                "NO SMS REQUIRED",

                icon="✅"

            )



            st.caption(

                "Storm probability is "

                "below threshold."

            )





# ============================================================

# LIVE PREDICTION HISTORY

# ============================================================



st.divider()





st.header(

    (

        "Live Prediction History"

        if test_mode

        else

        "Prediction History"

    )

)





if test_mode:



    st.info(

        "The records below are genuine live Random Forest "

        "predictions only. The simulated 60% warning is "

        "not added to this history."

    )





if HISTORY_FILE.exists():



    history = pd.read_csv(

        HISTORY_FILE

    )





    if not history.empty:



        history[

            "prediction_for"

        ] = pd.to_datetime(

            history[

                "prediction_for"

            ],

            errors="coerce",

            utc=True,

        )





        history[

            "storm_probability_percent"

        ] = (

            pd.to_numeric(

                history[

                    "storm_probability"

                ],

                errors="coerce",

            )

            *

            100

        )





        history = history.dropna(

            subset=[

                "prediction_for",

                "storm_probability_percent",

            ]

        )





        # ====================================================

        # HISTORY GRAPH

        # ====================================================



        if len(history) >= 2:



            chart_data = (

                history[

                    [

                        "prediction_for",

                        "storm_probability_percent",

                    ]

                ]

                .sort_values(

                    "prediction_for"

                )

                .copy()

            )





            threshold_percent = (

                threshold

                *

                100

            )





            probability_chart = (

                alt.Chart(

                    chart_data

                )

                .mark_line(

                    point=True,

                    size=3,

                    color="#0d78c7",

                )

                .encode(

                    x=alt.X(

                        "prediction_for:T",

                        title=

                            "Prediction Time",

                    ),



                    y=alt.Y(

                        "storm_probability_percent:Q",

                        title=

                            "Storm Probability (%)",



                        scale=

                            alt.Scale(

                                domain=[

                                    0,

                                    100,

                                ]

                            ),

                    ),



                    tooltip=[

                        alt.Tooltip(

                            "prediction_for:T",

                            title=

                                "Prediction Time",

                        ),



                        alt.Tooltip(

                            "storm_probability_percent:Q",

                            title=

                                "Storm Probability (%)",

                            format=".1f",

                        ),

                    ],

                )

            )





            threshold_data = (

                pd.DataFrame(

                    {

                        "threshold": [

                            threshold_percent

                        ]

                    }

                )

            )





            threshold_chart = (

                alt.Chart(

                    threshold_data

                )

                .mark_rule(

                    color="#c62828",

                    strokeDash=[

                        8,

                        5,

                    ],

                    size=2,

                )

                .encode(

                    y=

                        "threshold:Q"

                )

            )





            threshold_label_data = (

                pd.DataFrame(

                    {

                        "threshold": [

                            threshold_percent

                        ],



                        "label": [

                            (

                                f"Warning Threshold "

                                f"{threshold_percent:.0f}%"

                            )

                        ],

                    }

                )

            )





            threshold_label = (

                alt.Chart(

                    threshold_label_data

                )

                .mark_text(

                    align=

                        "left",



                    baseline=

                        "bottom",



                    dx=

                        5,



                    dy=

                        -5,



                    color=

                        "#a91d2d",

                )

                .encode(

                    y=

                        "threshold:Q",



                    text=

                        "label:N",

                )

            )





            final_chart = (

                probability_chart

                +

                threshold_chart

                +

                threshold_label

            ).properties(

                height=

                    350

            )





            st.altair_chart(

                final_chart,

                use_container_width=True,

            )





        else:



            st.info(

                "Prediction history graph will appear "

                "after multiple live updates."

            )





        # ====================================================

        # HISTORY TABLE

        # ====================================================



        required_history_columns = [

            "prediction_for",

            "storm_probability_percent",

            "warning_status",

            "temperature_c",

            "cape",

            "wind_gust_ms",

        ]





        available_history_columns = [

            column

            for column

            in required_history_columns

            if column

            in history.columns

        ]





        history_display = (

            history[

                available_history_columns

            ]

            .copy()

        )





        if (

            "prediction_for"

            in history_display.columns

        ):



            history_display[

                "prediction_for"

            ] = (

                history_display[

                    "prediction_for"

                ]

                .dt

                .tz_convert(

                    "Africa/Johannesburg"

                )

            )





            history_display[

                "prediction_for"

            ] = (

                history_display[

                    "prediction_for"

                ]

                .dt

                .strftime(

                    "%d %b %Y %H:%M"

                )

            )





            history_display = (

                history_display

                .sort_values(

                    "prediction_for",

                    ascending=False,

                )

                .head(20)

            )





        history_display = (

            history_display

            .rename(

                columns={

                    "prediction_for":

                        "Prediction Time (SAST)",



                    "storm_probability_percent":

                        "Storm Probability (%)",



                    "warning_status":

                        (

                            "Live Model Status"

                            if test_mode

                            else

                            "Status"

                        ),



                    "temperature_c":

                        "Temperature (°C)",



                    "cape":

                        "CAPE",



                    "wind_gust_ms":

                        "Wind Gust (m/s)",

                }

            )

        )





        st.dataframe(

            history_display,

            use_container_width=True,

            hide_index=True,

        )





else:



    st.info(

        "Prediction history will appear "

        "after forecasts are recorded."

    )





# ============================================================

# SMS ALERT HISTORY

# ============================================================



if SMS_LOG_FILE.exists():



    st.divider()





    with st.expander(

        "SMS Alert History"

    ):



        try:



            sms_log = pd.read_csv(

                SMS_LOG_FILE

            )





            if sms_log.empty:



                st.info(

                    "No SMS messages logged yet."

                )





            else:



                safe_columns = [

                    column

                    for column in [

                        "logged_at_utc",

                        "prediction_key",

                        "storm_probability",

                        "status",

                        "message_sid",

                        "error",

                    ]

                    if column

                    in sms_log.columns

                ]





                st.dataframe(

                    sms_log[

                        safe_columns

                    ]

                    .tail(20),



                    use_container_width=True,

                    hide_index=True,

                )





        except Exception as error:



            st.warning(

                f"Could not read SMS log: "

                f"{error}"

            )





# ============================================================

# ABOUT THIS SYSTEM

# ============================================================



st.divider()





with st.expander(

    "About this system"

):



    st.markdown(

        """

        ### Research Project



        **Smart Resilient Storm Early Warning System for

        Low Connectivity Environments: A Case of Matatiele**



        The current system is an **Alpha proof-of-concept**.



        Its purpose is to validate the complete software

        workflow:



        **Live forecast → feature preparation → Random Forest

        → storm probability → risk decision → dashboard → SMS**



        ---



        ### Current Alpha



        The current Alpha uses:



        - historical ERA5 data for model development;

        - Open-Meteo / ECMWF for live forecast input;

        - a Random Forest classifier;

        - a next-hour prediction horizon;

        - a 35% operational warning threshold;

        - a Streamlit dashboard;

        - Twilio SMS warning delivery.



        ---



        ### Low-Connectivity Research Goal



        The full research concept is intended for environments

        where continuous internet connectivity may not always

        be available.



        With suitable hardware and funding, future deployment

        could include:



        - local temperature sensors;

        - humidity sensors;

        - rainfall sensors;

        - atmospheric-pressure sensors;

        - wind-speed and wind-direction sensors;

        - a Raspberry Pi or similar edge device;

        - local processing of weather observations;

        - local execution of the trained Random Forest;

        - local storage during connectivity interruptions;

        - GSM/SMS warning delivery;

        - cloud synchronisation when connectivity returns.



        The future architecture could therefore operate as:



        **Local Weather Sensors  

        ↓  

        Edge Device  

        ↓  

        Local Feature Processing  

        ↓  

        Random Forest  

        ↓  

        Storm Probability  

        ↓  

        Warning Decision  

        ↓  

        Local Dashboard / GSM-SMS Warning**



        The current Alpha still requires internet connectivity

        for Open-Meteo and Twilio. It therefore demonstrates

        the core intelligent warning workflow rather than

        claiming to be fully offline.



        ---



        ### Presentation Test Mode



        Presentation Test Mode is used only to demonstrate

        the warning interface when no real storm is occurring.



        It does not:



        - retrain the Random Forest;

        - overwrite the live forecast;

        - change the genuine prediction history;

        - represent a real weather warning.



        ---



        ### Disclaimer



        This system is an academic Alpha prototype and does

        not replace official meteorological or

        disaster-management warnings.

        """

    )





# ============================================================

# FOOTER

# ============================================================



st.divider()





st.caption(

    "Matatiele Smart Resilient Storm Early Warning System "

    "• Random Forest Machine Learning "

    "• Next-Hour Storm Prediction "

    "• SMS Early Warning "

    "• Alpha Prototype"

)