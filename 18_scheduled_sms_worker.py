"""Scheduled Beta SMS worker. Default: dry-run, no SMS.

Uses a GitHub Issue as a durable per-hour reservation, preventing repeat sends
across ephemeral GitHub Actions runners. Issues permission is required in live mode.
A reservation is not a delivery receipt. Review failed runs manually.

Every execution also writes a sanitised run record (run_record.py). Recording is
monitoring only: it never changes a decision, an exit code or an SMS outcome.
"""
import argparse
import hashlib
import math
import re
import os
import subprocess
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import NoReturn
from urllib.parse import quote

import pandas as pd
import requests

try:  # Monitoring must never stop the worker from running.
    import run_record as _run_record
except Exception:  # pragma: no cover - exercised by test_missing_monitoring_module
    _run_record = None

BASE = Path(__file__).resolve().parent
PREDICTION = BASE / 'outputs' / 'model_live' / 'live_forecast_prediction.csv'
REPO = os.getenv('GITHUB_REPOSITORY', '')
TOKEN = os.getenv('GH_TOKEN', '')
API = 'https://api.github.com'
WARNING_THRESHOLD = .35
NOT_APPLICABLE_ = 'not_applicable'
RECORD = {}


class WorkerError(RuntimeError):
    """Credential-free diagnostic safe to print in Actions logs."""

    def __init__(self, message, category='unexpected_internal_error', detail=''):
        super().__init__(message)
        self.category = category
        self.detail = detail


def fail(message: str, category: str = 'unexpected_internal_error', detail: str = '') -> NoReturn:
    raise WorkerError(message, category, detail)


def _note(**fields):
    """Update the run record; monitoring only, never raises."""
    try:
        RECORD.update(fields)
    except Exception:
        pass


def github(method, endpoint, conflict_ok=False, **kwargs):
    if not re.fullmatch(r'[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+', REPO) or not TOKEN:
        fail('GITHUB_REPOSITORY and GH_TOKEN are required for live SMS.', 'configuration_failure', 'github_identity_missing')
    try:
        response = requests.request(
            method, f'{API}/repos/{REPO}/{endpoint}', timeout=(10,25),
            headers={'Authorization': f'Bearer {TOKEN}',
                     'Accept': 'application/vnd.github+json',
                     'X-GitHub-Api-Version': '2022-11-28'}, **kwargs)
        if conflict_ok and response.status_code == 422 and _already_exists(response):
            return {'_conflict': True}
        response.raise_for_status()
        if method == 'DELETE' and response.status_code == 204:
            return {}
        return response.json()
    except (requests.RequestException, ValueError):
        fail('GitHub ledger unavailable; submission stopped. Check permissions and service availability.',
             'duplicate_prevention_failure', 'ledger_unavailable')


def _already_exists(response):
    try:
        return any(isinstance(e, dict) and e.get('code') == 'already_exists' for e in response.json().get('errors', []))
    except Exception:
        return False


def lock_label_name(key):
    """Deterministic label name (GitHub limit: 50 characters) for one reservation key."""
    name = f'sms-lock:{key}'
    return name if len(name) <= 50 else 'sms-lock:' + hashlib.sha256(key.encode('utf-8')).hexdigest()[:40]


LOCK_GENERATIONS = 3  # bounded takeovers of abandoned locks per forecast hour
_HOLDER = re.compile(r'\brun=(\d{1,20}) attempt=(\d{1,6})\b')


def lock_description():
    """Label description (GitHub max 100 characters) naming the run that holds the lock."""
    run_id, attempt = os.getenv('GITHUB_RUN_ID', ''), os.getenv('GITHUB_RUN_ATTEMPT', '')
    holder = f' run={run_id} attempt={attempt}' if run_id.isdigit() and attempt.isdigit() else ''
    return f'Duplicate-SMS lock for one forecast hour. Do not delete.{holder}'


