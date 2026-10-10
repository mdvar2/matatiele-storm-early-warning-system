from datetime import datetime, timezone, timedelta
from pathlib import Path

from sms_alert import (
    sms_is_configured,
    send_storm_sms,
)


# ============================================================
# AUTOMATIC WARNING PIPELINE VALIDATION
# ============================================================

BASE_DIR = Path(__file__).resolve().parent

print("=" * 70)
print("MATATIELE AUTOMATIC WARNING PIPELINE TEST")
print("=" * 70)

print()
print("IMPORTANT:")
print("This is a CONTROLLED SIMULATION.")
print("It does not change the Random Forest model.")
print("It does not change the live forecast data.")
print("It does not represent a real storm warning.")
print()


# ============================================================
# CHECK SMS CONFIGURATION
# ============================================================

print("=" * 70)
print("CHECKING SMS CONFIGURATION")
print("=" * 70)

if not sms_is_configured():

    print()
    print("ERROR:")
    print("Twilio SMS configuration was not detected.")
    print()
    print("Run this script from the same PowerShell")
    print("session where your Twilio variables are set.")

    raise SystemExit(1)


print()
print("SMS configuration: OK")


# ============================================================
# SIMULATED STORM CONDITIONS
# ============================================================

print()
print("=" * 70)
print("SIMULATED STORM CONDITIONS")
print("=" * 70)


SIMULATED_PROBABILITY = 0.60

WARNING_THRESHOLD = 0.35

SIMULATED_TEMPERATURE = 23.5

SIMULATED_PRECIPITATION = 8.4

SIMULATED_CAPE = 1450.0

SIMULATED_WIND_GUST = 18.0


# Use a unique prediction hour for this test.
#
# We use a future UTC hour so this test does not interfere
# with the current real forecast's duplicate-warning record.

now_utc = datetime.now(
    timezone.utc
)

test_prediction_time = (
    now_utc
    +
    timedelta(hours=24)
).replace(
    minute=0,
    second=0,
    microsecond=0
)


print()
print(
    "Simulated storm probability:",
    f"{SIMULATED_PROBABILITY * 100:.1f}%"
)

print(
    "Warning threshold:",
    f"{WARNING_THRESHOLD * 100:.1f}%"
)

print(
    "Simulated prediction time:",
    test_prediction_time.isoformat()
)

print(
    "Temperature:",
    f"{SIMULATED_TEMPERATURE:.1f} C"
)

print(
    "Precipitation:",
    f"{SIMULATED_PRECIPITATION:.1f} mm"
)

print(
    "CAPE:",
    f"{SIMULATED_CAPE:.0f} J/kg"
)

print(
    "Wind gust:",
    f"{SIMULATED_WIND_GUST:.1f} m/s"
)


# ============================================================
# VERIFY THRESHOLD LOGIC
# ============================================================

print()
print("=" * 70)
print("CHECKING WARNING DECISION")
print("=" * 70)


if (
    SIMULATED_PROBABILITY
    >=
    WARNING_THRESHOLD
):

    print()
    print("Prediction: STORM WARNING")
    print()
    print(
        "Reason:",
        f"{SIMULATED_PROBABILITY * 100:.1f}%"
        " >= "
        f"{WARNING_THRESHOLD * 100:.1f}%"
    )

else:

    print()
    print("ERROR:")
    print(
        "Simulation probability did not reach "
        "the warning threshold."
    )

    raise SystemExit(1)


# ============================================================
# FIRST AUTOMATIC SMS ATTEMPT
# ============================================================

print()
print("=" * 70)
print("FIRST AUTOMATIC SMS ATTEMPT")
print("=" * 70)

print()
print(
    "The system should SEND one warning SMS now."
)


first_result = send_storm_sms(

    prediction_for=
        test_prediction_time.isoformat(),

    storm_probability=
        SIMULATED_PROBABILITY,

    threshold=
        WARNING_THRESHOLD,

    temperature_c=
        SIMULATED_TEMPERATURE,

    precipitation_mm=
        SIMULATED_PRECIPITATION,

    cape=
        SIMULATED_CAPE,

    wind_gust_ms=
        SIMULATED_WIND_GUST,

    location=
        "Matatiele - CONTROLLED TEST",
)


print()
print(
    "Status:",
    first_result.get(
        "status"
    )
)

print(
    "Sent:",
    first_result.get(
        "sent"
    )
)

print(
    "Message:",
    first_result.get(
        "message"
    )
)


# ============================================================
# SECOND AUTOMATIC SMS ATTEMPT
# ============================================================

print()
print("=" * 70)
print("DUPLICATE-PROTECTION TEST")
print("=" * 70)

print()
print(
    "The system will now try to send the exact same "
    "warning again."
)

print()
print(
    "EXPECTED RESULT:"
)

print(
    "The second message must NOT be sent."
)


second_result = send_storm_sms(

    prediction_for=
        test_prediction_time.isoformat(),

    storm_probability=
        SIMULATED_PROBABILITY,

    threshold=
        WARNING_THRESHOLD,

    temperature_c=
        SIMULATED_TEMPERATURE,

    precipitation_mm=
        SIMULATED_PRECIPITATION,

    cape=
        SIMULATED_CAPE,

    wind_gust_ms=
        SIMULATED_WIND_GUST,

    location=
        "Matatiele - CONTROLLED TEST",
)


print()
print(
    "Status:",
    second_result.get(
        "status"
    )
)

print(
    "Sent:",
    second_result.get(
        "sent"
    )
)

print(
    "Message:",
    second_result.get(
        "message"
    )
)


# ============================================================
# VALIDATION RESULT
# ============================================================

print()
print("=" * 70)
print("VALIDATION RESULT")
print("=" * 70)


first_sent = (
    first_result.get(
        "status"
    )
    ==
    "sent"
)


duplicate_blocked = (
    second_result.get(
        "status"
    )
    ==
    "duplicate"
)


if (
    first_sent
    and
    duplicate_blocked
):

    print()
    print("SUCCESS")
    print()
    print(
        "Automatic SMS warning delivery works."
    )

    print(
        "Duplicate-warning protection works."
    )

    print()
    print(
        "The automatic notification pipeline "
        "passed the test."
    )

else:

    print()
    print("TEST NOT FULLY PASSED")
    print()

    print(
        "First SMS sent:",
        first_sent
    )

    print(
        "Duplicate blocked:",
        duplicate_blocked
    )

    print()
    print(
        "Review the results above before continuing."
    )


print()
print("=" * 70)
print("TEST COMPLETE")
print("=" * 70)

print()
print(
    "Your real Random Forest prediction "
    "and live forecast files were not modified."
)