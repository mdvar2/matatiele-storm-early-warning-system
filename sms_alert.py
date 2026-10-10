"""Twilio SMS alerts for the Matatiele storm early-warning research prototype.

Requires TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN, TWILIO_FROM_NUMBER,
and ALERT_TO_NUMBERS (comma-separated E.164 numbers). Dashboard sessions use
Streamlit secrets with environment fallback; CLI workers use the environment.

Twilio accepting a message does NOT prove delivery. A repeat warning attempt
checks its recorded SID; ordinary dashboard reruns do not poll delivery.
Use Twilio's console as the final reference.
"""

from pathlib import Path
from datetime import datetime, timezone, timedelta
from zoneinfo import ZoneInfo
import csv
import os
import math
import re
import threading
from app_config import get_setting

_SEND_LOCK = threading.RLock()
_E164 = re.compile(r'\+[1-9][0-9]{7,14}')

BASE_DIR = Path(__file__).resolve().parent
MODEL_DIR = BASE_DIR / "outputs" / "model_live"
MODEL_DIR.mkdir(parents=True, exist_ok=True)
SMS_LOG_FILE = MODEL_DIR / "sms_alert_log.csv"
REQUIRED_ENV_VARS = (
    "TWILIO_ACCOUNT_SID", "TWILIO_AUTH_TOKEN",
    "TWILIO_FROM_NUMBER", "ALERT_TO_NUMBERS",
)
LOG_FIELDS = (
    "logged_at_utc", "prediction_key", "recipient", "storm_probability",
    "status", "message_sid", "error",
)


def sms_is_configured():
    if not all(get_setting(key) for key in REQUIRED_ENV_VARS):
        return False
    try:
        return bool(_get_recipients()) and bool(_E164.fullmatch(get_setting('TWILIO_FROM_NUMBER')))
    except ValueError:
        return False


def _get_recipients():
    recipients = list(dict.fromkeys(
        value.strip() for value in get_setting("ALERT_TO_NUMBERS").split(",")
        if value.strip()
    ))
    if any(not _E164.fullmatch(value) for value in recipients):
        raise ValueError('SMS recipients must use E.164 format; configuration rejected.')
    return recipients


def _normalise_prediction_key(prediction_for):
    try:
        parsed = datetime.fromisoformat(str(prediction_for).replace("Z", "+00:00"))
        if parsed.tzinfo is None:
            # Preserve existing project behavior for timezone-naive values.
            parsed = parsed.replace(tzinfo=timezone.utc)
        return parsed.astimezone(timezone.utc).replace(
            minute=0, second=0, microsecond=0
        ).isoformat()
    except (ValueError, TypeError):
        return str(prediction_for).strip()


def _read_log():
    if not SMS_LOG_FILE.exists():
        return []
    try:
        with SMS_LOG_FILE.open("r", encoding="utf-8", newline="") as handle:
            reader = csv.DictReader(handle, strict=True)
            if not set(LOG_FIELDS).issubset(reader.fieldnames or []):
                raise OSError('SMS history schema invalid; manual review required.')
            rows = list(reader)
            if any(None in row or any(row.get(field) is None for field in LOG_FIELDS) for row in rows):
                raise OSError('SMS history incomplete; manual review required.')
            return rows
    except csv.Error as exc:
        raise OSError('SMS history unreadable; manual review required.') from exc


def _log_attempt(prediction_key, recipient, probability, status,
                 message_sid="", error=""):
    needs_header = not SMS_LOG_FILE.exists() or SMS_LOG_FILE.stat().st_size == 0
    with SMS_LOG_FILE.open("a", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=LOG_FIELDS)
        if needs_header:
            writer.writeheader()
        writer.writerow({
            "logged_at_utc": datetime.now(timezone.utc).isoformat(),
            "prediction_key": prediction_key,
            "recipient": recipient,
            "storm_probability": "" if probability is None else f"{float(probability):.6f}",
            "status": status,
            "message_sid": message_sid,
            "error": error,
        })


def _create_twilio_client():
    if not sms_is_configured():
        return None
    try:
        from twilio.rest import Client
        return Client(
            get_setting("TWILIO_ACCOUNT_SID"),
            get_setting("TWILIO_AUTH_TOKEN"),
        )
    except (ImportError, ValueError):
        return None


def _latest_attempt(prediction_key, recipient):
    for row in reversed(_read_log()):
        if row.get("prediction_key") == prediction_key and row.get("recipient") == recipient:
            return row
    return None


