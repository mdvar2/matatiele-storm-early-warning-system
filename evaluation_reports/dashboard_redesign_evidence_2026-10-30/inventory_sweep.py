"""Component inventory of every dashboard page, production (c2aefb7) vs redesign (working tree).

Hermetic: synthetic genuine-shaped prediction and history files, fixed clock, network refused,
Twilio unconfigured, settings from the test environment only. Counts every rendered element
type (generic tree walk) plus HTML component markers (stylesheets excluded).
Usage (from project root): python inventory_sweep.py OUT.json
"""
import json, os, shutil, subprocess, sys, tempfile
from collections import Counter
from pathlib import Path
from unittest.mock import Mock, patch

ROOT = Path.cwd()
sys.path[:0] = [str(ROOT / 'tests'), str(ROOT)]
import pandas as pd, requests
import test_resident_dashboard as rd
import sms_alert, app_config
from forecast_timing import model_input_hour

PAGES = ['Dashboard', 'Safety Advice', 'Live Forecast', 'Weather Map', 'Risk Analysis', 'Historical Data', 'Alerts & Notifications', 'About']
MARKERS = ['resident-card', 'resident-guidance', 'kpi', 'weather-body', 'risk-body', 'prediction-table', 'research-card',
           'research-notice', 'rain-legend', 'status-strip', 'map-legend', 'section-title']
SKIP = {'html', 'markdown', 'caption', 'flex_container', 'divider', 'button', 'text_input', 'toggle', 'button_group', 'spinner'}


def walk(node, counter):
    kind = getattr(node, 'type', None)
    if kind:
        counter[kind] += 1
    for child in getattr(node, 'children', {}).values():
        walk(child, counter)


def sweep(files):
    tmp = Path(tempfile.mkdtemp(prefix='inv-'))
    for name, text in files.items():
        (tmp / name).write_text(text, encoding='utf-8')
    (tmp / '12_live_forecast_and_predict.py').write_text('# placeholder\n')
    model = tmp / 'outputs' / 'model_live'; model.mkdir(parents=True)
    (model / 'live_selected_threshold.txt').write_text('0.35\n')
    now = pd.Timestamp(rd.FIXED_NOW).tz_convert('Africa/Johannesburg'); start = model_input_hour(now, next_complete=True)
    row = {'forecast_source': 'Open-Meteo ECMWF', 'forecast_retrieved_at': now.isoformat(), 'prediction_generated_at': now.isoformat(),
           'forecast_input_time': start.isoformat(), 'prediction_for': (start + pd.Timedelta(hours=1)).isoformat(), 'storm_probability': .05,
           'decision_threshold': .35, 'temperature_c': 18.0, 'precipitation_mm': 0.0, 'cape': 0.0, 'wind_gust_ms': 3.0, 'wind_speed_ms': 1.0,
           'cloud_cover_percent': 10.0, 'pressure_msl_hpa': 1018.0, 'dewpoint_c': 9.0}
    pd.DataFrame([row]).to_csv(model / 'dashboard_forecast_prediction.csv', index=False)
    earlier = [dict(row, prediction_for=(start - pd.Timedelta(hours=h)).isoformat(), storm_probability=p) for h, p in ((1, .03), (2, .12), (3, .07))]
    pd.DataFrame(earlier).to_csv(model / 'prediction_history.csv', index=False)
    from streamlit.testing.v1 import AppTest
    import streamlit as st
    env_only = lambda name: os.getenv(name, '').strip()  # noqa: E731
    result = {}
    with patch.dict(os.environ, {'ADMIN_PASSWORD': 'inventory-only'}), patch.object(app_config, 'get_setting', env_only), \
         patch.object(sms_alert, 'get_setting', env_only), patch('requests.get', side_effect=requests.ConnectionError('offline')), \
         patch.object(sms_alert, '_send_warning', side_effect=AssertionError('send')), patch('subprocess.run', return_value=Mock(returncode=0)), \
         patch('datetime.datetime', rd.FrozenDateTime):
        st.cache_resource.clear()
        at = AppTest.from_file(str(tmp / '16_dashboard.py'), default_timeout=120).run()
        for page in PAGES:
            next(b for b in at.button if b.label == page).click().run()
            assert at.session_state['dashboard_page'].endswith(page), (at.session_state['dashboard_page'], page)
            counter = Counter(); walk(at._tree, counter)
            entry = {k: v for k, v in sorted(counter.items()) if k not in SKIP}
            html = '\n'.join(e.proto.body for e in at.get('html') if not e.proto.body.lstrip().startswith('<style'))
            for marker in MARKERS:
                n = html.count(f'class="{marker}') + html.count(f'class="{marker} ')
                n = html.count(f'class="{marker}')
                if n:
                    entry['.' + marker] = n
            result[page] = entry
    shutil.rmtree(tmp, ignore_errors=True)
    return result


prod = {name: subprocess.run(['git', 'show', f'c2aefb7:{name}'], cwd=ROOT, capture_output=True, text=True, encoding='utf-8', check=True).stdout
        for name in ('16_dashboard.py', 'app_config.py', 'forecast_timing.py', 'sms_alert.py', 'resident_view.py')}
new = {name: (ROOT / name).read_text(encoding='utf-8') for name in ('16_dashboard.py', 'app_config.py', 'forecast_timing.py', 'sms_alert.py', 'resident_view.py', 'dashboard_theme.py')}
a, b = sweep(prod), sweep(new)
json.dump({'production_c2aefb7': a, 'redesign': b}, open(sys.argv[1], 'w'), indent=1)
for page in PAGES:
    lost = {k: (a[page][k], b[page].get(k, 0)) for k in a[page] if b[page].get(k, 0) < a[page][k]}
    added = {k: b[page][k] - a[page].get(k, 0) for k in b[page] if b[page][k] > a[page].get(k, 0)}
    print(f'{page:23s} production={a[page]}')
    print(f'{"":23s} lost={lost or "none"} | added={added or "none"}')
