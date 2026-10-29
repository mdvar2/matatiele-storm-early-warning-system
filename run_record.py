"""Sanitised operational run records for the scheduled worker (monitoring only).

Standard library only, so a missing third-party package can never stop the
worker from importing it. Nothing here sends SMS, changes predictions or
touches the duplicate-prevention ledger; every public function is safe to call
from monitoring code and never raises.

Records contain enumerated statuses, timestamps, the genuine model probability
and the worker's own fixed diagnostic messages. They must never contain phone
numbers, message bodies, provider message identifiers, tokens or environment
variable values; sanitise_record() enforces this before anything is written.
"""
import json
import math
import os
import re
import tempfile
from datetime import datetime, timezone
from pathlib import Path

SCHEMA_VERSION = 1
NOT_ATTEMPTED = 'not_attempted'
NOT_APPLICABLE = 'not_applicable'
UNKNOWN = 'unknown'

TRIGGER_SOURCES = ('github_schedule', 'external_scheduler', 'manual', 'local', 'unknown')

ERROR_CATEGORIES = (
    'none', 'configuration_failure', 'forecast_retrieval_failure', 'invalid_forecast_data',
    'stale_forecast', 'model_loading_failure', 'inference_failure', 'prediction_output_failure',
    'invalid_model_output', 'pipeline_timeout', 'duplicate_prevention_failure',
    'sms_provider_failure', 'ledger_report_failure', 'unexpected_internal_error',
)

# Field -> allowed types. Anything else is dropped before a record is written.
SCHEMA = {
    'schema_version': int, 'record_type': str,
    'started_utc': str, 'finished_utc': str, 'duration_seconds': float,
    'worker_exit_code': int, 'outcome': str,
    'mode': str, 'trigger': str, 'workflow_run_id': str, 'workflow_run_number': str,
    'workflow_run_attempt': str, 'commit': str, 'scheduled_slot_utc': str,
    'trigger_source': str, 'dispatch_delay_seconds': float, 'reservation_lock': str,
    'lock_label_permission': str, 'run_status_permission': str,
    'model_loading': str, 'forecast_retrieval': str, 'forecast_http_status': int,
    'forecast_response_validation': str, 'model_inference': str, 'prediction_output': str,
    'forecast_retrieved_utc': str, 'forecast_input_utc': str, 'prediction_target_utc': str,
    'forecast_freshness_seconds': float, 'freshness_status': str,
    'prediction_validation': str, 'storm_probability': float, 'unvalidated_probability': float,
    'warning_threshold': float, 'warning_decision': str,
    'duplicate_prevention': str, 'ledger_issue_number': int,
    'sms_submission': str, 'sms_note': str, 'ledger_report': str,
    'error_category': str, 'error_detail': str, 'error_message': str, 'exception_type': str,
}

_SENSITIVE_ENV = ('TWILIO_ACCOUNT_SID', 'TWILIO_AUTH_TOKEN', 'TWILIO_FROM_NUMBER', 'ALERT_TO_NUMBERS',
                  'GH_TOKEN', 'GITHUB_TOKEN', 'ADMIN_PASSWORD')
_PATTERNS = (
    re.compile(r'\b(?:AC|SM|MM|MG|PN|SK)[0-9a-fA-F]{32}\b'),          # Twilio identifiers
    re.compile(r'\b(?:gh[pousr]_[A-Za-z0-9]{16,}|github_pat_[A-Za-z0-9_]{16,})\b'),  # GitHub tokens
    re.compile(r'(?i)\bbearer\s+[A-Za-z0-9._\-]{8,}'),
    re.compile(r'\+\d[\d \-]{6,}\d'),                                   # international numbers
    re.compile(r'(?<![\d.:\-])\d{9,15}(?![\d.:\-])'),                   # bare long digit runs
)
_MAX_TEXT = 200


def utc_now_iso():
    return datetime.now(timezone.utc).isoformat()


def sanitise_text(value):
    """Return text with secrets, identifiers and numbers redacted; never raises."""
    try:
        text = str(value)
        for name in _SENSITIVE_ENV:
            for secret in os.environ.get(name, '').split(','):
                secret = secret.strip()
                if len(secret) >= 4:
                    text = text.replace(secret, '[REDACTED]')
        for pattern in _PATTERNS:
            text = pattern.sub('[REDACTED]', text)
        text = ''.join(ch if ch.isprintable() else ' ' for ch in text)
        return text[:_MAX_TEXT]
    except Exception:
        return '[UNPRINTABLE]'


