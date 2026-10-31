"""The trained model's hourly outputs, from the durable public run log and the dashboard's own saved runs.

The scheduled worker posts one sanitised run record per hour as a comment on the public "[RUN-LOG] YYYY-MM"
issue (19_publish_run_record.py, when RUN_RECORD_PUBLISH=true). Those records survive dashboard restarts, so
they are the primary source. The dashboard's prediction_history.csv adds hours the worker did not record.
Only records with a validated model score are used; nothing is estimated, filled in or invented.
"""
import json
import re
from datetime import datetime, timedelta, timezone

import pandas as pd
import requests

RUN_LOG_TITLE = re.compile(r'^\[RUN-LOG\] (\d{4})-(\d{2})$')
JSON_BLOCK = re.compile(r'```json\s*(\{.*?\})\s*```', re.S)
WORKER, DASHBOARD = 'Hourly worker', 'Dashboard'
COLUMNS = ['prediction_for', 'forecast_input_time', 'prediction_generated_at', 'storm_probability', 'source']
API = 'https://api.github.com'


def _get(http, url, params):
    response = http.get(url, params=params, timeout=15,
                        headers={'Accept': 'application/vnd.github+json', 'X-GitHub-Api-Version': '2022-11-28'})
    response.raise_for_status()
    return response.json()


def parse_comment(body):
    """The run record inside a published comment, or None."""
    match = JSON_BLOCK.search(body or '')
    if not match:
        return None
    try:
        record = json.loads(match.group(1))
    except ValueError:
        return None
    return record if isinstance(record, dict) and record.get('record_type') == 'worker_run' else None


def fetch_records(repo, session=None, now=None, days=8):
    """Run records from the last `days` days (newest month issues only). Raises on network or API errors."""
    http = session or requests
    now = now or datetime.now(timezone.utc)
    since = now - timedelta(days=days)
    wanted = {f'{since:%Y-%m}', f'{now:%Y-%m}'}
    issues = []
    for page in (1, 2, 3):
        rows = _get(http, f'{API}/repos/{repo}/issues', {'state': 'all', 'sort': 'created', 'direction': 'desc',
                                                          'per_page': 100, 'page': page})
        for row in rows:
            match = RUN_LOG_TITLE.match(row.get('title', ''))
            if match and 'pull_request' not in row and f'{match.group(1)}-{match.group(2)}' in wanted:
                issues.append(row['number'])
        if len(rows) < 100:
            break
    records = []
    for number in issues:
        for page in range(1, 11):
            comments = _get(http, f'{API}/repos/{repo}/issues/{number}/comments',
                            {'since': since.isoformat(), 'per_page': 100, 'page': page})
            records += [r for r in (parse_comment(c.get('body')) for c in comments) if r]
            if len(comments) < 100:
                break
    return records


def worker_frame(records):
    """Validated model outputs from run records: one row per target hour (the latest record wins)."""
    rows = []
    for record in records:
        probability = record.get('storm_probability')
        if record.get('prediction_validation') != 'passed' or not isinstance(probability, (int, float)) or not 0 <= probability <= 1:
            continue
        rows.append({'prediction_for': record.get('prediction_target_utc'), 'forecast_input_time': record.get('forecast_input_utc'),
                     'prediction_generated_at': record.get('finished_utc'), 'storm_probability': float(probability), 'source': WORKER})
    return _clean(pd.DataFrame(rows, columns=COLUMNS))


def _clean(frame):
    frame = frame.copy()
    for column in ('prediction_for', 'forecast_input_time', 'prediction_generated_at'):
        frame[column] = pd.to_datetime(frame[column], utc=True, errors='coerce')
    frame['storm_probability'] = pd.to_numeric(frame['storm_probability'], errors='coerce')
    frame = frame.dropna(subset=['prediction_for', 'storm_probability'])
    frame = frame.loc[frame['storm_probability'].between(0, 1)]
    return frame.sort_values(['prediction_for', 'prediction_generated_at']).drop_duplicates('prediction_for', keep='last')


def combine(worker, history):
    """Worker records first; the dashboard's saved runs fill hours the worker did not record. Sorted by target hour."""
    local = pd.DataFrame(columns=COLUMNS)
    if history is not None and not history.empty and {'prediction_for', 'storm_probability'}.issubset(history.columns):
        local = history.reindex(columns=COLUMNS[:-1]).assign(source=DASHBOARD)
        local = _clean(local)
    parts = [p for p in (worker, local.loc[~local['prediction_for'].isin(worker['prediction_for'])]) if not p.empty]
    if not parts:
        return pd.DataFrame(columns=COLUMNS)
    return pd.concat(parts, ignore_index=True).sort_values('prediction_for').reset_index(drop=True)
