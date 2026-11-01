"""Storm-risk outlook: the trained Random Forest applied to each of the coming ECMWF forecast hours.

The live script (12_live_forecast_and_predict.py) scores one hour: the next complete forecast hour and the hour
before it predict the hour after. This module builds exactly the same 29 inputs, with the same unit conversions,
CAPE normalisation and model location, for every forecast hour in the next `hours` hours, so residents can be
warned before a storm arrives and before networks fail.

Scientific limits (state them wherever the outlook is shown):
- the model was evaluated one hour ahead only; scores further ahead are unvalidated, and forecast skill falls
  with lead time;
- a score is a model risk score, not a calibrated probability;
- the model, its features and the 35% threshold are unchanged. Nothing here alters the next-hour warning.
"""
from datetime import datetime, timezone

import numpy as np
import pandas as pd
import requests

from cape_normalisation import normalise_cape
from forecast_timing import model_input_hour

API_URL = 'https://api.open-meteo.com/v1/ecmwf'
TARGET_LATITUDE, TARGET_LONGITUDE = -30.30, 28.80   # as in 12_live_forecast_and_predict.py
MODEL_LATITUDE, MODEL_LONGITUDE = -30.25, 28.75
VARIABLES = ('temperature_2m', 'dew_point_2m', 'pressure_msl', 'surface_pressure', 'precipitation', 'showers',
             'cape', 'cloud_cover', 'wind_speed_10m', 'wind_direction_10m', 'wind_gusts_10m')
WEATHER = ('t2m', 'd2m', 'msl', 'sp', 'tp', 'cape', 'cp', 'tcc', 'u10', 'v10', 'i10fg', 'wind_speed')
THRESHOLD = 0.35
DEFAULT_HOURS = 12


def fetch(session=None):
    """The same ECMWF request as the live script. Raises on network or API errors."""
    http = session or requests
    response = http.get(API_URL, timeout=(15, 120), params={
        'latitude': TARGET_LATITUDE, 'longitude': TARGET_LONGITUDE, 'hourly': ','.join(VARIABLES), 'timezone': 'UTC',
        'wind_speed_unit': 'ms', 'precipitation_unit': 'mm', 'past_days': 1, 'forecast_days': 2})
    response.raise_for_status()
    payload = response.json()
    if payload.get('error') or 'hourly' not in payload:
        raise ValueError('Open-Meteo returned no hourly forecast.')
    return payload


def training_units(payload):
    """Hourly forecast in the training units (identical conversions to the live script); incomplete hours dropped."""
    frame = pd.DataFrame(payload['hourly'])
    missing = [v for v in ('time',) + VARIABLES if v not in frame]
    if missing:
        raise ValueError(f'Forecast is missing {missing}.')
    frame['valid_time'] = pd.to_datetime(frame.pop('time'), errors='coerce', utc=True)
    frame = frame.sort_values('valid_time').reset_index(drop=True)
    frame['t2m'] = frame['temperature_2m'] + 273.15
    frame['d2m'] = frame['dew_point_2m'] + 273.15
    frame['msl'] = frame['pressure_msl'] * 100
    frame['sp'] = frame['surface_pressure'] * 100
    frame['tp'] = frame['precipitation'] / 1000
    frame['cp'] = frame['showers'] / 1000
    frame['tcc'] = frame['cloud_cover'] / 100
    frame['i10fg'] = frame['wind_gusts_10m']
    radians = np.radians(frame['wind_direction_10m'])
    frame['u10'] = -frame['wind_speed_10m'] * np.sin(radians)
    frame['v10'] = -frame['wind_speed_10m'] * np.cos(radians)
    frame['wind_speed'] = np.sqrt(frame['u10'] ** 2 + frame['v10'] ** 2)
    return frame.dropna(subset=('valid_time',) + WEATHER).copy()