def trigger_source(environ):
    """Who started the run: explicit RUN_TRIGGER_SOURCE if valid, else derived from the event."""
    explicit = (environ.get('RUN_TRIGGER_SOURCE') or '').strip()
    if explicit in TRIGGER_SOURCES:
        return explicit
    event = (environ.get('GITHUB_EVENT_NAME') or '').strip()
    if event == 'schedule':
        return 'github_schedule'
    if event == 'workflow_dispatch':
        return 'manual'
    return 'local' if not event else 'unknown'


def scheduled_slot(environ):
    """Intended UTC slot from the external scheduler, strictly validated; never guessed."""
    raw = (environ.get('RUN_SCHEDULED_FOR') or '').strip()
    if not raw:
        return 'not_available', None
    if not re.fullmatch(r'\d{4}-\d{2}-\d{2}T\d{2}:\d{2}(?::\d{2})?Z', raw):
        return 'invalid', None
    try:
        slot = datetime.fromisoformat(raw.replace('Z', '+00:00'))
    except ValueError:
        return 'invalid', None
    return slot.isoformat(), slot


def new_record(environ=None):
    """Initial record: every stage explicitly not attempted until it runs."""
    env = os.environ if environ is None else environ
    started = datetime.now(timezone.utc)
    slot_text, slot = scheduled_slot(env)
    return {
        'schema_version': SCHEMA_VERSION, 'record_type': 'worker_run',
        'started_utc': started.isoformat(), 'finished_utc': None, 'duration_seconds': None,
        'trigger_source': trigger_source(env),
        'dispatch_delay_seconds': round((started - slot).total_seconds(), 1) if slot else None,
        'reservation_lock': NOT_ATTEMPTED,
        'worker_exit_code': None, 'outcome': UNKNOWN,
        'mode': UNKNOWN,
        'trigger': env.get('GITHUB_EVENT_NAME') or 'local',
        'workflow_run_id': env.get('GITHUB_RUN_ID') or NOT_APPLICABLE,
        'workflow_run_number': env.get('GITHUB_RUN_NUMBER') or NOT_APPLICABLE,
        'workflow_run_attempt': env.get('GITHUB_RUN_ATTEMPT') or NOT_APPLICABLE,
        'commit': (env.get('GITHUB_SHA') or '')[:7] or NOT_APPLICABLE,
        # GitHub does not expose the cron slot; an external scheduler may supply RUN_SCHEDULED_FOR.
        'scheduled_slot_utc': slot_text,
        'model_loading': NOT_ATTEMPTED, 'forecast_retrieval': NOT_ATTEMPTED,
        'forecast_http_status': None, 'forecast_response_validation': NOT_ATTEMPTED,
        'model_inference': NOT_ATTEMPTED, 'prediction_output': NOT_ATTEMPTED,
        'forecast_retrieved_utc': None, 'forecast_input_utc': None, 'prediction_target_utc': None,
        'forecast_freshness_seconds': None, 'freshness_status': NOT_ATTEMPTED,
        'prediction_validation': NOT_ATTEMPTED,
        'storm_probability': None, 'unvalidated_probability': None,
        'warning_threshold': None, 'warning_decision': 'not_evaluated',
        'duplicate_prevention': NOT_ATTEMPTED, 'ledger_issue_number': None,
        'sms_submission': NOT_ATTEMPTED, 'sms_note': '', 'ledger_report': NOT_ATTEMPTED,
        'error_category': 'none', 'error_detail': '', 'error_message': '', 'exception_type': '',
    }


# Ordered stage markers printed by 12_live_forecast_and_predict.py (stdout).
_STAGE_FILES_OK = 'All live-compatible model files found.'
_STAGE_MODEL_OK = 'Random Forest loaded successfully.'
_STAGE_REQUEST_FAILED = 'Live forecast request failed.'
_STAGE_DOWNLOADED = 'Live forecast downloaded successfully.'
_STAGE_FEATURES = 'Features prepared for model'
_STAGE_PREDICTED = 'LIVE NEXT-HOUR STORM PREDICTION'
_STAGE_SAVED = 'Prediction saved to:'