def _delivery_state(client, prediction_key, recipient, probability):
    """Return latest known status, optionally refreshing it from Twilio.

    A previously failed/undelivered message is retryable. Pending messages
    are not retried, avoiding duplicate sends on Streamlit reruns.
    """
    row = _latest_attempt(prediction_key, recipient)
    if row is None:
        return None
    status = (row.get("status") or "").lower()
    sid = (row.get("message_sid") or "").strip()
    if status in {"failed", "undelivered", "canceled"}:
        return status
    if status == "delivered":
        return status
    if not sid:
        return status
    try:
        message = client.messages(sid).fetch()
        remote_status = str(getattr(message, "status", status)).lower()
        if remote_status != status:
            code = getattr(message, "error_code", None)
            _log_attempt(
                prediction_key, recipient, probability, remote_status,
                message_sid=sid,
                error=str(code) if code is not None else "",
            )
        return remote_status
    except Exception:
        # If Twilio cannot be reached, do not risk resending an accepted SMS.
        return status


def _already_sent(prediction_key, recipient):
    """Compatibility helper: submitted/pending/delivered count as attempted."""
    row = _latest_attempt(prediction_key, recipient)
    if row is None:
        return False
    return (row.get("status") or "").lower() not in {
        "failed", "undelivered", "canceled", "test_failed"
    }


def _send_warning(prediction_key, probability, body, *, duplicate_label):
    # Serialize Streamlit sessions within this process. Separate processes still
    # require the worker's GitHub concurrency group / durable reservation.
    with _SEND_LOCK:
        return _send_warning_locked(prediction_key, probability, body, duplicate_label=duplicate_label)


def _send_warning_locked(prediction_key, probability, body, *, duplicate_label):
    if not sms_is_configured():
        return {"status": "not_configured", "sent": False,
                "message": "Twilio SMS environment variables are not configured."}
    client = _create_twilio_client()
    if client is None:
        return {"status": "failed", "sent": False,
                "message": "Twilio client unavailable. Install the twilio package."}
    recipients = _get_recipients()
    if not recipients:
        return {"status": "not_configured", "sent": False,
                "message": "No SMS recipients configured."}

    submitted = 0
    duplicates = 0
    errors = []
    for recipient in recipients:
        try:
            current_status = _delivery_state(client, prediction_key, recipient, probability)
        except OSError:
            return {'status':'failed','sent':False,
                    'message':'SMS history unavailable; submission stopped. Manual review required.'}
        if current_status not in (None, "failed", "undelivered", "canceled", "test_failed"):
            duplicates += 1
            continue
        try:
            # Commit intent BEFORE the provider call. A timeout or interrupted
            # response may have accepted an SMS; never automatically resend it.
            _log_attempt(prediction_key, recipient, probability, 'reserved')
        except OSError:
            return {'status':'failed','sent':False,
                    'message':'SMS reservation could not be saved; submission stopped.'}
        try:
            message = client.messages.create(
                body=body,
                from_=get_setting("TWILIO_FROM_NUMBER"),
                to=recipient,
            )
            sid = str(getattr(message, "sid", ""))
            if not sid:
                raise RuntimeError('Provider acceptance cannot be identified; manual review required.')
            status = str(getattr(message, "status", "queued") or "queued").lower()
            if status not in {'accepted','scheduled','queued','sending','sent','delivered','failed','undelivered','canceled'}:
                raise RuntimeError('Unrecognised provider response; manual review required.')
            _log_attempt(prediction_key, recipient, probability, status, message_sid=sid)
            if status in {"failed", "undelivered", "canceled"}:
                errors.append(f"Twilio reported {status} for recipient.")
            else:
                submitted += 1
        except Exception as exc:
            http_status = getattr(exc, 'status', None)
            definite_rejection = isinstance(http_status, int) and 400 <= http_status < 500 and http_status != 408
            status = 'failed' if definite_rejection else 'submission_unknown'
            error = 'Provider rejected request.' if definite_rejection else 'Submission outcome uncertain; review Twilio before retry.'
            errors.append(error)
            try:
                _log_attempt(prediction_key, recipient, probability, status, error=error)
            except OSError:
                # The pre-submission reservation remains and blocks a retry.
                pass

    if submitted and errors:
        return {"status": "partial", "sent": False, "submitted": submitted,
                "failed_or_uncertain": len(errors), "duplicates": duplicates,
                "message": f"{duplicate_label} submitted to {submitted} of {len(recipients)} recipient(s); {len(errors)} failed or uncertain. Manual review required. Delivery not yet confirmed."}
    if submitted:
        return {"status": "sent", "sent": True,
                "message": f"{duplicate_label} submitted to {submitted} recipient(s). Delivery not yet confirmed."}
    if duplicates == len(recipients):
        return {"status": "duplicate", "sent": False,
                "message": f"{duplicate_label} already submitted for this prediction hour."}
    return {"status": "failed", "sent": False,
            "message": errors[0] if errors else "SMS could not be submitted."}


