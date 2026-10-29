"""R1 operational run records: classification, isolation and redaction.

All external services are mocked: no forecast request, no GitHub call and no SMS.
Dummy credentials override any real environment values for the duration of each test.
"""
import contextlib
import importlib.util
import io
import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest
import urllib.error
from unittest.mock import Mock, patch

import pandas as pd

import run_record
from test_scheduled_sms_worker import load_worker

ROOT = Path(__file__).resolve().parents[1]
SCRIPT_12 = (ROOT / '12_live_forecast_and_predict.py').read_text(encoding='utf-8')
DUMMY_SID = 'AC' + '1234abcd' * 4
DUMMY_TOKEN = 'dummy-auth-token-value-987'
DUMMY_NUMBER = '+15555550101'
DUMMY_GH = 'ghp_' + 'A1b2C3d4' * 5

# Output fragments exactly as printed by script 12 (drift-checked below).
OUT_MODEL_OK = ('Checking live-compatible model files...\nAll live-compatible model files found.\n'
                'Loading live-compatible Random Forest...\nRandom Forest loaded successfully.\n')
OUT_REQUEST = 'Requesting live ECMWF forecast from Open-Meteo...\nRequest URL: https://api.open-meteo.com/v1/ecmwf\n'
OUT_DOWNLOADED = OUT_MODEL_OK + OUT_REQUEST + 'HTTP status: 200\nLive forecast downloaded successfully.\n'
OUT_FEATURES = OUT_DOWNLOADED + '\nFeatures prepared for model: 29\n'


