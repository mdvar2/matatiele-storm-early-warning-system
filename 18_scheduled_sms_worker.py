"""Scheduled Beta SMS worker. Default: dry-run, no SMS.

Uses a GitHub Issue as a durable per-hour reservation, preventing repeat sends
across ephemeral GitHub Actions runners. Issues permission is required in live mode.
A reservation is not a delivery receipt. Review failed runs manually.
"""
import argparse
import math
import re
import os
import subprocess
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import NoReturn

import pandas as pd
import requests

BASE = Path(__file__).resolve().parent
PREDICTION = BASE / 'outputs' / 'model_live' / 'live_forecast_prediction.csv'
REPO = os.getenv('GITHUB_REPOSITORY', '')
TOKEN = os.getenv('GH_TOKEN', '')
API = 'https://api.github.com'


class WorkerError(RuntimeError):
    """Credential-free diagnostic safe to print in Actions logs."""


def fail(message: str) -> NoReturn:
    raise WorkerError(message)


def github(method, endpoint, **kwargs):
    if not re.fullmatch(r'[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+', REPO) or not TOKEN:
        fail('GITHUB_REPOSITORY and GH_TOKEN are required for live SMS.')
    try:
        response = requests.request(
            method, f'{API}/repos/{REPO}/{endpoint}', timeout=(10,25),
            headers={'Authorization': f'Bearer {TOKEN}',
                     'Accept': 'application/vnd.github+json',
                     'X-GitHub-Api-Version': '2022-11-28'}, **kwargs)
        response.raise_for_status()
        return response.json()
    except (requests.RequestException, ValueError):
        fail('GitHub ledger unavailable; submission stopped. Check permissions and service availability.')


def reserve_hour(key):
    # Live runs must use the same Actions concurrency group. Issue creation is
    # not atomic outside that serialized workflow. Never retry an uncertain POST.
    # List all issues, including closed; a closed reservation must not trigger resends.
    page = 1
    title = f'[SMS-LEDGER] {key}'
    while True:
        rows = github('GET', f'issues?state=all&sort=created&direction=asc&per_page=100&page={page}')
        if not isinstance(rows,list) or any(not isinstance(row,dict) for row in rows):
            fail('Invalid ledger response; no warning submitted.')
        if any(row.get('title') == title and 'pull_request' not in row for row in rows):
            return None
        if len(rows) < 100:
            break
        page += 1
    issue = github('POST', 'issues', json={
        'title': title,
        'body': ('Automated warning reservation for one forecast hour. '
                 'Do not delete this issue: it prevents duplicate SMS sends. '
                 'A reservation does not prove delivery.'),
    })
    if not isinstance(issue,dict) or not isinstance(issue.get('number'),int):
        fail('Reservation confirmation invalid; no SMS submitted. Review ledger manually.')
    return issue['number']


def report(issue_number, message):
    github('POST', f'issues/{issue_number}/comments', json={'body': message})


def validate_prediction(data, started, now):
    """Only fresh, genuine, finite next-hour outputs are eligible for warnings."""
    required={'forecast_source','forecast_retrieved_at','forecast_input_time','prediction_for',
              'storm_probability','decision_threshold','temperature_c','dewpoint_c',
              'pressure_msl_hpa','precipitation_mm','cape','wind_gust_ms','latitude','longitude'}
    if len(data)!=1 or not required.issubset(data.columns):
        fail('Expected one complete prediction row.')
    row=data.iloc[0]
    try:
        values={k:float(row[k]) for k in required if k not in {
            'forecast_source','forecast_retrieved_at','forecast_input_time','prediction_for'}}
        times={k:pd.Timestamp(row[k]) for k in ['prediction_for','forecast_input_time','forecast_retrieved_at']}
        if any(pd.isna(t) or t.tzinfo is None for t in times.values()):
            fail('Prediction timestamps require explicit timezones.')
        times={k:t.tz_convert('UTC') for k,t in times.items()}
    except (ValueError,TypeError,OverflowError):
        fail('Invalid prediction values or timestamps.')
    if not all(math.isfinite(v) for v in values.values()):
        fail('Nonfinite forecast/model values; no SMS sent.')
    probability=values['storm_probability']
    if not (0<=probability<=1 and abs(values['decision_threshold']-.35)<1e-9):
        fail('Invalid probability or unexpected threshold; expected 35%.')
    if str(row['forecast_source'])!='Open-Meteo ECMWF':
        fail('Unexpected forecast source; only genuine ECMWF output accepted.')
    if values['precipitation_mm']<0 or values['cape']<0 or values['wind_gust_ms']<0 or values['pressure_msl_hpa']<=0:
        fail('Invalid physical forecast values; no SMS sent.')
    if not (math.isclose(values['latitude'],-30.30,abs_tol=1e-6) and math.isclose(values['longitude'],28.80,abs_tol=1e-6)):
        fail('Unexpected forecast location; no SMS sent.')
    retrieved=times['forecast_retrieved_at']
    if not (max(started-timedelta(seconds=2),now-timedelta(minutes=20))<=retrieved<=now+timedelta(minutes=2)):
        fail('Forecast was not freshly retrieved by this run; saved result rejected.')
    forecast_time=times['prediction_for']
    if times['forecast_input_time']!=now.floor('h') or forecast_time!=times['forecast_input_time']+timedelta(hours=1) or forecast_time<=now:
        fail('Expired or invalid next-hour forecast target.')
    return row,probability,forecast_time


