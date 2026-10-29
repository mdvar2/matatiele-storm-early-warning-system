"""Run the real 12_live_forecast_and_predict.py offline (no network, no writes to the project).

The script runs from a temporary folder, so its output CSV lands there. Open-Meteo is
replaced by a supplied JSON payload, the input hour is fixed, and joblib.load returns the
real Random Forest (loaded once). The model, features and 0.35 threshold are the
project's own files; nothing about them is changed.
"""
import contextlib
import io
import json
import runpy
import shutil
import sys
import tempfile
from pathlib import Path
from unittest.mock import patch

import joblib
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
MODEL_DIR = ROOT / 'outputs' / 'model_live'
SCRIPT = ROOT / '12_live_forecast_and_predict.py'
VARIABLES = ('temperature_2m', 'dew_point_2m', 'pressure_msl', 'surface_pressure', 'precipitation', 'showers',
             'cape', 'cloud_cover', 'wind_speed_10m', 'wind_direction_10m', 'wind_gusts_10m')
_MODEL = None


def model_available():
    return all((MODEL_DIR / name).is_file() for name in
               ('random_forest_live_model.pkl', 'live_model_features.txt', 'live_selected_threshold.txt'))


def real_model():
    global _MODEL
    if _MODEL is None:
        _MODEL = joblib.load(MODEL_DIR / 'random_forest_live_model.pkl')
    return _MODEL


class _Spy:
    """Forwards everything to the real model; records each feature frame given to predict_proba."""

    def __init__(self, model, capture):
        self._model, self._capture = model, capture

    def __getattr__(self, name):
        return getattr(self._model, name)

    def predict_proba(self, frame):
        self._capture.append(frame.copy())
        return self._model.predict_proba(frame)


class _Response:
    def __init__(self, payload):
        self.status_code, self._payload = 200, payload

    def raise_for_status(self):
        return None

    def json(self):
        return json.loads(json.dumps(self._payload))  # fresh copy each call


def synthetic_payload(start='2026-10-29T17:00', hours=4, **overrides):
    """Plausible Matatiele hourly forecast; overrides map variable -> list or scalar."""
    times = pd.date_range(start, periods=hours, freq='h').strftime('%Y-%m-%dT%H:%M').tolist()
    base = {'temperature_2m': 16.3, 'dew_point_2m': 12.6, 'pressure_msl': 1020.9, 'surface_pressure': 863.6,
            'precipitation': 0.0, 'showers': 0.0, 'cape': 0.0, 'cloud_cover': 6.0, 'wind_speed_10m': 0.98,
            'wind_direction_10m': 120.0, 'wind_gusts_10m': 2.7}
    hourly = {'time': times}
    for name in VARIABLES:
        value = overrides.get(name, base[name])
        hourly[name] = list(value) if isinstance(value, (list, tuple)) else [value] * hours
    return {'latitude': -30.25, 'longitude': 28.75, 'hourly': hourly}


def run_inference(payload, input_hour, script=SCRIPT, capture=None):
    """Return (row_dict or None, error or None, stdout). Never touches the network.

    If capture is a list, each model input frame is appended to it.
    """
    tmp = Path(tempfile.mkdtemp(prefix='inference-'))
    try:
        target = tmp / 'outputs' / 'model_live'
        target.mkdir(parents=True)
        for name in ('live_model_features.txt', 'live_selected_threshold.txt'):
            shutil.copy(MODEL_DIR / name, target / name)
        (target / 'random_forest_live_model.pkl').write_bytes(b'')  # placeholder; joblib.load is patched
        copy = tmp / '12_live_forecast_and_predict.py'
        shutil.copy(script, copy)
        out = io.StringIO()
        error = None
        with patch('requests.get', return_value=_Response(payload)) as get, \
             patch('forecast_timing.model_input_hour', return_value=pd.Timestamp(input_hour)), \
             patch('joblib.load', return_value=real_model() if capture is None else _Spy(real_model(), capture)), \
             patch.object(sys, 'argv', [str(copy)]), contextlib.redirect_stdout(out):
            try:
                runpy.run_path(str(copy), run_name='__main__')
            except (SystemExit, Exception) as exc:  # the script signals failure by raising
                error = exc
        assert get.call_count <= 1
        csv = target / 'live_forecast_prediction.csv'
        row = pd.read_csv(csv).iloc[0].to_dict() if csv.is_file() and error is None else None
        return row, error, out.getvalue()
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