def load_publisher():
    spec = importlib.util.spec_from_file_location('publisher', ROOT / '19_publish_run_record.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def failed_process(stdout='', stderr=''):
    return subprocess.CalledProcessError(1, ['python', '12_live_forecast_and_predict.py'], output=stdout, stderr=stderr)


class RecordHarness(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='run-record-test-', dir=ROOT / 'outputs')
        self.addCleanup(self.temp.cleanup)
        self.record_file = Path(self.temp.name) / 'run_record.json'
        self.env = patch.dict(os.environ, {
            'ENABLE_REAL_SMS': 'true', 'GITHUB_ACTIONS': 'true', 'GITHUB_REPOSITORY': 'example/research',
            'GH_TOKEN': DUMMY_GH, 'GITHUB_TOKEN': DUMMY_GH, 'GITHUB_EVENT_NAME': 'schedule',
            'GITHUB_RUN_ID': '40832590994', 'GITHUB_RUN_NUMBER': '101', 'GITHUB_RUN_ATTEMPT': '1',
            'GITHUB_SHA': '4b06a95' + '0' * 33, 'RUN_RECORD_FILE': str(self.record_file),
            'TWILIO_ACCOUNT_SID': DUMMY_SID, 'TWILIO_AUTH_TOKEN': DUMMY_TOKEN,
            'TWILIO_FROM_NUMBER': '+15555550100', 'ALERT_TO_NUMBERS': DUMMY_NUMBER,
            'SMS_TEST_CONFIRMED': 'false', 'RUN_RECORD_PUBLISH': ''})
        self.env.start(); self.addCleanup(self.env.stop)
        self.now = pd.Timestamp.now(tz='UTC')
        # One clock per test: the worker sees the same instant the fixture was built from,
        # so a run that straddles an hour boundary cannot make the target look expired.
        clock = patch.object(pd.Timestamp, 'now', return_value=self.now)
        clock.start(); self.addCleanup(clock.stop)
        self.row = {'forecast_source': 'Open-Meteo ECMWF', 'forecast_retrieved_at': self.now.isoformat(),
                    'forecast_input_time': self.now.floor('h').isoformat(),
                    'prediction_for': (self.now.floor('h') + pd.Timedelta(hours=1)).isoformat(),
                    'storm_probability': .10, 'decision_threshold': .35, 'temperature_c': 20, 'dewpoint_c': 15,
                    'pressure_msl_hpa': 1012, 'precipitation_mm': 1, 'cape': 500, 'wind_gust_ms': 10,
                    'latitude': -30.30, 'longitude': 28.80}

    def run_worker(self, args=('--live',), probability=None, rows=None, subprocess_effect=None, worker=None):
        worker = worker or load_worker()
        row = dict(self.row, **({} if probability is None else {'storm_probability': probability}))
        out, err = io.StringIO(), io.StringIO()
        with patch.object(worker.subprocess, 'run', side_effect=subprocess_effect) as inference, \
             patch.object(worker.pd, 'read_csv', return_value=pd.DataFrame(rows or [row])) as read, \
             patch.object(worker.PREDICTION.__class__, 'is_file', return_value=True), \
             contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            code = worker.run(list(args))
        record = json.loads(self.record_file.read_text(encoding='utf-8')) if self.record_file.exists() else None
        return {'worker': worker, 'code': code, 'record': record, 'stdout': out.getvalue(),
                'stderr': err.getvalue(), 'inference': inference, 'read_csv': read}

    def assert_no_secrets(self, text):
        for secret in (DUMMY_SID, DUMMY_TOKEN, DUMMY_NUMBER, DUMMY_GH, '+15555550100'):
            self.assertNotIn(secret, text)


class WarningPathRecords(RecordHarness):
    def test_successful_forecast_below_threshold(self):
        with patch('sms_alert.send_storm_sms') as send, patch('sms_alert.sms_is_configured', return_value=True):
            r = self.run_worker(probability=.10)
        rec = r['record']
        self.assertEqual(r['code'], 0); send.assert_not_called()
        self.assertEqual((rec['outcome'], rec['worker_exit_code'], rec['error_category']), ('completed', 0, 'none'))
        self.assertEqual((rec['mode'], rec['trigger'], rec['workflow_run_id'], rec['commit']), ('live', 'schedule', '40832590994', '4b06a95'))
        for key in ('model_loading', 'forecast_retrieval', 'forecast_response_validation', 'model_inference', 'prediction_output'):
            self.assertEqual(rec[key], 'ok', key)
        self.assertEqual((rec['prediction_validation'], rec['freshness_status']), ('passed', 'fresh'))
        self.assertAlmostEqual(rec['storm_probability'], .10); self.assertIsNone(rec['unvalidated_probability'])
        self.assertEqual(rec['warning_threshold'], .35)
        self.assertEqual(rec['warning_decision'], 'below_threshold')
        self.assertEqual((rec['duplicate_prevention'], rec['sms_submission'], rec['ledger_report']), ('not_applicable',) * 3)
        self.assertEqual(rec['forecast_input_utc'], self.now.floor('h').isoformat())
        self.assertGreaterEqual(rec['duration_seconds'], 0)

    def test_valid_forecast_above_threshold_is_submitted_once_and_recorded(self):
        worker = load_worker()
        with patch('sms_alert.sms_is_configured', return_value=True), \
             patch('sms_alert.send_storm_sms', return_value={'status': 'sent', 'sent': True}) as send, \
             patch.object(worker, 'reserve_hour', return_value=7) as reserve, patch.object(worker, 'report') as report:
            r = self.run_worker(probability=.40, worker=worker)
        rec = r['record']
        self.assertEqual(r['code'], 0); send.assert_called_once(); reserve.assert_called_once(); report.assert_called_once()
        self.assertEqual(send.call_args.kwargs['threshold'], .35)
        self.assertAlmostEqual(send.call_args.kwargs['storm_probability'], .40)
        self.assertEqual((rec['warning_decision'], rec['duplicate_prevention'], rec['ledger_issue_number']), ('warning_eligible', 'reserved', 7))
        self.assertEqual((rec['sms_submission'], rec['ledger_report'], rec['error_category']), ('sent', 'ok', 'none'))

    def test_decision_boundary_is_unchanged(self):
        for probability, should_send in [(.3499, False), (.35, True), (.3501, True)]:
            with self.subTest(probability=probability):
                worker = load_worker()
                with patch('sms_alert.sms_is_configured', return_value=True), \
                     patch('sms_alert.send_storm_sms', return_value={'status': 'sent', 'sent': True}) as send, \
                     patch.object(worker, 'reserve_hour', return_value=3), patch.object(worker, 'report'):
                    r = self.run_worker(probability=probability, worker=worker)
                self.assertEqual(send.called, should_send)
                self.assertEqual(r['record']['warning_decision'], 'warning_eligible' if should_send else 'below_threshold')

    def test_dry_run_eligible_never_reserves_or_sends(self):
        worker = load_worker()
        with patch('sms_alert.send_storm_sms') as send, patch.object(worker, 'github') as gh:
            r = self.run_worker(args=('--dry-run',), probability=.9, worker=worker)
        send.assert_not_called(); gh.assert_not_called()
        rec = r['record']
        self.assertEqual((r['code'], rec['mode'], rec['warning_decision']), (0, 'dry_run', 'warning_eligible'))
        self.assertEqual((rec['duplicate_prevention'], rec['sms_submission'], rec['sms_note']), ('not_attempted', 'not_attempted', 'dry_run'))


class FailureClassification(RecordHarness):
    def assert_failed_before_prediction(self, r):
        self.assertEqual(r['code'], 1)
        r['read_csv'].assert_not_called()
        self.assertEqual(r['record']['warning_decision'], 'not_evaluated')
        self.assertIsNone(r['record']['storm_probability'])
        self.assertEqual(r['record']['sms_submission'], 'not_attempted')

    def test_forecast_retrieval_failure(self):
        stdout = OUT_MODEL_OK + OUT_REQUEST + ('HTTP status: 503\n\nLive forecast request failed.\n'
                                               '503 Server Error: Service Unavailable for url: https://api.open-meteo.com/v1/ecmwf?latitude=-30.3')
        with patch('sms_alert.send_storm_sms') as send:
            r = self.run_worker(subprocess_effect=failed_process(stdout))
        send.assert_not_called(); self.assert_failed_before_prediction(r)
        rec = r['record']
        self.assertEqual((rec['error_category'], rec['error_detail'], rec['forecast_http_status']), ('forecast_retrieval_failure', 'http_503', 503))
        self.assertEqual((rec['model_loading'], rec['forecast_retrieval'], rec['model_inference']), ('ok', 'failed', 'not_attempted'))
        self.assertIn('forecast_retrieval_failure: http_503', r['stderr'])
        self.assertNotIn('open-meteo.com', json.dumps(rec))  # raw output never copied

    def test_undecodable_forecast_response(self):
        stderr = 'Traceback (most recent call last):\nrequests.exceptions.JSONDecodeError: Expecting value: line 1 column 1'
        r = self.run_worker(subprocess_effect=failed_process(OUT_MODEL_OK + OUT_REQUEST + 'HTTP status: 200\n', stderr))
        self.assert_failed_before_prediction(r)
        rec = r['record']
        self.assertEqual((rec['error_category'], rec['error_detail']), ('forecast_retrieval_failure', 'response_not_decodable'))
        self.assertEqual(rec['exception_type'], 'requests.exceptions.JSONDecodeError')

    def test_invalid_forecast_response(self):
        cases = [('ValueError: The selected forecast input hour is unavailable; no earlier row is substituted.', 'selected_hour_unavailable'),
                 ("ValueError: Open-Meteo response is missing:\n['cape']", 'variables_missing'),
                 ('ValueError: No previous-hour forecast found for 2026-10-29 06:00:00+00:00.', 'previous_hour_unavailable')]
        for stderr, detail in cases:
            with self.subTest(detail=detail):
                r = self.run_worker(subprocess_effect=failed_process(OUT_DOWNLOADED, 'Traceback (most recent call last):\n' + stderr))
                self.assert_failed_before_prediction(r)
                rec = r['record']
                self.assertEqual((rec['error_category'], rec['error_detail']), ('invalid_forecast_data', detail))
                self.assertEqual((rec['forecast_retrieval'], rec['forecast_response_validation'], rec['model_inference']), ('ok', 'failed', 'not_attempted'))

    def test_nonfinite_input_is_invalid_data_not_inference(self):
        r = self.run_worker(subprocess_effect=failed_process(OUT_FEATURES, 'ValueError: Nonfinite model input; prediction was not updated.'))
        rec = r['record']
        self.assertEqual((rec['error_category'], rec['model_inference']), ('invalid_forecast_data', 'not_attempted'))

    def test_stale_forecast(self):
        stale = dict(self.row, storm_probability=.40, forecast_retrieved_at=(self.now - pd.Timedelta(hours=1)).isoformat())
        with patch('sms_alert.send_storm_sms') as send:
            r = self.run_worker(rows=[stale])
        send.assert_not_called()
        rec = r['record']
        self.assertEqual((r['code'], rec['error_category'], rec['error_detail']), (1, 'stale_forecast', 'not_retrieved_by_this_run'))
        self.assertEqual((rec['prediction_validation'], rec['freshness_status'], rec['warning_decision']), ('rejected', 'stale', 'not_evaluated'))
        self.assertIsNone(rec['storm_probability'])
        self.assertAlmostEqual(rec['unvalidated_probability'], .40)  # genuine but rejected; labelled as such
        self.assertGreater(rec['forecast_freshness_seconds'], 3500)

    def test_model_loading_and_inference_failures(self):
        cases = [('Checking live-compatible model files...\nAll live-compatible model files found.\nLoading live-compatible Random Forest...\n',
                  "ModuleNotFoundError: No module named 'sklearn'", 'model_loading_failure', 'model_load_error', 'failed', 'not_attempted'),
                 ('Checking live-compatible model files...\n',
                  'FileNotFoundError: Required file not found:\n/home/runner/work/x/outputs/model_live/random_forest_live_model.pkl',
                  'model_loading_failure', 'model_artefact_missing', 'failed', 'not_attempted'),
                 (OUT_FEATURES, "AttributeError: 'RandomForestClassifier' object has no attribute 'monotonic_cst'",
                  'inference_failure', 'predict_proba_error', 'ok', 'failed')]
        for stdout, stderr, category, detail, loading, inference in cases:
            with self.subTest(detail=detail):
                r = self.run_worker(subprocess_effect=failed_process(stdout, 'Traceback (most recent call last):\n' + stderr))
                self.assert_failed_before_prediction(r)
                rec = r['record']
                self.assertEqual((rec['error_category'], rec['error_detail']), (category, detail))
                self.assertEqual((rec['model_loading'], rec['model_inference']), (loading, inference))
                self.assertNotIn('/home/runner', json.dumps(rec))

    def test_pipeline_timeout(self):
        r = self.run_worker(subprocess_effect=subprocess.TimeoutExpired(['python'], 240, output=OUT_MODEL_OK.encode()))
        self.assert_failed_before_prediction(r)
        self.assertEqual((r['record']['error_category'], r['record']['error_detail']), ('pipeline_timeout', 'forecast_script_timeout'))

    def test_sms_provider_failure(self):
        for outcome, status, detail in [({'status': 'failed', 'sent': False}, 'failed', 'submission_status_failed'),
                                        (RuntimeError(f'SECRET provider error for {DUMMY_NUMBER} {DUMMY_SID}'), 'exception', 'submission_exception')]:
            with self.subTest(status=status):
                worker = load_worker()
                with patch('sms_alert.sms_is_configured', return_value=True), \
                     patch('sms_alert.send_storm_sms', side_effect=[outcome] if isinstance(outcome, Exception) else None,
                           return_value=None if isinstance(outcome, Exception) else outcome) as send, \
                     patch.object(worker, 'reserve_hour', return_value=9), patch.object(worker, 'report') as report:
                    r = self.run_worker(probability=.40, worker=worker)
                rec = r['record']
                self.assertEqual(r['code'], 1); send.assert_called_once()
                self.assertEqual((rec['error_category'], rec['error_detail'], rec['sms_submission']), ('sms_provider_failure', detail, status))
                self.assertEqual(rec['duplicate_prevention'], 'reserved')
                self.assertGreaterEqual(report.call_count, 1)
                self.assert_no_secrets(json.dumps(rec) + r['stdout'] + r['stderr'])
                self.assertNotIn('SECRET', json.dumps(rec))

    def test_sent_sms_with_failed_ledger_comment_is_not_reported_as_unsent(self):
        worker = load_worker()
        with patch('sms_alert.sms_is_configured', return_value=True), \
             patch('sms_alert.send_storm_sms', return_value={'status': 'sent', 'sent': True}) as send, \
             patch.object(worker, 'reserve_hour', return_value=4), \
             patch.object(worker, 'report', side_effect=worker.WorkerError('ledger down', 'duplicate_prevention_failure')):
            r = self.run_worker(probability=.40, worker=worker)
        rec = r['record']
        self.assertEqual(r['code'], 1); send.assert_called_once()  # exit code unchanged from original behaviour
        self.assertEqual((rec['sms_submission'], rec['ledger_report'], rec['error_category']), ('sent', 'failed', 'ledger_report_failure'))

    def test_configuration_failure(self):
        with patch('sms_alert.sms_is_configured', return_value=False), patch('sms_alert.send_storm_sms') as send:
            r = self.run_worker(probability=.40)
        send.assert_not_called()
        self.assertEqual((r['code'], r['record']['error_category'], r['record']['error_detail']), (1, 'configuration_failure', 'sms_configuration_missing'))
        self.assertEqual(r['record']['duplicate_prevention'], 'not_attempted')


class DuplicatePrevention(RecordHarness):
    def test_duplicate_warning_is_suppressed_and_recorded(self):
        worker = load_worker()
        with patch('sms_alert.sms_is_configured', return_value=True), patch('sms_alert.send_storm_sms') as send, \
             patch.object(worker, 'reserve_hour', return_value=None):
            r = self.run_worker(probability=.40, worker=worker)
        send.assert_not_called()
        rec = r['record']
        self.assertEqual((r['code'], rec['duplicate_prevention'], rec['sms_submission'], rec['sms_note']),
                         (0, 'already_reserved', 'not_attempted', 'duplicate_suppressed'))

    def test_fresh_runners_share_ledger_and_send_once(self):
        ledger = []

        def github(method, endpoint, **kwargs):
            if method == 'GET':
                return list(ledger)
            if endpoint == 'issues':
                ledger.append({'number': len(ledger) + 1, 'title': kwargs['json']['title']}); return ledger[-1]
            return {}
        records = []
        with patch('sms_alert.sms_is_configured', return_value=True), \
             patch('sms_alert.send_storm_sms', return_value={'status': 'sent', 'sent': True}) as send:
            for _ in range(2):
                worker = load_worker()
                with patch.object(worker, 'github', side_effect=github):
                    records.append(self.run_worker(probability=.40, worker=worker)['record'])
        self.assertEqual(send.call_count, 1); self.assertEqual(len(ledger), 1)
        self.assertEqual([r['duplicate_prevention'] for r in records], ['reserved', 'already_reserved'])

    def test_ledger_failure_blocks_sms_and_is_classified(self):
        worker = load_worker()
        with patch('sms_alert.sms_is_configured', return_value=True), patch('sms_alert.send_storm_sms') as send, \
             patch.object(worker.requests, 'request', side_effect=worker.requests.ConnectionError('down')):
            r = self.run_worker(probability=.40, worker=worker)
        send.assert_not_called()
        rec = r['record']
        self.assertEqual((r['code'], rec['error_category'], rec['error_detail'], rec['duplicate_prevention']),
                         (1, 'duplicate_prevention_failure', 'ledger_unavailable', 'failed'))


class MonitoringIsolation(RecordHarness):
    def test_storage_failure_does_not_change_outcomes(self):
        blocker = Path(self.temp.name) / 'not-a-directory'
        blocker.write_text('x', encoding='utf-8')
        os.environ['RUN_RECORD_FILE'] = str(blocker / 'run_record.json')  # parent is a file: write must fail
        for probability, expected_sends in [(.10, 0), (.40, 1)]:
            with self.subTest(probability=probability):
                worker = load_worker()
                with patch('sms_alert.sms_is_configured', return_value=True), \
                     patch('sms_alert.send_storm_sms', return_value={'status': 'sent', 'sent': True}) as send, \
                     patch.object(worker, 'reserve_hour', return_value=2), patch.object(worker, 'report'):
                    r = self.run_worker(probability=probability, worker=worker)
                self.assertEqual(r['code'], 0); self.assertEqual(send.call_count, expected_sends)
                self.assertIn('Run record could not be written', r['stdout'])

    def test_monitoring_exceptions_do_not_change_outcomes(self):
        worker = load_worker()
        with patch.object(worker._run_record, 'write_record', side_effect=RuntimeError('boom')), \
             patch.object(worker._run_record, 'sanitise_record', side_effect=RuntimeError('boom')), \
             patch('sms_alert.sms_is_configured', return_value=True), \
             patch('sms_alert.send_storm_sms', return_value={'status': 'sent', 'sent': True}) as send, \
             patch.object(worker, 'reserve_hour', return_value=2), patch.object(worker, 'report'):
            r = self.run_worker(probability=.40, worker=worker)
        self.assertEqual(r['code'], 0); send.assert_called_once()
        with patch.object(worker._run_record, 'classify_forecast_failure', side_effect=RuntimeError('boom')):
            r = self.run_worker(subprocess_effect=failed_process('x'), worker=worker)
        self.assertEqual(r['code'], 1); r['read_csv'].assert_not_called()

    def test_worker_runs_without_monitoring_module(self):
        worker = load_worker(); worker._run_record = None
        with patch('sms_alert.sms_is_configured', return_value=True), \
             patch('sms_alert.send_storm_sms', return_value={'status': 'sent', 'sent': True}) as send, \
             patch.object(worker, 'reserve_hour', return_value=2), patch.object(worker, 'report'):
            r = self.run_worker(probability=.40, worker=worker)
        self.assertEqual(r['code'], 0); send.assert_called_once(); self.assertIsNone(r['record'])

    def test_publisher_failures_never_fail_the_step(self):
        publisher = load_publisher()
        self.record_file.write_text(json.dumps(run_record.new_record()), encoding='utf-8')
        env = dict(os.environ, RUN_RECORD_PUBLISH='true')
        for error in (urllib.error.URLError('down'), OSError('disk'), RuntimeError('unexpected')):
            with self.subTest(error=type(error).__name__):
                out = io.StringIO()
                with contextlib.redirect_stdout(out):
                    self.assertEqual(publisher.main(env, request=Mock(side_effect=error)), 0)
                self.assertIn('::warning::', out.getvalue())


class PublisherBehaviour(RecordHarness):
    def fake_github(self, issues):
        calls = []

        def request(method, url, token, payload=None):
            calls.append((method, url, payload))
            if method == 'GET':
                return list(issues)
            if url.endswith('/issues'):
                issues.append({'number': 50, 'title': payload['title']}); return issues[-1]
            return {}
        return request, calls

    def test_creates_then_reuses_monthly_log_and_never_touches_ledger(self):
        publisher = load_publisher()
        record = run_record.new_record(); record.update(started_utc='2026-11-03T06:12:00+00:00', storm_probability=.05)
        self.record_file.write_text(json.dumps(record), encoding='utf-8')
        issues = [{'number': 1, 'title': '[SMS-LEDGER] CONNECTIVITY-TEST-RUN-1'}]
        request, calls = self.fake_github(issues)
        env = dict(os.environ, RUN_RECORD_PUBLISH='true')
        with contextlib.redirect_stdout(io.StringIO()):
            publisher.main(env, request=request); publisher.main(env, request=request)
        posts = [c for c in calls if c[0] == 'POST']
        self.assertEqual([c[1].rsplit('/repos/example/research/', 1)[1] for c in posts],
                         ['issues', 'issues/50/comments', 'issues/50/comments'])
        self.assertEqual(posts[0][2]['title'], '[RUN-LOG] 2026-11')
        self.assertFalse(any('issues/1/' in c[1] for c in calls))  # SMS ledger untouched
        self.assertIn('"storm_probability": 0.05', posts[1][2]['body'])

    def test_missing_record_is_reported_not_fabricated(self):
        publisher = load_publisher()
        request, calls = self.fake_github([])
        with contextlib.redirect_stdout(io.StringIO()):
            publisher.main(dict(os.environ, RUN_RECORD_PUBLISH='true'), request=request)
        body = json.loads(calls[-1][2]['body'].split('```json\n', 1)[1].rsplit('\n```', 1)[0])
        self.assertEqual((body['record_type'], body['error_detail']), ('worker_record_missing', 'worker_record_missing_or_unreadable'))
        self.assertIsNone(body['storm_probability'])

    def test_publication_disabled_outside_actions_and_job_summary_written(self):
        publisher = load_publisher()
        self.record_file.write_text(json.dumps(run_record.new_record()), encoding='utf-8')
        summary = Path(self.temp.name) / 'summary.md'
        request = Mock()
        with contextlib.redirect_stdout(io.StringIO()):
            publisher.main(dict(os.environ, GITHUB_ACTIONS='false', RUN_RECORD_PUBLISH='true', GITHUB_STEP_SUMMARY=str(summary)), request=request)
        request.assert_not_called()
        self.assertIn('| warning_decision | not_evaluated |', summary.read_text(encoding='utf-8'))


class Redaction(RecordHarness):
    def test_sanitise_text_redacts_secrets_and_identifiers(self):
        text = (f'token {DUMMY_TOKEN} sid {DUMMY_SID} msg SM{"f" * 32} to {DUMMY_NUMBER} or +27 82 123 4567 '
                f'or 0821234567 gh {DUMMY_GH} Bearer abc.def-ghi123 pat github_pat_{"x" * 30}')
        clean = run_record.sanitise_text(text)
        self.assert_no_secrets(clean)
        for fragment in ('SM' + 'f' * 32, '82 123 4567', '0821234567', 'abc.def-ghi123', 'github_pat_'):
            self.assertNotIn(fragment, clean)
        self.assertEqual(run_record.sanitise_text('2026-10-29T06:59:50+00:00'), '2026-10-29T06:59:50+00:00')

    def test_sanitise_record_whitelists_fields_and_types(self):
        record = run_record.new_record()
        record.update(recipient=DUMMY_NUMBER, message_body='Storm risk 90%', message_sid=DUMMY_SID,
                      error_message=f'failed for {DUMMY_NUMBER}', storm_probability=float('nan'),
                      workflow_run_id='40832590994', workflow_run_number='12; rm -rf', error_category='made_up')
        clean = run_record.sanitise_record(record)
        for key in ('recipient', 'message_body', 'message_sid'):
            self.assertNotIn(key, clean)
        self.assertNotIn(DUMMY_NUMBER, json.dumps(clean))
        self.assertIsNone(clean['storm_probability'])
        self.assertEqual((clean['workflow_run_id'], clean['workflow_run_number']), ('40832590994', '[REDACTED]'))
        self.assertEqual(clean['error_category'], 'unexpected_internal_error')

    def test_full_run_record_contains_no_secrets(self):
        worker = load_worker()
        with patch('sms_alert.sms_is_configured', return_value=True), \
             patch('sms_alert.send_storm_sms', return_value={'status': 'sent', 'sent': True}), \
             patch.object(worker, 'reserve_hour', return_value=5), patch.object(worker, 'report'):
            r = self.run_worker(probability=.40, worker=worker)
        self.assert_no_secrets(self.record_file.read_text(encoding='utf-8') + r['stdout'] + r['stderr'])

    def test_job_summary_withheld_if_secret_survives_sanitisation(self):
        publisher = load_publisher()
        summary = Path(self.temp.name) / 'summary.md'
        leaked = {'outcome': 'failed', 'error_detail': f'leak {DUMMY_TOKEN}'}  # error_detail is a summary field
        with patch.object(publisher, 'load_record', return_value=leaked), contextlib.redirect_stdout(io.StringIO()) as out:
            self.assertEqual(publisher.main(dict(os.environ, GITHUB_STEP_SUMMARY=str(summary))), 0)
        text = summary.read_text(encoding='utf-8')
        self.assertNotIn(DUMMY_TOKEN, text); self.assertIn('withheld', text)
        self.assertIn('::warning::', out.getvalue())

    def test_failed_run_summary_is_sanitised(self):
        publisher = load_publisher()
        worker = load_worker()
        with patch('sms_alert.sms_is_configured', return_value=True), \
             patch('sms_alert.send_storm_sms', side_effect=RuntimeError(f'{DUMMY_NUMBER} {DUMMY_SID} {DUMMY_TOKEN}')), \
             patch.object(worker, 'reserve_hour', return_value=6), patch.object(worker, 'report'):
            self.run_worker(probability=.40, worker=worker)
        summary = Path(self.temp.name) / 'summary.md'
        with contextlib.redirect_stdout(io.StringIO()):
            publisher.main(dict(os.environ, GITHUB_STEP_SUMMARY=str(summary)))
        text = summary.read_text(encoding='utf-8')
        self.assertIn('| error_category | sms_provider_failure |', text)
        self.assert_no_secrets(text)

    def test_publisher_refuses_content_with_secrets(self):
        publisher = load_publisher()
        request = Mock()
        with contextlib.redirect_stdout(io.StringIO()) as out:
            published = publisher.publish({'error_message': f'leak {DUMMY_TOKEN}'}, dict(os.environ), request=request)
        self.assertFalse(published); request.assert_not_called()
        self.assertIn('sensitive content detected', out.getvalue())


class ContractsAndInvariants(unittest.TestCase):
    def test_classifier_patterns_match_script_12_output(self):
        for marker in (run_record._STAGE_FILES_OK, run_record._STAGE_MODEL_OK, run_record._STAGE_REQUEST_FAILED,
                       run_record._STAGE_DOWNLOADED, run_record._STAGE_FEATURES, run_record._STAGE_PREDICTED,
                       run_record._STAGE_SAVED, 'HTTP status:'):
            self.assertIn(marker, SCRIPT_12)
        for message, _, category in run_record._KNOWN_MESSAGES:
            self.assertIn(message, SCRIPT_12); self.assertIn(category, run_record.ERROR_CATEGORIES)

    def test_threshold_cron_and_monitoring_step_isolation(self):
        worker = load_worker()
        self.assertEqual(worker.WARNING_THRESHOLD, .35)
        workflow = (ROOT / '.github/workflows/scheduled-storm-sms.yml').read_text(encoding='utf-8')
        self.assertIn("- cron: '12 * * * *'", workflow)
        publish = workflow.split('- name: Publish sanitised run record (monitoring only)', 1)[1]
        for line in ('if: ${{ always() }}', 'continue-on-error: true', 'run: python 19_publish_run_record.py',
                     "RUN_RECORD_PUBLISH: 'false'"):
            self.assertIn(line, publish)  # initial deployment: job summary only, no public issue
        self.assertIn('issues: write', workflow); self.assertIn('contents: read', workflow)
        self.assertNotIn('contents: write', workflow)
        compile_line = next(l for l in workflow.splitlines() if 'py_compile' in l)
        self.assertNotIn('run_record', compile_line)  # a monitoring syntax error must not block the warning step

    def test_monitoring_modules_use_standard_library_only(self):
        import ast
        allowed = {'json', 'math', 'os', 're', 'tempfile', 'datetime', 'pathlib', 'sys', 'urllib', 'run_record'}
        for name in ('run_record.py', '19_publish_run_record.py'):
            tree = ast.parse((ROOT / name).read_text(encoding='utf-8'))
            modules = {a.name.split('.')[0] for n in ast.walk(tree) if isinstance(n, ast.Import) for a in n.names}
            modules |= {n.module.split('.')[0] for n in ast.walk(tree) if isinstance(n, ast.ImportFrom)}
            self.assertLessEqual(modules, allowed, name)

    def test_monitoring_code_never_references_sms_sending(self):
        for name in ('run_record.py', '19_publish_run_record.py'):
            source = (ROOT / name).read_text(encoding='utf-8')
            for forbidden in ('send_storm_sms', 'send_test_sms', 'send_simulated', 'twilio', 'messages.create', 'SMS-LEDGER]'):
                self.assertNotIn(forbidden, source.replace('[SMS-LEDGER] reservations', ''), (name, forbidden))


class ConnectivityRecord(RecordHarness):
    def test_connectivity_test_record(self):
        os.environ.update(GITHUB_EVENT_NAME='workflow_dispatch', SMS_TEST_CONFIRMED='true')
        worker = load_worker()
        with patch('sms_alert.sms_is_configured', return_value=True), patch('sms_alert._get_recipients', return_value=['x']), \
             patch('sms_alert.send_test_sms', return_value={'status': 'test_sent', 'sent': True}), \
             patch('sms_alert.send_storm_sms') as storm, \
             patch.object(worker, 'reserve_hour', return_value=11), patch.object(worker, 'report'):
            r = self.run_worker(args=('--test-sms',), worker=worker)
        storm.assert_not_called(); r['inference'].assert_not_called()
        rec = r['record']
        self.assertEqual((r['code'], rec['mode'], rec['sms_submission'], rec['duplicate_prevention'], rec['warning_decision']),
                         (0, 'connectivity_test', 'test_sent', 'reserved', 'not_applicable'))
        self.assertEqual(rec['forecast_retrieval'], 'not_applicable')


if __name__ == '__main__':
    unittest.main()
