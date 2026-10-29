"""Publish the worker's sanitised run record (monitoring only).

Runs as a separate workflow step after the worker. Standard library only, so it
also works when dependency installation failed. It never sends SMS, never reads
or writes the [SMS-LEDGER] reservations, and always exits 0: a monitoring
problem is reported as a workflow warning, never as a failed warning run.

Outputs:
  * GitHub job summary (if GITHUB_STEP_SUMMARY is set);
  * one JSON comment on the monthly "[RUN-LOG] YYYY-MM" issue, only when
    RUN_RECORD_PUBLISH=true inside GitHub Actions.
"""
import json
import os
import re
import sys
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

try:
    import run_record
except Exception:  # pragma: no cover - publisher must still report something
    run_record = None

API = 'https://api.github.com'
TITLE_PREFIX = '[RUN-LOG]'
SUMMARY_FIELDS = ('outcome', 'worker_exit_code', 'mode', 'trigger', 'trigger_source', 'scheduled_slot_utc',
                  'dispatch_delay_seconds', 'reservation_lock', 'lock_label_permission', 'run_status_permission',
                  'cape_normalisation', 'cape_original_j_kg', 'previous_cape_normalisation', 'previous_cape_original_j_kg',
                  'workflow_run_number', 'started_utc',
                  'duration_seconds', 'model_loading', 'forecast_retrieval', 'forecast_http_status',
                  'forecast_response_validation', 'model_inference', 'prediction_output', 'prediction_validation',
                  'freshness_status', 'forecast_input_utc', 'prediction_target_utc', 'storm_probability',
                  'unvalidated_probability', 'warning_threshold', 'warning_decision', 'duplicate_prevention',
                  'sms_submission', 'ledger_report', 'error_category', 'error_detail')
_SENSITIVE_ENV = ('TWILIO_ACCOUNT_SID', 'TWILIO_AUTH_TOKEN', 'TWILIO_FROM_NUMBER', 'ALERT_TO_NUMBERS',
                  'GH_TOKEN', 'GITHUB_TOKEN', 'ADMIN_PASSWORD')


def warn(message):
    print(f'::warning::{message}')


def load_record(path):
    """Return the sanitised record, or an explicit 'missing record' record."""
    try:
        data = json.loads(Path(path).read_text(encoding='utf-8'))
        if not isinstance(data, dict):
            raise ValueError
        return run_record.sanitise_record(data) if run_record else {}
    except Exception:
        record = run_record.new_record() if run_record else {}
        record.update(record_type='worker_record_missing', outcome='unknown',
                      error_category='unexpected_internal_error', error_detail='worker_record_missing_or_unreadable')
        return run_record.sanitise_record(record) if run_record else record


def contains_secret(text, environ):
    for name in _SENSITIVE_ENV:
        for value in environ.get(name, '').split(','):
            value = value.strip()
            if len(value) >= 4 and value in text:
                return True
    return bool(re.search(r'\b(?:AC|SM|MM)[0-9a-fA-F]{32}\b|\+\d[\d \-]{6,}\d', text))


def summary_markdown(record):
    lines = ['### Scheduled storm check: run record (monitoring only)', '',
             '| Field | Value |', '|---|---|']
    for key in SUMMARY_FIELDS:
        value = record.get(key)
        lines.append(f"| {key} | {'n/a' if value in (None, '') else str(value).replace('|', '/')} |")
    lines += ['', 'No phone numbers, message content or provider identifiers are recorded.']
    return '\n'.join(lines) + '\n'


def github_request(method, url, token, payload=None, timeout=20):
    data = None if payload is None else json.dumps(payload).encode('utf-8')
    request = urllib.request.Request(url, data=data, method=method, headers={
        'Authorization': f'Bearer {token}', 'Accept': 'application/vnd.github+json',
        'X-GitHub-Api-Version': '2022-11-28', 'Content-Type': 'application/json',
        'User-Agent': 'matatiele-run-record'})
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return json.loads(response.read().decode('utf-8') or 'null')


def find_or_create_log_issue(repo, token, month, request=github_request):
    title = f'{TITLE_PREFIX} {month}'
    page = 1
    while True:
        rows = request('GET', f'{API}/repos/{repo}/issues?state=all&sort=created&direction=asc&per_page=100&page={page}', token)
        if not isinstance(rows, list):
            raise ValueError('unexpected issue listing')
        for row in rows:
            if isinstance(row, dict) and row.get('title') == title and 'pull_request' not in row:
                return row['number']
        if len(rows) < 100:
            break
        page += 1
    issue = request('POST', f'{API}/repos/{repo}/issues', token, {
        'title': title,
        'body': ('Sanitised operational run records for the scheduled Matatiele storm check, one comment per run. '
                 'Monitoring only: this is NOT the SMS duplicate-prevention ledger and contains no phone numbers, '
                 'message content or provider identifiers.')})
    if not isinstance(issue, dict) or not isinstance(issue.get('number'), int):
        raise ValueError('issue creation unconfirmed')
    return issue['number']


def publish(record, environ, request=github_request):
    repo, token = environ.get('GITHUB_REPOSITORY', ''), environ.get('GH_TOKEN', '')
    if not re.fullmatch(r'[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+', repo) or not token:
        warn('Run record not published: repository or token unavailable.')
        return False
    body_json = json.dumps(record, indent=2, sort_keys=True)
    if contains_secret(body_json, environ):
        warn('Run record not published: sensitive content detected after sanitisation.')
        return False
    month = str(record.get('started_utc') or datetime.now(timezone.utc).isoformat())[:7]
    if not re.fullmatch(r'\d{4}-\d{2}', month):
        month = datetime.now(timezone.utc).strftime('%Y-%m')
    number = find_or_create_log_issue(repo, token, month, request)
    request('POST', f'{API}/repos/{repo}/issues/{number}/comments', token, {
        'body': ('Run record (sanitised; monitoring only).\n\n```json\n' + body_json + '\n```')})
    print(f'Run record published to {TITLE_PREFIX} {month} (issue #{number}).')
    return True


def main(environ=None, request=github_request):
    env = os.environ if environ is None else environ
    try:
        record = load_record(env.get('RUN_RECORD_FILE', ''))
        summary_path = env.get('GITHUB_STEP_SUMMARY', '')
        if summary_path:
            try:
                text = summary_markdown(record)
                if contains_secret(text, env):  # the job summary is public on a public repository
                    warn('Run record summary withheld: sensitive content detected after sanitisation.')
                    text = '### Scheduled storm check: run record withheld (sensitive content detected)\n'
                with open(summary_path, 'a', encoding='utf-8') as handle:
                    handle.write(text)
            except Exception:
                warn('Run record job summary could not be written (monitoring only).')
        if env.get('RUN_RECORD_PUBLISH', '').lower() == 'true' and env.get('GITHUB_ACTIONS', '').lower() == 'true':
            try:
                publish(record, env, request)
            except (urllib.error.URLError, OSError, ValueError, KeyError, TypeError):
                warn('Run record could not be published to GitHub Issues (monitoring only; warning outcome unaffected).')
        else:
            print('Run record publication disabled (local run or RUN_RECORD_PUBLISH not true).')
    except Exception:
        warn('Run record publisher failed unexpectedly (monitoring only; warning outcome unaffected).')
    return 0


if __name__ == '__main__':
    sys.exit(main())