def _build_warning_message(location: str, prediction_for: object, storm_probability: float,
                           threshold: float, temperature_c: float, precipitation_mm: float,
                           cape: float, wind_gust_ms: float) -> str:
    """Compact real model alert; avoid unsupported claims of a certain storm."""
    probability = round(float(storm_probability) * 100)
    end = datetime.fromisoformat(str(prediction_for).replace('Z', '+00:00'))
    if end.tzinfo is None:
        end = end.replace(tzinfo=timezone.utc)  # Existing UTC CSV convention.
    end = end.astimezone(ZoneInfo('Africa/Johannesburg'))
    start = end - timedelta(hours=1)
    period = (f'{start:%d %b %H:%M}-{end:%H:%M}' if start.date() == end.date()
              else f'{start:%d %b %H:%M}-{end:%d %b %H:%M}')
    # Short ASCII text helps keep the message within trial-account limits.
    return (
        f"MATATIELE MODEL ALERT: {period} SAST. Storm risk {probability}%. "
        "If severe weather develops, stay indoors. Avoid lightning/flooded roads. Check SAWS."
    )


def send_storm_sms(prediction_for: object, storm_probability: float, threshold: float = 0.35,
                   temperature_c: float = 0.0, precipitation_mm: float = 0.0,
                   cape: float = 0.0, wind_gust_ms: float = 0.0,
                   location: str = "Matatiele"):
    """Submit a real model-based warning only when the threshold is reached."""
    try:
        probability, selected_threshold = float(storm_probability), float(threshold)
        if not math.isfinite(probability) or not 0 <= probability <= 1 or not math.isclose(selected_threshold,.35,rel_tol=0,abs_tol=1e-9):
            raise ValueError('Invalid probability or threshold')
        target = datetime.fromisoformat(str(prediction_for).replace('Z','+00:00'))
        if target.minute or target.second or target.microsecond:
            raise ValueError('Target must be an hourly endpoint')
        if location.strip().casefold() != 'matatiele':
            raise ValueError('Only Matatiele model outputs are supported')
    except (ValueError,TypeError,OverflowError,AttributeError):
        return {'status':'failed','sent':False,'message':'Invalid Matatiele model prediction; no SMS submitted.'}
    if probability < selected_threshold:
        return {"status": "not_required", "sent": False,
                "message": "Storm probability is below the warning threshold."}
    key = "REAL-SHORT-V1-" + _normalise_prediction_key(prediction_for)
    body = _build_warning_message(
        location, prediction_for, storm_probability, threshold,
        temperature_c, precipitation_mm, cape, wind_gust_ms,
    )
    return _send_warning(key, storm_probability, body, duplicate_label="Storm warning")


def send_test_sms():
    """Manual connectivity test; deliberately different from a weather alert."""
    key = "TEST-" + datetime.now(timezone.utc).isoformat()
    body = "MATATIELE SMS TEST. Notification service check only. NO WEATHER WARNING."
    result = _send_warning(key, None, body, duplicate_label="Test SMS")
    if result["status"] == "sent":
        result["status"] = "test_sent"  # Dashboard compatibility.
    return result


def send_simulated_storm_sms(prediction_for, storm_probability=0.60,
                             threshold=0.35, location="Matatiele"):
    """Automatic, clearly labelled research simulation warning."""
    if float(storm_probability) < float(threshold):
        return {"status": "not_required", "sent": False,
                "message": "Simulated probability below threshold."}
    key = "SIMULATION-SHORT-V2-" + _normalise_prediction_key(prediction_for)
    body = (
        f"TEST ONLY - MATATIELE. Storm risk {float(storm_probability) * 100:.0f}%. "
        "Stay indoors. Avoid trees and flooded roads. "
        "Check SAWS. NOT A REAL WARNING."
    )
    return _send_warning(key, storm_probability, body,
                         duplicate_label="Simulated warning")
