"""Forecast validity helpers; stored/API timestamps are UTC, display is SAST.

Open-Meteo precipitation is a preceding-hour sum, not an instantaneous value:
https://open-meteo.com/en/docs/ecmwf-api#hourly-parameter-definition
No forecast timestamps or measurements are shifted by these helpers.
"""
from datetime import datetime
from typing import Any, Mapping
from zoneinfo import ZoneInfo

import pandas as pd

SAST = ZoneInfo('Africa/Johannesburg')
TARGET_LABEL = 'Forecast target (SAST)'
GENERATED_LABEL = 'Prediction generated (SAST)'


def local_time(value: Any) -> pd.Timestamp | None:
    """Normalize UTC API/legacy CSV timestamps; missing dates stay unknown."""
    if value is None:
        return None
    timestamp = pd.to_datetime(value, utc=True, errors='coerce')
    return timestamp.tz_convert(SAST) if isinstance(timestamp, pd.Timestamp) else None


def timestamp_labels(row: Mapping[str, Any]) -> dict[str, str]:
    labels = {}
    for label, field in [(TARGET_LABEL, 'prediction_for'),
                         (GENERATED_LABEL, 'prediction_generated_at')]:
        timestamp = local_time(row.get(field))
        labels[label] = timestamp.strftime('%d %b %Y %H:%M:%S') if timestamp is not None else 'Unknown (legacy record)'
    return labels


def interval_label(end: Any) -> str:
    """Label the documented accumulation interval, including midnight dates."""
    timestamp = local_time(end)
    if timestamp is None:
        return 'Target interval unavailable'
    start = timestamp - pd.Timedelta(hours=1)
    return f'{start:%d %b %Y %H:%M} – {timestamp:%d %b %Y %H:%M} SAST'


def next_hour_endpoint(now: datetime | pd.Timestamp) -> pd.Timestamp:
    clock = pd.Timestamp(now)
    if clock.tzinfo is None:
        raise ValueError('Forecast selection requires a timezone-aware clock')
    endpoint = clock.tz_convert('UTC').floor('h') + pd.Timedelta(hours=1)
    if not isinstance(endpoint, pd.Timestamp):
        raise ValueError('Invalid forecast selection clock')
    return endpoint


def model_input_hour(now: datetime | pd.Timestamp, *, next_complete: bool = False) -> pd.Timestamp:
    """Keep worker inputs at floor(now); dashboard may use the next hourly row.

    Both use the unchanged training relationship X(t) -> storm_label(t+1).
    Selecting a future input requires real forecast values for that timestamp.
    """
    clock = pd.Timestamp(now)
    if clock.tzinfo is None:
        raise ValueError('Model selection requires a timezone-aware clock')
    clock = clock.tz_convert('UTC')
    hour = clock.ceil('h') if next_complete else clock.floor('h')
    if not isinstance(hour, pd.Timestamp):
        raise ValueError('Invalid model selection clock')
    return hour


def next_complete_hour_endpoint(now: datetime | pd.Timestamp) -> pd.Timestamp:
    return next_hour_endpoint(model_input_hour(now, next_complete=True))


def is_next_complete_prediction(input_time: Any, target: Any, now: datetime) -> bool:
    start, end = local_time(input_time), local_time(target)
    return (start is not None and end is not None
            and start == model_input_hour(now, next_complete=True)
            and end == start + pd.Timedelta(hours=1))


def six_hour_forecast(frame: pd.DataFrame, now: datetime | pd.Timestamp,
                      *, complete_intervals: bool = False) -> pd.DataFrame:
    """Select the next six fixed hourly endpoints, never skipping missing hours.

    The first interval may already be underway. Incomplete data are returned
    with gaps (no imputation), rather than substituting later forecast hours.
    """
    if frame.empty:
        return frame.copy()
    result = frame.copy()
    result['time'] = pd.to_datetime(result['forecast_hour'], utc=True, errors='coerce')
    first = next_complete_hour_endpoint(now) if complete_intervals else next_hour_endpoint(now)
    last = first + pd.Timedelta(hours=5)
    result = pd.DataFrame(result.loc[(result['sample_id'] == 25) & result['time'].between(first, last)])
    result = result.sort_values(by='time').drop_duplicates(subset=['time']).copy()
    result['time'] = pd.Series(result['time']).dt.tz_convert(SAST)
    result['precipitation'] = result['precipitation_mm']
    return result


def forecast_axis_order(times: pd.Series) -> list[str]:
    """Explicit ordinal order prevents Vega-Lite's lexical midnight sorting."""
    return pd.to_datetime(times, utc=True).dt.tz_convert(SAST).sort_values().dt.strftime('%H:%M').tolist()