def lock_holder_state(key):
    """'finished' only when the run named in the lock has provably ended; else 'active' or 'unknown'.

    A finished holder can no longer create a ledger issue or send an SMS. Any doubt
    (old-format lock, API or permission failure) returns 'unknown', which keeps suppression.
    """
    try:
        label = github('GET', 'labels/' + quote(lock_label_name(key), safe=''))
        match = _HOLDER.search(str(label.get('description') or '')) if isinstance(label, dict) else None
        if not match:
            return 'unknown'
        holder_run, holder_attempt = match.group(1), int(match.group(2))
        if holder_run == os.getenv('GITHUB_RUN_ID', ''):
            # Attempts of one run execute one after another; only an earlier attempt can have ended.
            current = os.getenv('GITHUB_RUN_ATTEMPT', '')
            return 'finished' if current.isdigit() and holder_attempt < int(current) else 'active'
        run = github('GET', f'actions/runs/{holder_run}')
        if not isinstance(run, dict) or not run.get('status'):
            return 'unknown'
        return 'finished' if run['status'] == 'completed' else 'active'
    except Exception:
        return 'unknown'


def acquire_reservation_lock(key):
    """Atomic reservation: GitHub label names are unique per repository.

    'created' -> this run holds the lock; 'already_exists' -> another run reserved this key.
    'unavailable'/'unverified' -> the lock could not be confirmed; the caller falls back to
    the issue ledger (previous behaviour).
    """
    name = lock_label_name(key)
    try:
        result = github('POST', 'labels', conflict_ok=True, json={
            'name': name, 'color': 'ededed', 'description': lock_description()})
    except Exception:
        return 'unavailable'
    if isinstance(result, dict) and result.get('_conflict'):
        return 'already_exists'
    if isinstance(result, dict) and result.get('name') == name:
        return 'created'
    return 'unverified'


def release_reservation_lock(key):
    """Best effort, only after issue creation failed and before any SMS: lets a later run retry.

    Safe if the failed POST did create the issue, because later runs find it by title.
    Returns 'released' or 'release_failed' (a later run may then recover the lock once
    this run has ended; see lock_holder_state).
    """
    try:
        github('DELETE', 'labels/' + quote(lock_label_name(key), safe=''))
        return 'released'
    except Exception:
        return 'release_failed'


def ledger_has(title):
    # List all issues, including closed; a closed reservation must not trigger resends.
    page = 1
    while True:
        rows = github('GET', f'issues?state=all&sort=created&direction=asc&per_page=100&page={page}')
        if not isinstance(rows,list) or any(not isinstance(row,dict) for row in rows):
            fail('Invalid ledger response; no warning submitted.', 'duplicate_prevention_failure', 'ledger_response_invalid')
        if any(row.get('title') == title and 'pull_request' not in row for row in rows):
            return True
        if len(rows) < 100:
            return False
        page += 1


def reserve_hour(key):
    # Live runs must use the same Actions concurrency group. Issue creation is
    # not atomic outside that serialized workflow; the label lock adds atomicity.
    # Never retry an uncertain POST.
    title = f'[SMS-LEDGER] {key}'
    if ledger_has(title):
        _note(reservation_lock='not_attempted')
        return None
    for generation in range(1, LOCK_GENERATIONS + 1):
        lock_key = key if generation == 1 else f'{key}#gen{generation}'
        lock = acquire_reservation_lock(lock_key)
        if lock != 'already_exists':
            break
        # An SMS is only ever sent after the ledger issue exists. So a lock whose holder
        # run has ended, with still no issue, was abandoned before any SMS: the next
        # generation's label (again atomic) lets exactly one later run take over.
        holder = lock_holder_state(lock_key)
        if holder != 'finished':
            _note(reservation_lock='already_exists' if holder == 'active' else 'held_holder_unknown')
            return None  # a concurrent run may hold this key, or we cannot prove otherwise
        if ledger_has(title):  # re-check after the holder ended: it may have reserved first
            _note(reservation_lock='already_exists')
            return None
    else:
        _note(reservation_lock='generations_exhausted')
        return None
    _note(reservation_lock='recovered' if generation > 1 and lock == 'created' else lock)
    try:
        issue = github('POST', 'issues', json={
            'title': title,
            'body': ('Automated warning reservation for one forecast hour. '
                     'Do not delete this issue: it prevents duplicate SMS sends. '
                     'A reservation does not prove delivery.'),
        })
    except WorkerError:
        if lock == 'created':
            _note(reservation_lock=release_reservation_lock(lock_key))
        raise
    if not isinstance(issue,dict) or not isinstance(issue.get('number'),int):
        fail('Reservation confirmation invalid; no SMS submitted. Review ledger manually.',
             'duplicate_prevention_failure', 'reservation_unconfirmed')
    return issue['number']


