"""Early storm alert: warn residents hours ahead, while networks still work.

Runs as a separate workflow step after the hourly worker. It never changes the validated next-hour warning, never
fails the job (always exits 0), and is off unless OUTLOOK_ALERTS_ENABLED=true.

1. Score the next 12 ECMWF forecast hours with the unchanged Random Forest (outlook.py, the live script's exact inputs).
2. If any hour 2 to 12 hours ahead reaches the 35% threshold, an early alert is due for that 6-hour block (SAST).
3. Public record first: one "[OUTLOOK] OUTLOOK-V1-<date>-<block>" GitHub issue per block. An existing record means the
   alert was already made, so nothing is sent again.
4. SMS only when SUBSCRIBER_ALERTS_ENABLED=true: residents get the early alert, community relays the same text plus
   the request to pass it on; one message per alert and subscriber (subscriber_alerts.deliver_warning).

Scores beyond one hour ahead are unvalidated, and every message says the alert is not certain.
Run locally (prints the outlook; sends nothing unless enabled):  python 27_outlook_alert.py
"""
import json
import os
import sys
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

import joblib
import numpy as np
import pandas as pd

import outlook

ROOT = Path(__file__).resolve().parent
MODEL_DIR = ROOT / 'outputs' / 'model_live'
API = 'https://api.github.com'
RECORD_PREFIX = '[OUTLOOK] '
KEY_PREFIX = 'OUTLOOK-V1-'
BLOCKS = ('night', 'morning', 'afternoon', 'evening')   # SAST 00-06, 06-12, 12-18, 18-24
SAST = 'Africa/Johannesburg'


def alert_key(row):
    """One early alert per 6-hour SAST block of the first hour at or above the threshold."""
    start = pd.Timestamp(row['target_end_utc']).tz_convert(SAST) - pd.Timedelta(hours=1)
    return f'{KEY_PREFIX}{start:%Y-%m-%d}-{BLOCKS[start.hour // 6]}'


def message(row, now):
    start = pd.Timestamp(row['target_end_utc']).tz_convert(SAST) - pd.Timedelta(hours=1)
    day = 'today' if start.date() == pd.Timestamp(now).tz_convert(SAST).date() else 'tomorrow'
    return (f'MATATIELE EARLY STORM ALERT: model outlook shows raised storm risk from about {start:%H:%M} SAST {day} '
            f'(score {row["score"]:.0%}). Not certain. Prepare now: plan shelter, move animals early, avoid rivers. Check SAWS.')


def github_request(method, url, token, payload=None, timeout=20):
    data = None if payload is None else json.dumps(payload).encode('utf-8')
    req = urllib.request.Request(url, data=data, method=method, headers={
        'Accept': 'application/vnd.github+json', 'Authorization': f'Bearer {token}', 'X-GitHub-Api-Version': '2022-11-28',
        'Content-Type': 'application/json'})
    with urllib.request.urlopen(req, timeout=timeout) as response:
        return json.loads(response.read().decode('utf-8') or 'null')


def find_or_create_record(repo, token, key, body, request=github_request):
    """(issue number, created). An existing record means this early alert was already made."""
    title = RECORD_PREFIX + key
    for page in (1, 2, 3):
        rows = request('GET', f'{API}/repos/{repo}/issues?state=all&sort=created&direction=desc&per_page=100&page={page}', token)
        for row in rows or []:
            if isinstance(row, dict) and row.get('title') == title and 'pull_request' not in row:
                return row['number'], False
        if not rows or len(rows) < 100:
            break
    issue = request('POST', f'{API}/repos/{repo}/issues', token, {'title': title, 'body': body})
    return issue['number'], True


def load_model():
    model = joblib.load(MODEL_DIR / 'random_forest_live_model.pkl')
    features = (MODEL_DIR / 'live_model_features.txt').read_text(encoding='utf-8').split()
    threshold = float((MODEL_DIR / 'live_selected_threshold.txt').read_text().strip())
    if len(features) != 29 or list(model.feature_names_in_) != features or not np.isclose(threshold, outlook.THRESHOLD):
        raise ValueError('The model, its 29 features or the 35% threshold differ from the deployed configuration.')
    return model, features


def run(environ, now=None, session=None, request=github_request):
    """Returns a summary dict (no personal data)."""
    now = pd.Timestamp(now or datetime.now(timezone.utc))
    model, features = load_model()
    rows = outlook.score(outlook.fetch(session), model, features, now=now)
    summary = {'generated_utc': now.isoformat(), 'outlook': [{'target_end_utc': r['target_end_utc'].isoformat(), 'lead_hours': r['lead_hours'],
                                                             'score': round(r['score'], 4)} for r in rows]}
    hit = outlook.first_exceedance(rows)
    if not hit:
        return dict(summary, early_alert='none')
    key = alert_key(hit)
    summary.update(early_alert_key=key, first_target_end_utc=hit['target_end_utc'].isoformat(), score=round(hit['score'], 4))
    if (environ.get('OUTLOOK_ALERTS_ENABLED') or '').strip().lower() != 'true':
        return dict(summary, early_alert='due_but_disabled')
    repo, token = environ.get('GITHUB_REPOSITORY', ''), environ.get('GH_TOKEN', '')
    if repo and token:
        body = ('Early storm alert from the model outlook (sanitised; no personal data). Unvalidated beyond one hour ahead; '
                'not an official warning.\n\n```json\n' + json.dumps(summary, indent=2) + '\n```')
        number, created = find_or_create_record(repo, token, key, body, request)
        summary.update(record_issue=number)
        if not created:
            return dict(summary, early_alert='already_alerted')
    summary['early_alert'] = 'recorded' if repo and token else 'not_recorded'
    if (environ.get('SUBSCRIBER_ALERTS_ENABLED') or '').strip().lower() == 'true':
        import subscriber_alerts
        import subscriptions as subs
        from subscriber_store import open_store
        gateway = subs.gateway_from_config(environ.get)
        if gateway is not None:
            text = message(hit, now)
            if not gateway.real:
                text = subscriber_alerts.TEST_PREFIX + text
            counts = subscriber_alerts.deliver_warning(open_store(environ.get), gateway, key, text, hit['target_end_utc'].isoformat(),
                                                       hit['score'], relay_body=subscriber_alerts.relay_message(text))
            summary.update(sms=counts)
    return summary


def main(environ=None):
    environ = os.environ if environ is None else environ
    try:
        summary = run(environ)
    except Exception as exc:   # monitoring-style step: report, never fail the job
        summary = {'early_alert': 'failed', 'error': type(exc).__name__}
    text = json.dumps(summary, indent=1, default=str)
    print(text)
    if environ.get('GITHUB_STEP_SUMMARY'):
        try:
            with open(environ['GITHUB_STEP_SUMMARY'], 'a', encoding='utf-8') as handle:
                handle.write('### Storm-risk outlook (next 12 hours)\n\n```json\n' + text + '\n```\n')
        except OSError:
            pass
    return 0


if __name__ == '__main__':
    sys.exit(main())
