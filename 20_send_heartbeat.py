"""Send Healthchecks.io heartbeats derived from the R1 run record (monitoring only).

Runs in its own workflow steps. Standard library only. It reads the sanitised
R1 run record; it never re-runs inference, never evaluates warning logic, never
sends SMS and never touches the duplicate-prevention ledger. It always exits 0.

Checks (ping URLs come only from GitHub Secrets; unset = that check is skipped):
  HC_EXECUTION_URL  HB-1  "/start" when the job starts, success ping when it ends (any outcome)
  HC_FORECAST_URL   HB-2  success ping only when a genuine prediction passed validation
  HC_FAILURE_URL    HB-3  success ping on a successful run, "/fail" on a failed run
  HC_WARNING_URL    HB-4  "/fail" ONLY, when an eligible genuine warning attempt failed.
                          Never pinged on success, so later runs cannot conceal it.

Usage:  python 20_send_heartbeat.py --start      (job start; HB-1 only)
        python 20_send_heartbeat.py              (job end; reads RUN_RECORD_FILE)
"""
import json
import os
import re
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

try:
    import run_record
except Exception:  # pragma: no cover - heartbeats must still be attempted
    run_record = None

CHECKS = {'HB-1': 'HC_EXECUTION_URL', 'HB-2': 'HC_FORECAST_URL', 'HB-3': 'HC_FAILURE_URL', 'HB-4': 'HC_WARNING_URL'}
ATTEMPTS = 3
ATTEMPT_TIMEOUT_S = 8
BACKOFF_S = 2
TOTAL_BUDGET_S = 60
MAX_BODY_BYTES = 1000
MAX_RESPONSE_BYTES = 64  # documented ping responses are short strings such as "OK"

# Documented Healthchecks.io ping responses (https://healthchecks.io/docs/http_api/).
# Only an exact "OK" body proves acceptance; HTTP 200 alone does not.
ACCEPTED_BODY = b'OK'
REJECTED_200_BODIES = {b'OK (not found)': 'endpoint_not_found', b'OK (rate limited)': 'rate_limited'}
HTTP_ERROR_OUTCOMES = {400: 'invalid_url_format', 404: 'endpoint_not_found', 409: 'ambiguous_endpoint',
                       429: 'rate_limited'}

# Enumerated fields only: no probability, no free-text messages, no identifiers of people or messages.
PAYLOAD_FIELDS = ('schema_version', 'record_type', 'outcome', 'worker_exit_code', 'mode', 'trigger',
                  'workflow_run_number', 'workflow_run_attempt', 'started_utc', 'duration_seconds',
                  'model_loading', 'forecast_retrieval', 'forecast_http_status', 'forecast_response_validation',
                  'model_inference', 'prediction_output', 'prediction_validation', 'freshness_status',
                  'warning_decision', 'duplicate_prevention', 'sms_submission', 'ledger_report',
                  'error_category', 'error_detail', 'exception_type')
_CODE = re.compile(r'^[A-Za-z0-9_.:+\-]{0,80}$')  # enumerations, ISO timestamps, class names
_SENSITIVE_ENV = ('TWILIO_ACCOUNT_SID', 'TWILIO_AUTH_TOKEN', 'TWILIO_FROM_NUMBER', 'ALERT_TO_NUMBERS',
                  'GH_TOKEN', 'GITHUB_TOKEN', 'ADMIN_PASSWORD') + tuple(CHECKS.values())
_WARNING_FAILURE_OK = {'sent', 'duplicate'}


def log(message):
    print(f'Heartbeat: {message}', flush=True)


def warn(message):
    print(f'::warning::Heartbeat: {message}', flush=True)


# ---------------------------------------------------------------- record -> signals
def load_record(path):
    """Sanitised R1 record, or an explicit missing-record marker. Never raises."""
    try:
        data = json.loads(Path(path).read_text(encoding='utf-8'))
        if not isinstance(data, dict):
            raise ValueError
        # Without run_record the payload allow-list and value checks still apply.
        return run_record.sanitise_record(data) if run_record else data
    except Exception:
        return {'record_type': 'worker_record_missing', 'outcome': 'unknown', 'worker_exit_code': None,
                'error_category': 'unexpected_internal_error', 'error_detail': 'worker_record_missing_or_unreadable'}


def is_valid_prediction(record):
    return (record.get('record_type') == 'worker_run' and record.get('forecast_retrieval') == 'ok'
            and record.get('model_inference') == 'ok' and record.get('prediction_validation') == 'passed')


def is_failed_run(record):
    return record.get('worker_exit_code') != 0 or record.get('record_type') != 'worker_run'


def is_genuine_warning_failure(record):
    """An eligible genuine (live) warning that was not accepted by the provider.

    Excludes dry runs, connectivity tests, duplicate suppression (already reserved)
    and accepted submissions ('sent'/'duplicate'), including a sent SMS whose
    ledger comment failed (that is reported through HB-3 instead).
    """
    return (record.get('record_type') == 'worker_run' and record.get('mode') == 'live'
            and record.get('warning_decision') == 'warning_eligible'
            and record.get('worker_exit_code') != 0
            and record.get('duplicate_prevention') != 'already_reserved'
            and record.get('sms_submission') not in _WARNING_FAILURE_OK)


def plan_pings(record):
    """Return [(check, suffix)] in priority order. suffix '' = success, '/fail' = failure."""
    pings = []
    if is_genuine_warning_failure(record):
        pings.append(('HB-4', '/fail'))
    pings.append(('HB-3', '/fail' if is_failed_run(record) else ''))
    if is_valid_prediction(record):
        pings.append(('HB-2', ''))
    pings.append(('HB-1', ''))
    return pings


