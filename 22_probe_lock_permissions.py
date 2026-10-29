"""Check that the workflow token can operate the R3 duplicate-SMS lock (monitoring only).

Runs as its own workflow step after the worker. Standard library only. It
creates and immediately deletes a probe label named "sms-probe:<run>-<attempt>"
(never an "sms-lock:" name, so it cannot block or release a reservation), and
reads this run's own status, which lock recovery needs. It never sends SMS,
never reads or writes [SMS-LEDGER] issues and always exits 0.

Results are added to the sanitised run record (so they reach the job summary and
heartbeats):
  lock_label_permission  ok | create_forbidden | create_error | delete_forbidden | delete_error | not_attempted
  run_status_permission  ok | forbidden | error | not_attempted
"""
import json
import os
import re
import sys
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

try:
    import run_record
except Exception:  # pragma: no cover - the probe must still report something
    run_record = None

API = 'https://api.github.com'


def log(message):
    print(f'Lock permission probe: {message}', flush=True)


def github_status(method, url, token, payload=None, timeout=15):
    """Return the HTTP status only; response bodies are never logged or kept."""
    data = None if payload is None else json.dumps(payload).encode('utf-8')
    request = urllib.request.Request(url, data=data, method=method, headers={
        'Authorization': f'Bearer {token}', 'Accept': 'application/vnd.github+json',
        'X-GitHub-Api-Version': '2022-11-28', 'Content-Type': 'application/json',
        'User-Agent': 'matatiele-lock-probe'})
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return response.status
    except urllib.error.HTTPError as exc:
        return exc.code


def _outcome(status, ok, prefix=''):
    if status in ok:
        return 'ok'
    return f'{prefix}forbidden' if status in (401, 403) else f'{prefix}error'


def probe(environ, request=github_status):
    repo, token = environ.get('GITHUB_REPOSITORY', ''), environ.get('GH_TOKEN', '')
    run_id, attempt = environ.get('GITHUB_RUN_ID', ''), environ.get('GITHUB_RUN_ATTEMPT', '')
    if (environ.get('GITHUB_ACTIONS', '').lower() != 'true' or not token
            or not re.fullmatch(r'[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+', repo)
            or not run_id.isdigit() or not attempt.isdigit()):
        return {'lock_label_permission': 'not_attempted', 'run_status_permission': 'not_attempted'}
    base = f'{API}/repos/{repo}'
    name = f'sms-probe:{run_id}-{attempt}'
    results = {}
    try:
        created = request('POST', f'{base}/labels', token, {
            'name': name, 'color': 'ededed',
            'description': 'Permission probe; deleted immediately. Not an SMS lock.'})
        # 422 means a probe label of this very attempt already exists: creation rights are proven.
        results['lock_label_permission'] = _outcome(created, (201, 422), 'create_')
        if results['lock_label_permission'] == 'ok':
            deleted = request('DELETE', f"{base}/labels/{urllib.parse.quote(name, safe='')}", token)
            results['lock_label_permission'] = _outcome(deleted, (204,), 'delete_')
    except Exception:
        results['lock_label_permission'] = 'create_error'
    try:
        results['run_status_permission'] = _outcome(request('GET', f'{base}/actions/runs/{run_id}', token), (200,))
    except Exception:
        results['run_status_permission'] = 'error'
    return results


def main(environ=None, request=github_status):
    env = os.environ if environ is None else environ
    try:
        results = probe(env, request)
        for key, value in results.items():
            if value in ('ok', 'not_attempted'):
                log(f'{key}={value}')
            else:
                print(f'::warning::Lock permission probe: {key}={value}; the duplicate-SMS lock falls back to the issue ledger.')
        path = env.get('RUN_RECORD_FILE', '')
        if path and run_record and Path(path).is_file():
            record = json.loads(Path(path).read_text(encoding='utf-8'))
            if isinstance(record, dict):
                record.update(results)
                run_record.write_record(record, path)
    except Exception:
        print('::warning::Lock permission probe failed unexpectedly (monitoring only; warning outcome unaffected).')
    return 0


if __name__ == '__main__':
    sys.exit(main())