def features_for(frame, input_hour):
    """The 29-feature row for one input hour (and the hour before it), or None if either hour is missing."""
    input_hour = pd.Timestamp(input_hour)
    current = frame.loc[frame['valid_time'] == input_hour]
    previous = frame.loc[frame['valid_time'] == input_hour - pd.Timedelta(hours=1)]
    if current.empty or previous.empty:
        return None
    latest, before = current.iloc[-1].copy(), previous.iloc[0].copy()
    for row in (latest, before):
        value, _ = normalise_cape(row['cape'])
        if value is not None:
            row['cape'] = value
    row = {'latitude': MODEL_LATITUDE, 'longitude': MODEL_LONGITUDE}
    row.update({name: latest[name] for name in ('t2m', 'd2m', 'msl', 'sp', 'tp', 'cape', 'cp', 'tcc', 'u10', 'v10', 'i10fg')})
    row.update({'hour': input_hour.hour, 'month': input_hour.month, 'day_of_year': input_hour.dayofyear, 'wind_speed': latest['wind_speed']})
    row.update({f'previous_{name}': before[name] for name in WEATHER})
    return row


def score(payload, model, features, now=None, hours=DEFAULT_HOURS):
    """Model risk score for each target hour in the next `hours` hours.

    Returns rows {target_end_utc, input_hour_utc, lead_hours, score}; hours without complete inputs are skipped,
    never filled in. Lead 1 is the next-hour estimate the live script makes; later leads are the outlook.
    """
    now = pd.Timestamp(now or datetime.now(timezone.utc)).tz_convert('UTC')
    frame = training_units(payload)
    first_input = model_input_hour(now, next_complete=True)   # the dashboard's next-hour input, so lead 1 matches it
    rows, inputs = [], []
    for lead in range(1, hours + 1):
        input_hour = first_input + pd.Timedelta(hours=lead - 1)
        row = features_for(frame, input_hour)
        if row is None:
            continue
        rows.append({'target_end_utc': input_hour + pd.Timedelta(hours=1), 'input_hour_utc': input_hour, 'lead_hours': lead})
        inputs.append(row)
    if not inputs:
        return []
    matrix = pd.DataFrame(inputs)[list(features)]
    if not np.isfinite(matrix.to_numpy(dtype=float)).all():
        raise ValueError('Nonfinite model input in the outlook.')
    for row, probability in zip(rows, model.predict_proba(matrix)[:, 1]):
        row['score'] = float(probability)
    return rows


def first_exceedance(rows, threshold=THRESHOLD, min_lead=2):
    """The earliest outlook hour (lead >= min_lead) at or above the threshold, or None."""
    return next((r for r in rows if r['lead_hours'] >= min_lead and r['score'] >= threshold), None)


RECORD_PREFIX = '[OUTLOOK] '


def early_alert_records(repo, session=None):
    """Early alerts made by 27_outlook_alert.py, from the public [OUTLOOK] issues (newest first). Raises on API errors."""
    import json
    import re
    http = session or requests
    records = []
    for page in (1, 2, 3):
        response = http.get(f'https://api.github.com/repos/{repo}/issues', timeout=15,
                            params={'state': 'all', 'sort': 'created', 'direction': 'desc', 'per_page': 100, 'page': page},
                            headers={'Accept': 'application/vnd.github+json', 'X-GitHub-Api-Version': '2022-11-28'})
        response.raise_for_status()
        rows = response.json()
        for row in rows:
            if not row.get('title', '').startswith(RECORD_PREFIX) or 'pull_request' in row:
                continue
            match = re.search(r'```json\s*(\{.*?\})\s*```', row.get('body') or '', re.S)
            try:
                data = json.loads(match.group(1)) if match else {}
            except ValueError:
                data = {}
            if data.get('first_target_end_utc') and isinstance(data.get('score'), (int, float)):
                records.append({'key': row['title'][len(RECORD_PREFIX):], 'first_target_end_utc': data['first_target_end_utc'],
                                'score': float(data['score']), 'created_at': row.get('created_at'), 'url': row.get('html_url')})
        if len(rows) < 100:
            break
    return records