def build_payload(record, environ):
    """Compact allow-listed JSON, or b'' if anything unexpected remains."""
    try:
        payload = {}
        for key in PAYLOAD_FIELDS:
            value = record.get(key)
            if value is None or isinstance(value, (bool, int, float)):
                payload[key] = value
            elif isinstance(value, str) and _CODE.fullmatch(value):
                payload[key] = value
            else:
                payload[key] = 'redacted'
        body = json.dumps(payload, separators=(',', ':'), sort_keys=True)
        if contains_secret(body, environ) or len(body.encode('utf-8')) > MAX_BODY_BYTES:
            return b''
        return body.encode('utf-8')
    except Exception:
        return b''


def contains_secret(text, environ):
    for name in _SENSITIVE_ENV:
        for value in environ.get(name, '').split(','):
            value = value.strip()
            if len(value) >= 4 and value in text:
                return True
    return bool(re.search(r'\b(?:AC|SM|MM)[0-9a-fA-F]{32}\b|\+\d[\d \-]{6,}\d|hc-ping\.com', text))


# ---------------------------------------------------------------- transport
def valid_endpoint(url):
    return bool(re.fullmatch(r'https://[A-Za-z0-9.\-]+(?::\d{2,5})?/[A-Za-z0-9_\-/.]+', url or ''))


def http_send(url, body, timeout):
    """Send one request; return (HTTP status, response body truncated to MAX_RESPONSE_BYTES + 1)."""
    data = body if body else None
    request = urllib.request.Request(url, data=data, method='POST' if data else 'GET',
                                     headers={'User-Agent': 'matatiele-heartbeat', 'Content-Type': 'text/plain'})
    with urllib.request.urlopen(request, timeout=timeout) as response:
        # Bounded read: one byte over the limit is enough to detect an oversized reply.
        return response.status, response.read(MAX_RESPONSE_BYTES + 1)


def classify_response(status, body):
    """Map a completed HTTP exchange to (outcome, retryable). Only status 200 + body 'OK' is 'sent'.

    Bodies are compared as whole values (surrounding whitespace ignored), never by
    substring. Response content is never returned or logged, only a category.
    """
    if status != 200:
        if status in HTTP_ERROR_OUTCOMES:
            return HTTP_ERROR_OUTCOMES[status], False
        return f'http_{status}', status >= 500
    if not isinstance(body, (bytes, bytearray)):
        return 'unexpected_response', False
    if len(body) > MAX_RESPONSE_BYTES:
        return 'unexpected_response_oversized', False
    text = bytes(body).strip()
    if text == ACCEPTED_BODY:
        return 'sent', False
    if text in REJECTED_200_BODIES:
        # Unknown/deleted check or ignored ping: never retried (rate limits must not be hammered).
        return REJECTED_200_BODIES[text], False
    if not text:
        return 'unexpected_response_empty', False
    return 'unexpected_response', False


def send_ping(check, base_url, suffix, body, deadline, sender=http_send, sleep=time.sleep):
    """Attempt one ping with bounded retries for transient errors only. Returns a status code string. Never raises."""
    if time.monotonic() >= deadline:
        return 'skipped_time_budget'
    url = base_url.rstrip('/') + suffix
    outcome = 'not_attempted'
    for attempt in range(1, ATTEMPTS + 1):
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            return 'failed_time_budget'
        try:
            status, response_body = sender(url, body, min(ATTEMPT_TIMEOUT_S, remaining))
            outcome, retryable = classify_response(int(status), response_body)
            if not retryable:
                return outcome
        except urllib.error.HTTPError as exc:
            outcome, retryable = classify_response(int(exc.code), None)
            if not retryable:
                return outcome  # wrong, revoked or rate-limited endpoint: retrying cannot help
        except (urllib.error.URLError, TimeoutError, OSError) as exc:
            outcome = 'timeout' if 'timed out' in str(getattr(exc, 'reason', exc)).lower() or isinstance(exc, TimeoutError) else 'network_error'
        except Exception as exc:
            outcome = f'error_{type(exc).__name__}'
        if attempt < ATTEMPTS:
            sleep(min(BACKOFF_S * attempt, max(0.0, deadline - time.monotonic())))
    return outcome


def main(argv=None, environ=None, sender=http_send, sleep=time.sleep, clock=time.monotonic):
    env = os.environ if environ is None else environ
    args = sys.argv[1:] if argv is None else argv
    results = {}
    try:
        deadline = clock() + TOTAL_BUDGET_S
        if '--start' in args:
            plan, body = [('HB-1', '/start')], b''
        else:
            record = load_record(env.get('RUN_RECORD_FILE', ''))
            plan, body = plan_pings(record), build_payload(record, env)
            log(f"run state: outcome={record.get('outcome')} category={record.get('error_category')} "
                f"valid_prediction={is_valid_prediction(record)} warning_failure={is_genuine_warning_failure(record)}")
        for check, suffix in plan:
            url = env.get(CHECKS[check], '').strip()
            if not url:
                results[check] = 'skipped_not_configured'
                continue
            if not valid_endpoint(url):
                results[check] = 'skipped_invalid_endpoint'
                warn(f'{check} endpoint is not a valid HTTPS URL; skipped (value not shown).')
                continue
            results[check] = send_ping(check, url, suffix, body if suffix != '/start' else b'', deadline, sender, sleep)
        for check, outcome in results.items():
            (log if outcome in ('sent', 'skipped_not_configured') else warn)(f'{check} {outcome}')
        if results and all(v == 'skipped_not_configured' for v in results.values()):
            log('no heartbeat secrets configured; monitoring skipped.')
    except Exception as exc:
        warn(f'unexpected heartbeat error ({type(exc).__name__}); warning outcome unaffected.')
    return 0, results


if __name__ == '__main__':
    main()
    sys.exit(0)