def report(issue_number, message):
    github('POST', f'issues/{issue_number}/comments', json={'body': message})


def validate_prediction(data, started, now):
    """Only fresh, genuine, finite next-hour outputs are eligible for warnings."""
    required={'forecast_source','forecast_retrieved_at','forecast_input_time','prediction_for',
              'storm_probability','decision_threshold','temperature_c','dewpoint_c',
              'pressure_msl_hpa','precipitation_mm','cape','wind_gust_ms','latitude','longitude'}
    if len(data)!=1 or not required.issubset(data.columns):
        fail('Expected one complete prediction row.', 'prediction_output_failure', 'prediction_row_incomplete')
    row=data.iloc[0]
    try:
        values={k:float(row[k]) for k in required if k not in {
            'forecast_source','forecast_retrieved_at','forecast_input_time','prediction_for'}}
        times={k:pd.Timestamp(row[k]) for k in ['prediction_for','forecast_input_time','forecast_retrieved_at']}
        if any(pd.isna(t) or t.tzinfo is None for t in times.values()):
            fail('Prediction timestamps require explicit timezones.', 'invalid_model_output', 'timestamps_without_timezone')
        times={k:t.tz_convert('UTC') for k,t in times.items()}
    except (ValueError,TypeError,OverflowError):
        fail('Invalid prediction values or timestamps.', 'invalid_model_output', 'values_not_parseable')
    try:  # monitoring only; argument evaluation must not affect validation
        _note(forecast_retrieved_utc=times['forecast_retrieved_at'].isoformat(),
              forecast_input_utc=times['forecast_input_time'].isoformat(),
              prediction_target_utc=times['prediction_for'].isoformat(),
              forecast_freshness_seconds=(now-times['forecast_retrieved_at']).total_seconds(),
              unvalidated_probability=values.get('storm_probability'))
    except Exception:
        pass
    if not all(math.isfinite(v) for v in values.values()):
        fail('Nonfinite forecast/model values; no SMS sent.', 'invalid_model_output', 'nonfinite_values')
    probability=values['storm_probability']
    if not (0<=probability<=1 and abs(values['decision_threshold']-.35)<1e-9):
        fail('Invalid probability or unexpected threshold; expected 35%.', 'invalid_model_output', 'probability_or_threshold_invalid')
    if str(row['forecast_source'])!='Open-Meteo ECMWF':
        fail('Unexpected forecast source; only genuine ECMWF output accepted.', 'invalid_forecast_data', 'unexpected_source')
    if values['precipitation_mm']<0 or values['cape']<0 or values['wind_gust_ms']<0 or values['pressure_msl_hpa']<=0:
        fail('Invalid physical forecast values; no SMS sent.', 'invalid_forecast_data', 'physical_values_invalid')
    if not (math.isclose(values['latitude'],-30.30,abs_tol=1e-6) and math.isclose(values['longitude'],28.80,abs_tol=1e-6)):
        fail('Unexpected forecast location; no SMS sent.', 'invalid_forecast_data', 'unexpected_location')
    retrieved=times['forecast_retrieved_at']
    if not (max(started-timedelta(seconds=2),now-timedelta(minutes=20))<=retrieved<=now+timedelta(minutes=2)):
        fail('Forecast was not freshly retrieved by this run; saved result rejected.', 'stale_forecast', 'not_retrieved_by_this_run')
    forecast_time=times['prediction_for']
    if times['forecast_input_time']!=now.floor('h') or forecast_time!=times['forecast_input_time']+timedelta(hours=1) or forecast_time<=now:
        fail('Expired or invalid next-hour forecast target.', 'stale_forecast', 'target_expired_or_invalid')
    return row,probability,forecast_time