def manual_connectivity_test():
    """Explicit Actions dispatch only; durable run reservation prevents rerun SMS."""
    if (os.getenv('GITHUB_ACTIONS', '').lower() != 'true'
            or os.getenv('GITHUB_EVENT_NAME') != 'workflow_dispatch'
            or os.getenv('SMS_TEST_CONFIRMED', '').lower() != 'true'):
        fail('Connectivity SMS requires an explicitly confirmed manual Actions dispatch.')
    run_id = os.getenv('GITHUB_RUN_ID', '')
    if not run_id.isdigit() or not REPO or not TOKEN:
        fail('Connectivity SMS requires GitHub run identity and ledger access.')
    from sms_alert import sms_is_configured, _get_recipients, send_test_sms
    if not sms_is_configured() or len(_get_recipients()) != 1:
        fail('Connectivity SMS requires valid Twilio settings and exactly one verified trial recipient.')
    # Separate namespace from forecast-hour warnings; same run ID across reruns.
    issue = reserve_hour('CONNECTIVITY-TEST-RUN-' + run_id)
    if issue is None:
        print('Connectivity test already reserved for this run; no repeat SMS.')
        return
    try:
        result = send_test_sms()
        status = 'test_sent' if result.get('status') == 'test_sent' and result.get('sent') else 'failed_or_uncertain'
        report(issue, f'Connectivity test: **{status}**. NO WEATHER WARNING. Review Twilio Console and confirm handset receipt.')
        if status != 'test_sent':
            fail('Connectivity submission failed or uncertain; review Twilio before a new manual dispatch.')
        print('Connectivity SMS submitted: NO WEATHER WARNING. Delivery not confirmed; check your phone.')
    except Exception:
        fail('Connectivity test failed after reservation; no automatic retry. Review Twilio and the reservation privately.')


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__)
    mode=parser.add_mutually_exclusive_group()
    mode.add_argument('--dry-run',action='store_true',help='Retrieve and predict; never send SMS or write GitHub issues (default).')
    mode.add_argument('--live',action='store_true',help='Requires ENABLE_REAL_SMS=true and the serialized Actions workflow.')
    mode.add_argument('--test-sms',action='store_true',help='Confirmed manual Actions connectivity SMS only; no forecast or storm warning.')
    args=parser.parse_args(argv)
    if args.test_sms:
        manual_connectivity_test()
        return
    live=args.live and os.getenv('ENABLE_REAL_SMS','').strip().lower()=='true'
    if args.live and not live:
        fail('Live activation disabled. Use --dry-run; no SMS sent.')
    if live and os.getenv('GITHUB_ACTIONS','').lower()!='true':
        fail('Live submission requires the serialized GitHub Actions workflow.')
    print('Mode:', 'LIVE' if live else 'DRY RUN (no SMS, no GitHub ledger writes)')
    started=pd.Timestamp.now(tz='UTC')
    try:
        subprocess.run([sys.executable, str(BASE / '12_live_forecast_and_predict.py')],
                       cwd=BASE, check=True, timeout=240,capture_output=True,text=True)
    except (OSError,subprocess.SubprocessError):
        fail('Live forecast/model execution failed; saved predictions are not used for SMS.')
    if not PREDICTION.is_file():
        fail('Forecast script did not produce a prediction CSV.')
    try:
        data=pd.read_csv(PREDICTION)
    except (OSError,ValueError,pd.errors.ParserError):
        fail('Prediction CSV unreadable; no warning submitted.')
    row,probability,forecast_time=validate_prediction(data,started,pd.Timestamp.now(tz='UTC'))
    threshold=.35
    print(f'Actual prediction: {probability:.2%}, threshold: 35%, target: {forecast_time.tz_convert("Africa/Johannesburg"):%Y-%m-%d %H:%M SAST}')
    if probability < threshold:
        print('Below threshold: no warning.')
        return
    if not live:
        print('DRY RUN: threshold reached; would reserve warning and submit SMS. Nothing sent.')
        return
    # No sending without durable ledger and explicit live activation.
    if not REPO or not TOKEN:
        fail('Live mode requires GitHub repository and token.')
    from sms_alert import sms_is_configured, send_storm_sms
    if not sms_is_configured():
        fail('Twilio credentials/recipients missing; no SMS sent.')
    key = 'REAL-SHORT-V1-' + forecast_time.floor('h').isoformat()
    issue = reserve_hour(key)
    if issue is None:
        print('Already reserved this prediction hour; no duplicate SMS.')
        return
    print('Reserved warning hour in GitHub issue #', issue)
    try:
        result = send_storm_sms(
            prediction_for=forecast_time.isoformat(), storm_probability=probability,
            threshold=threshold, temperature_c=float(row['temperature_c']),
            precipitation_mm=float(row['precipitation_mm']),
            cape=float(row['cape']), wind_gust_ms=float(row['wind_gust_ms']),
            location='Matatiele')
        status = result.get('status', 'unknown')
        if status not in {'sent','partial','duplicate','failed','not_configured','not_required'}:
            status='unknown'
        # Never publish phone numbers, message bodies or Twilio secrets to issues.
        report(issue, f'SMS submission status: **{status}**. Check Twilio Console for delivery.')
        if status not in ('sent', 'duplicate'):
            fail(f'SMS submission unsuccessful: {status}; inspect Twilio logs before manual retry.')
        print('SMS submission status:', status, '(delivery not confirmed)')
    except Exception:
        try:
            report(issue, 'Worker failed after reservation. Manual review required; no automatic retry.')
        except Exception:
            pass
        fail('SMS submission/reporting failed after reservation; manual review required. No automatic retry.')


if __name__ == '__main__':
    try:
        main()
    except WorkerError as exc:
        print('ERROR:', str(exc), file=sys.stderr)
        sys.exit(1)
    except Exception:
        print('ERROR: Unexpected worker failure. No automatic retry; review configuration privately.',file=sys.stderr)
        sys.exit(1)