# Fixed messages raised by script 12 -> (detail code, category). Matched as substrings.
_KNOWN_MESSAGES = (
    ('Required file not found', 'model_artefact_missing', 'model_loading_failure'),
    ('Open-Meteo error', 'provider_error_response', 'forecast_retrieval_failure'),
    ('No hourly forecast data was returned', 'hourly_block_missing', 'invalid_forecast_data'),
    ('Open-Meteo response is missing', 'variables_missing', 'invalid_forecast_data'),
    ('No complete live forecast observations', 'no_complete_rows', 'invalid_forecast_data'),
    ('The selected forecast input hour is unavailable', 'selected_hour_unavailable', 'invalid_forecast_data'),
    ('Selected-hour ECMWF inputs are incomplete or unavailable', 'selected_hour_incomplete', 'invalid_forecast_data'),
    ('No previous-hour forecast found', 'previous_hour_unavailable', 'invalid_forecast_data'),
    ('Prediction input is missing features', 'feature_construction_incomplete', 'model_loading_failure'),
    ('Expected the existing 29-feature Random Forest', 'model_feature_count_mismatch', 'model_loading_failure'),
    ('The feature list does not match the trained model order', 'model_feature_order_mismatch', 'model_loading_failure'),
    ('This research system requires the selected 35% threshold', 'threshold_artefact_mismatch', 'configuration_failure'),
    ('Nonfinite model input', 'nonfinite_model_input', 'invalid_forecast_data'),
)
_PRE_INFERENCE_MODEL_CHECKS = ('feature_construction_incomplete', 'model_feature_count_mismatch',
                               'model_feature_order_mismatch', 'threshold_artefact_mismatch')


def _text(value):
    if value is None:
        return ''
    if isinstance(value, bytes):
        return value.decode('utf-8', errors='replace')
    return str(value)


def classify_forecast_failure(stdout, stderr, timed_out=False, launch_error=False):
    """Classify a failed run of script 12 from its own output.

    Returns enumerated stage statuses, an error category and a detail code, plus
    the HTTP status and exception class name where present. Raw output is never
    returned.
    """
    out, err = _text(stdout), _text(stderr)
    both = out + '\n' + err
    result = {
        'model_loading': UNKNOWN, 'forecast_retrieval': UNKNOWN, 'forecast_response_validation': UNKNOWN,
        'model_inference': UNKNOWN, 'prediction_output': UNKNOWN,
        'error_category': 'unexpected_internal_error', 'error_detail': 'unclassified',
        'forecast_http_status': None, 'exception_type': '',
    }
    try:
        http = re.findall(r'HTTP status:\s*(\d{3})', out)
        if http:
            result['forecast_http_status'] = int(http[-1])
        exc = re.findall(r'^([A-Za-z_][\w.]*(?:Error|Exception|Exit|Interrupt|Warning)):', err, flags=re.M)
        if exc:
            result['exception_type'] = exc[-1][:80]
        if launch_error:
            result.update(model_loading=NOT_ATTEMPTED, forecast_retrieval=NOT_ATTEMPTED,
                          forecast_response_validation=NOT_ATTEMPTED, model_inference=NOT_ATTEMPTED,
                          prediction_output=NOT_ATTEMPTED, error_detail='forecast_script_not_started')
            return result
        if timed_out:
            result.update(error_category='pipeline_timeout', error_detail='forecast_script_timeout')
        files_ok, model_ok = _STAGE_FILES_OK in out, _STAGE_MODEL_OK in out
        downloaded, features = _STAGE_DOWNLOADED in out, _STAGE_FEATURES in out
        predicted, saved = _STAGE_PREDICTED in out, _STAGE_SAVED in out
        result['model_loading'] = 'ok' if model_ok else 'failed'
        if not model_ok:
            for key in ('forecast_retrieval', 'forecast_response_validation', 'model_inference', 'prediction_output'):
                result[key] = NOT_ATTEMPTED
        elif _STAGE_REQUEST_FAILED in out or (result['forecast_http_status'] or 200) >= 400:
            result.update(forecast_retrieval='failed', forecast_response_validation=NOT_ATTEMPTED,
                          model_inference=NOT_ATTEMPTED, prediction_output=NOT_ATTEMPTED)
        elif not downloaded:
            # A 200 response that could not be decoded, or an error before the
            # success banner, is a retrieval problem unless a known message says otherwise.
            result.update(forecast_retrieval='failed', forecast_response_validation=NOT_ATTEMPTED,
                          model_inference=NOT_ATTEMPTED, prediction_output=NOT_ATTEMPTED)
        else:
            result['forecast_retrieval'] = 'ok'
            result['forecast_response_validation'] = 'ok' if features else 'failed'
            if not features:
                result.update(model_inference=NOT_ATTEMPTED, prediction_output=NOT_ATTEMPTED)
            else:
                result['model_inference'] = 'ok' if predicted else 'failed'
                result['prediction_output'] = ('ok' if saved else 'failed') if predicted else NOT_ATTEMPTED
        if timed_out:
            return result
        for message, detail, category in _KNOWN_MESSAGES:
            if message in both:
                result.update(error_category=category, error_detail=detail)
                if detail in _PRE_INFERENCE_MODEL_CHECKS:
                    # Response already validated; the model/feature check precedes inference.
                    result.update(forecast_response_validation='ok', model_inference=NOT_ATTEMPTED,
                                  prediction_output=NOT_ATTEMPTED)
                elif detail == 'nonfinite_model_input':
                    result.update(forecast_response_validation='failed', model_inference=NOT_ATTEMPTED,
                                  prediction_output=NOT_ATTEMPTED)
                elif category == 'invalid_forecast_data' and result['forecast_response_validation'] == UNKNOWN:
                    result['forecast_response_validation'] = 'failed'
                return result
        if not files_ok or not model_ok:
            result.update(error_category='model_loading_failure', error_detail='model_load_error')
        elif result['forecast_retrieval'] == 'failed':
            if _STAGE_REQUEST_FAILED in out:
                detail = f"http_{result['forecast_http_status']}" if result['forecast_http_status'] else 'request_exception'
            else:
                detail = 'response_not_decodable'
            result.update(error_category='forecast_retrieval_failure', error_detail=detail)
        elif result['forecast_response_validation'] == 'failed':
            result.update(error_category='invalid_forecast_data', error_detail='response_validation_error')
        elif result['model_inference'] == 'failed':
            result.update(error_category='inference_failure', error_detail='predict_proba_error')
        elif result['prediction_output'] == 'failed':
            result.update(error_category='prediction_output_failure', error_detail='prediction_write_error')
        return result
    except Exception:
        return result