def manual_connectivity_test():
    """Explicit Actions dispatch only; durable run reservation prevents rerun SMS."""
    _note(mode='connectivity_test', warning_decision='not_applicable', model_loading=NOT_APPLICABLE_,
          forecast_retrieval=NOT_APPLICABLE_, forecast_response_validation=NOT_APPLICABLE_,
          model_inference=NOT_APPLICABLE_, prediction_output=NOT_APPLICABLE_,
          prediction_validation=NOT_APPLICABLE_, freshness_status=NOT_APPLICABLE_)
    if (os.getenv('GITHUB_ACTIONS', '').lower() != 'true'
            or os.getenv('GITHUB_EVENT_NAME') != 'workflow_dispatch'
            or os.getenv('SMS_TEST_CONFIRMED', '').lower() != 'true'):
        fail('Connectivity SMS requires an explicitly confirmed manual Actions dispatch.', 'configuration_failure', 'dispatch_not_confirmed')
    if os.getenv('RUN_TRIGGER_SOURCE', '').strip() == 'external_scheduler':
        fail('Connectivity SMS cannot be started by the external scheduler.', 'configuration_failure', 'external_trigger_not_allowed')
    run_id = os.getenv('GITHUB_RUN_ID', '')
    if not run_id.isdigit() or not REPO or not TOKEN:
        fail('Connectivity SMS requires GitHub run identity and ledger access.', 'configuration_failure', 'github_identity_missing')
    from sms_alert import sms_is_configured, _get_recipients, send_test_sms
    if not sms_is_configured() or len(_get_recipients()) != 1:
        fail('Connectivity SMS requires valid Twilio settings and exactly one verified trial recipient.',
             'configuration_failure', 'sms_configuration_invalid')
    # Separate namespace from forecast-hour warnings; same run ID across reruns.
    _note(duplicate_prevention='failed')
    issue = reserve_hour('CONNECTIVITY-TEST-RUN-' + run_id)
    if issue is None:
        _note(duplicate_prevention='already_reserved', sms_submission='not_attempted', sms_note='already_reserved')
        print('Connectivity test already reserved for this run; no repeat SMS.')
        return
    _note(duplicate_prevention='reserved', ledger_issue_number=issue, sms_submission='exception')
    try:
        result = send_test_sms()
        status = 'test_sent' if result.get('status') == 'test_sent' and result.get('sent') else 'failed_or_uncertain'
        _note(sms_submission=status, ledger_report='failed')
        report(issue, f'Connectivity test: **{status}**. NO WEATHER WARNING. Review Twilio Console and confirm handset receipt.')
        _note(ledger_report='ok')
        if status != 'test_sent':
            fail('Connectivity submission failed or uncertain; review Twilio before a new manual dispatch.')
        print('Connectivity SMS submitted: NO WEATHER WARNING. Delivery not confirmed; check your phone.')
    except Exception:
        fail('Connectivity test failed after reservation; no automatic retry. Review Twilio and the reservation privately.',
             'sms_provider_failure' if RECORD.get('ledger_report') != 'failed' else 'ledger_report_failure',
             'connectivity_test_failed')


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
    _note(mode='live' if live else ('live_requested' if args.live else 'dry_run'), warning_threshold=WARNING_THRESHOLD)
    if args.live and not live:
        fail('Live activation disabled. Use --dry-run; no SMS sent.', 'configuration_failure', 'live_not_enabled')
    if live and os.getenv('GITHUB_ACTIONS','').lower()!='true':
        fail('Live submission requires the serialized GitHub Actions workflow.', 'configuration_failure', 'not_in_actions')
    print('Mode:', 'LIVE' if live else 'DRY RUN (no SMS, no GitHub ledger writes)')
    started=pd.Timestamp.now(tz='UTC')
    try:
        subprocess.run([sys.executable, str(BASE / '12_live_forecast_and_predict.py')],
                       cwd=BASE, check=True, timeout=240,capture_output=True,text=True)
    except (OSError,subprocess.SubprocessError) as exc:
        stage = _classify_forecast_failure(exc)
        fail(f"Live forecast/model execution failed ({stage.get('error_category', 'unexpected_internal_error')}: "
             f"{stage.get('error_detail', 'unclassified')}); saved predictions are not used for SMS.",
             stage.get('error_category', 'unexpected_internal_error'), stage.get('error_detail', 'unclassified'))
    _note(model_loading='ok', forecast_retrieval='ok', forecast_response_validation='ok', model_inference='ok')
    if not PREDICTION.is_file():
        fail('Forecast script did not produce a prediction CSV.', 'prediction_output_failure', 'prediction_csv_missing')
    try:
        data=pd.read_csv(PREDICTION)
    except (OSError,ValueError,pd.errors.ParserError):
        fail('Prediction CSV unreadable; no warning submitted.', 'prediction_output_failure', 'prediction_csv_unreadable')
    _note(prediction_output='ok', prediction_validation='rejected')
    row,probability,forecast_time=validate_prediction(data,started,pd.Timestamp.now(tz='UTC'))
    _note(prediction_validation='passed', freshness_status='fresh', storm_probability=probability, unvalidated_probability=None)
    threshold=WARNING_THRESHOLD
    print(f'Actual prediction: {probability:.2%}, threshold: 35%, target: {forecast_time.tz_convert("Africa/Johannesburg"):%Y-%m-%d %H:%M SAST}')
    if probability < threshold:
        _note(warning_decision='below_threshold', duplicate_prevention=NOT_APPLICABLE_,
              sms_submission=NOT_APPLICABLE_, ledger_report=NOT_APPLICABLE_)
        print('Below threshold: no warning.')
        return
    _note(warning_decision='warning_eligible')
    if not live:
        _note(sms_note='dry_run')
        print('DRY RUN: threshold reached; would reserve warning and submit SMS. Nothing sent.')
        return
    # No sending without durable ledger and explicit live activation.
    if not REPO or not TOKEN:
        fail('Live mode requires GitHub repository and token.', 'configuration_failure', 'github_identity_missing')
    from sms_alert import sms_is_configured, send_storm_sms
    if not sms_is_configured():
        fail('Twilio credentials/recipients missing; no SMS sent.', 'configuration_failure', 'sms_configuration_missing')
    key = 'REAL-SHORT-V1-' + forecast_time.floor('h').isoformat()
    _note(duplicate_prevention='failed')
    issue = reserve_hour(key)
    if issue is None:
        _note(duplicate_prevention='already_reserved', sms_note='duplicate_suppressed', ledger_report=NOT_APPLICABLE_)
        print('Already reserved this prediction hour; no duplicate SMS.')
        return
    _note(duplicate_prevention='reserved', ledger_issue_number=issue, sms_submission='exception')
    print('Reserved warning hour in GitHub issue #', issue)
    result_status = None
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
        result_status = status
        _note(sms_submission=status, ledger_report='failed')
        # Never publish phone numbers, message bodies or Twilio secrets to issues.
        report(issue, f'SMS submission status: **{status}**. Check Twilio Console for delivery.')
        _note(ledger_report='ok')
        if status not in ('sent', 'duplicate'):
            fail(f'SMS submission unsuccessful: {status}; inspect Twilio logs before manual retry.')
        print('SMS submission status:', status, '(delivery not confirmed)')
    except Exception:
        try:
            report(issue, 'Worker failed after reservation. Manual review required; no automatic retry.')
        except Exception:
            pass
        if result_status is None:
            category, detail = 'sms_provider_failure', 'submission_exception'
        elif RECORD.get('ledger_report') == 'failed':
            category, detail = 'ledger_report_failure', 'status_comment_failed'
        else:
            category, detail = 'sms_provider_failure', f'submission_status_{result_status}'
        fail('SMS submission/reporting failed after reservation; manual review required. No automatic retry.',
             category, detail)


