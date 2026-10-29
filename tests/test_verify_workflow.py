"""Isolated dry-run verification workflow: static safety checks and worker behaviour.

The verification workflow must be manual-only, read-only, secret-free and
structurally unable to send SMS or write the duplicate-prevention ledger.
All external services are mocked; any SMS, ledger or network call fails a test.
"""
import contextlib
import importlib.util
import io
import json
import os
from pathlib import Path
import re
import subprocess
import unittest
from unittest.mock import Mock, patch

import pandas as pd

from test_run_record import RecordHarness, failed_process, OUT_MODEL_OK, OUT_REQUEST, OUT_FEATURES
from test_scheduled_sms_worker import load_worker

ROOT = Path(__file__).resolve().parents[1]
VERIFY = ROOT / '.github/workflows/verify-monitoring.yml'
PRODUCTION = ROOT / '.github/workflows/scheduled-storm-sms.yml'
LABEL = 'DRY-RUN VERIFICATION — NOT A REAL WARNING'


def workflow_text(path=None):
    # Resolve the default at call time so the checks always read the current target file.
    return (path or VERIFY).read_text(encoding='utf-8').replace('\r', '')


def code_lines(text):
    """Workflow lines without comments, so comments cannot satisfy or defeat a check."""
    return [l for l in text.splitlines() if l.strip() and not l.strip().startswith('#')]


class VerificationWorkflowStatic(unittest.TestCase):
    def setUp(self):
        self.text = workflow_text()
        self.code = '\n'.join(code_lines(self.text))

    def test_manual_trigger_only(self):
        on_block = self.text.split("'on':", 1)[1].split('permissions:', 1)[0]
        self.assertEqual([l.strip() for l in code_lines(on_block)], ['workflow_dispatch:'])
        for trigger in ('schedule', 'cron', 'push', 'pull_request', 'workflow_run', 'repository_dispatch',
                        'workflow_call', 'issues', 'release'):
            self.assertNotRegex(self.code, rf'(?m)^\s*{trigger}\s*:', trigger)

    def test_read_only_permissions_and_no_persisted_token(self):
        self.assertIn('permissions:\n  contents: read\nconcurrency:', self.text)
        self.assertNotRegex(self.code, r':\s*write\b')
        self.assertEqual(self.code.count('permissions:'), 1)  # no job-level escalation
        self.assertIn('persist-credentials: false', self.code)

    def test_no_secrets_or_credentials_passed(self):
        self.assertNotIn('secrets.', self.code)
        self.assertNotIn('github.token', self.code)
        for name in ('GH_TOKEN', 'GITHUB_TOKEN', 'TWILIO', 'ALERT_TO_NUMBERS', 'HC_', 'SMS_TEST_CONFIRMED', 'ADMIN_PASSWORD'):
            self.assertNotIn(name, self.code, name)

    def test_dry_run_only_and_no_sms_paths(self):
        runs = re.findall(r'(?m)^\s*(?:- )?run:\s*(.+)$', self.code)
        worker_runs = [r for r in runs if '18_scheduled_sms_worker.py' in r]
        self.assertEqual(worker_runs, ['python 18_scheduled_sms_worker.py --dry-run'])
        for forbidden in ('--live', '--test-sms', '20_send_heartbeat.py', 'sms_alert', 'curl', 'gh '):
            self.assertNotIn(forbidden, self.code, forbidden)
        self.assertIn("ENABLE_REAL_SMS: 'false'", self.code)
        self.assertIn("RUN_RECORD_PUBLISH: 'false'", self.code)

    def test_separate_concurrency_group(self):
        group = re.search(r'(?m)^\s+group:\s*(\S+)', self.text).group(1)
        production_group = re.search(r'(?m)^\s+group:\s*(\S+)', workflow_text(PRODUCTION)).group(1)
        self.assertEqual(production_group, 'matatiele-hourly-sms')
        self.assertNotEqual(group, production_group)

    def test_outputs_are_labelled(self):
        self.assertTrue(self.text.startswith(f'name: {LABEL}\n'))
        self.assertIn(f'name: {LABEL}', self.code)  # job name
        self.assertIn(f'## {LABEL}', self.code)  # job summary banner
        for step in ('Forecast and model', 'Run record summary', 'Label run'):
            self.assertIn(f'name: {step} ({LABEL})', self.code)

    def test_publisher_is_isolated(self):
        publish = self.text.split('Run record summary', 1)[1]
        for line in ('if: ${{ always() }}', 'continue-on-error: true', 'run: python 19_publish_run_record.py'):
            self.assertIn(line, publish)

    def test_production_workflow_untouched_by_verification(self):
        production = workflow_text(PRODUCTION)
        self.assertIn("- cron: '12 * * * *'", production)
        self.assertIn("ENABLE_REAL_SMS: 'true'", production)
        self.assertIn('run: python 18_scheduled_sms_worker.py --live', production)
        self.assertNotIn('verify-monitoring', production)