_ID_FIELDS = ('workflow_run_id', 'workflow_run_number', 'workflow_run_attempt')


def _coerce(key, value):
    expected = SCHEMA[key]
    if value is None:
        return None
    if key in _ID_FIELDS:
        # Public GitHub run identifiers are digits; anything else is not trusted.
        text = str(value)
        return text if re.fullmatch(r'\d{1,20}', text) or text in (NOT_APPLICABLE, UNKNOWN) else '[REDACTED]'
    if expected is float:
        if isinstance(value, bool):
            return None
        try:
            number = float(value)
        except (TypeError, ValueError):
            return None
        return number if math.isfinite(number) else None
    if expected is int:
        if isinstance(value, bool):
            return None
        try:
            return int(value)
        except (TypeError, ValueError):
            return None
    return sanitise_text(value)


def sanitise_record(record):
    """Whitelist schema fields, coerce types and redact text; never raises."""
    clean = {}
    try:
        for key in SCHEMA:
            if key in record:
                clean[key] = _coerce(key, record[key])
        if clean.get('error_category') not in ERROR_CATEGORIES:
            clean['error_category'] = 'unexpected_internal_error'
        if 'trigger_source' in clean and clean['trigger_source'] not in TRIGGER_SOURCES:
            clean['trigger_source'] = 'unknown'
    except Exception:
        clean = {'schema_version': SCHEMA_VERSION, 'record_type': 'worker_run',
                 'error_category': 'unexpected_internal_error', 'error_detail': 'record_sanitisation_failed'}
    return clean


def default_record_path():
    configured = os.environ.get('RUN_RECORD_FILE', '').strip()
    if configured:
        return Path(configured)
    stamp = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')
    return Path(__file__).resolve().parent / 'outputs' / 'model_live' / 'run_records' / f'run_record_{stamp}_{os.getpid()}.json'


def write_record(record, path=None):
    """Atomically write the sanitised record; returns the path or None. Never raises."""
    temporary = None
    try:
        target = Path(path) if path else default_record_path()
        target.parent.mkdir(parents=True, exist_ok=True)
        payload = json.dumps(sanitise_record(record), indent=2, sort_keys=True)
        with tempfile.NamedTemporaryFile('w', encoding='utf-8', dir=target.parent, suffix='.tmp', delete=False) as handle:
            temporary = Path(handle.name)
            handle.write(payload)
        os.replace(temporary, target)
        return target
    except Exception:
        try:
            if temporary is not None:
                temporary.unlink(missing_ok=True)
        except Exception:
            pass
        return None