def _classify_forecast_failure(exc):
    """Monitoring only: classify a failed forecast subprocess without exposing its output."""
    try:
        if _run_record is None:
            return {}
        stage = _run_record.classify_forecast_failure(
            getattr(exc, 'stdout', None), getattr(exc, 'stderr', None),
            timed_out=isinstance(exc, subprocess.TimeoutExpired),
            launch_error=isinstance(exc, OSError))
        _note(**stage)
        return stage
    except Exception:
        return {}


def _start_record():
    global RECORD
    try:
        RECORD = _run_record.new_record() if _run_record is not None else {}
    except Exception:
        RECORD = {}


def _finish_record(exit_code, elapsed, error=None):
    """Write the sanitised record. Never raises and never alters the exit code."""
    try:
        if _run_record is None:
            return None
        if error is not None:
            _note(error_category=getattr(error, 'category', 'unexpected_internal_error'),
                  error_detail=getattr(error, 'detail', ''),
                  error_message=str(error) if isinstance(error, WorkerError) else 'Unexpected worker failure.',
                  # Keep the forecast script's exception class if the classifier found one.
                  exception_type=RECORD.get('exception_type', '') if isinstance(error, WorkerError) else type(error).__name__)
        _note(finished_utc=_run_record.utc_now_iso(), duration_seconds=round(elapsed, 3), worker_exit_code=exit_code,
              outcome='completed' if exit_code == 0 else 'failed')
        if RECORD.get('prediction_validation') == 'rejected':
            # The freshness check is the last validation step; earlier rejections never reach it.
            _note(freshness_status='stale' if RECORD.get('error_category') == 'stale_forecast' else 'not_evaluated')
        path = _run_record.write_record(RECORD)
        clean = _run_record.sanitise_record(RECORD)
        print(f"RUN RECORD: outcome={clean.get('outcome')} category={clean.get('error_category')} "
              f"decision={clean.get('warning_decision')} sms={clean.get('sms_submission')} "
              f"file={'written' if path else 'NOT WRITTEN'}")
        if path is None:
            print('::warning::Run record could not be written (monitoring only; warning outcome unaffected).')
        return path
    except Exception:
        try:
            print('::warning::Run record failed (monitoring only; warning outcome unaffected).')
        except Exception:
            pass
        return None


def run(argv=None):
    """Entry point: identical messages and exit codes to the original __main__ block, plus a run record."""
    _start_record()
    clock = time.monotonic()
    exit_code, error = 1, None
    try:
        main(argv)
        exit_code = 0
    except WorkerError as exc:
        error = exc
        print('ERROR:', str(exc), file=sys.stderr)
    except SystemExit as exc:  # argparse; propagate unchanged, record the real code
        exit_code = exc.code if isinstance(exc.code, int) else 1
        error = WorkerError('Worker exited before execution (command-line arguments).',
                            'configuration_failure', 'invalid_arguments') if exit_code else None
        raise
    except Exception as exc:
        error = exc
        print('ERROR: Unexpected worker failure. No automatic retry; review configuration privately.',file=sys.stderr)
    finally:
        _finish_record(exit_code, time.monotonic() - clock, error)
    return exit_code


if __name__ == '__main__':
    sys.exit(run())