class DryRunNeverSendsOrWritesLedger(RecordHarness):
    """Worker behaviour under --dry-run, with guards that record any forbidden call."""

    def guarded_run(self, args=('--dry-run',), **kwargs):
        guards = {'network': Mock(side_effect=AssertionError('network call')),
                  'send_storm_sms': Mock(side_effect=AssertionError('sms')),
                  'send_test_sms': Mock(side_effect=AssertionError('sms')),
                  'send_simulated_storm_sms': Mock(side_effect=AssertionError('sms')),
                  'github': Mock(side_effect=AssertionError('ledger')),
                  'reserve_hour': Mock(side_effect=AssertionError('ledger')),
                  'report': Mock(side_effect=AssertionError('ledger'))}
        worker = load_worker()
        with patch.object(worker.requests, 'request', guards['network']), \
             patch('sms_alert.send_storm_sms', guards['send_storm_sms']), \
             patch('sms_alert.send_test_sms', guards['send_test_sms']), \
             patch('sms_alert.send_simulated_storm_sms', guards['send_simulated_storm_sms']), \
             patch.object(worker, 'github', guards['github']), \
             patch.object(worker, 'reserve_hour', guards['reserve_hour']), \
             patch.object(worker, 'report', guards['report']):
            result = self.run_worker(args=args, worker=worker, **kwargs)
        for name, guard in guards.items():
            self.assertFalse(guard.called, f'{name} was called during a dry run')
        return result

    def verification_environment(self):
        """The verification job's environment: no secrets, live disabled, manual dispatch."""
        for name in ('TWILIO_ACCOUNT_SID', 'TWILIO_AUTH_TOKEN', 'TWILIO_FROM_NUMBER', 'ALERT_TO_NUMBERS',
                     'GH_TOKEN', 'GITHUB_TOKEN'):
            os.environ.pop(name, None)
        os.environ.update(ENABLE_REAL_SMS='false', GITHUB_EVENT_NAME='workflow_dispatch', RUN_RECORD_PUBLISH='false')

    def test_above_threshold_dry_run_never_sends_even_with_live_enabled(self):
        # Worst case: credentials present and ENABLE_REAL_SMS=true, but --dry-run.
        r = self.guarded_run(probability=.95)
        rec = r['record']
        self.assertEqual((r['code'], rec['mode'], rec['warning_decision']), (0, 'dry_run', 'warning_eligible'))
        self.assertEqual((rec['duplicate_prevention'], rec['sms_submission'], rec['sms_note']),
                         ('not_attempted', 'not_attempted', 'dry_run'))
        self.assertIn('DRY RUN', r['stdout'])

    def test_verification_environment_records_dispatch_dry_run(self):
        self.verification_environment()
        for probability, decision in ((.10, 'below_threshold'), (.95, 'warning_eligible')):
            with self.subTest(probability=probability):
                r = self.guarded_run(probability=probability)
                rec = r['record']
                self.assertEqual((r['code'], rec['trigger'], rec['mode'], rec['warning_decision']),
                                 (0, 'workflow_dispatch', 'dry_run', decision))
                self.assertEqual(rec['forecast_retrieval'], 'ok')
                self.assertEqual(rec['warning_threshold'], .35)

    def test_error_paths_never_send_or_write_ledger(self):
        self.verification_environment()
        stale = dict(self.row, storm_probability=.95, forecast_retrieved_at='2020-01-01T00:00:00+00:00')
        cases = {
            'forecast retrieval failure': dict(subprocess_effect=failed_process(
                OUT_MODEL_OK + OUT_REQUEST + 'HTTP status: 503\n\nLive forecast request failed.\n')),
            'invalid forecast data': dict(subprocess_effect=failed_process(
                OUT_FEATURES, 'ValueError: Nonfinite model input; prediction was not updated.')),
            'pipeline timeout': dict(subprocess_effect=subprocess.TimeoutExpired(['python'], 240)),
            'forecast script not started': dict(subprocess_effect=OSError('cannot start')),
            'stale high-probability prediction': dict(rows=[stale]),
            'non-finite prediction': dict(rows=[dict(self.row, storm_probability=float('nan'))]),
        }
        for label, kwargs in cases.items():
            with self.subTest(label):
                self.record_file.unlink(missing_ok=True)
                r = self.guarded_run(**kwargs)
                rec = r['record']
                self.assertEqual(r['code'], 1)
                self.assertEqual((rec['mode'], rec['duplicate_prevention'], rec['sms_submission']),
                                 ('dry_run', 'not_attempted', 'not_attempted'))
                self.assertNotEqual(rec['error_category'], 'none')

    def test_unreadable_prediction_csv_never_sends(self):
        self.verification_environment()
        worker = load_worker()
        guard = Mock(side_effect=AssertionError('sms'))
        with patch.object(worker.subprocess, 'run'), \
             patch.object(worker.pd, 'read_csv', side_effect=OSError('locked')), \
             patch.object(worker.PREDICTION.__class__, 'is_file', return_value=True), \
             patch('sms_alert.send_storm_sms', guard), patch.object(worker, 'github', guard), \
             contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
            code = worker.run(['--dry-run'])
        self.assertEqual(code, 1); guard.assert_not_called()
        rec = json.loads(self.record_file.read_text(encoding='utf-8'))
        self.assertEqual((rec['error_category'], rec['error_detail']), ('prediction_output_failure', 'prediction_csv_unreadable'))

    def test_publisher_in_verification_environment_makes_no_requests(self):
        self.verification_environment()
        os.environ['GITHUB_ACTIONS'] = 'true'
        self.guarded_run(probability=.95)  # eligible, but dry run: SMS must be not_attempted
        spec = importlib.util.spec_from_file_location('publisher', ROOT / '19_publish_run_record.py')
        publisher = importlib.util.module_from_spec(spec); spec.loader.exec_module(publisher)
        summary = Path(self.temp.name) / 'summary.md'
        request = Mock(side_effect=AssertionError('network'))
        with contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(publisher.main(dict(os.environ, GITHUB_STEP_SUMMARY=str(summary)), request=request), 0)
        request.assert_not_called()
        text = summary.read_text(encoding='utf-8')
        self.assertIn('| mode | dry_run |', text)
        self.assertIn('| trigger | workflow_dispatch |', text)
        self.assertIn('| sms_submission | not_attempted |', text)


if __name__ == '__main__':
    unittest.main()
