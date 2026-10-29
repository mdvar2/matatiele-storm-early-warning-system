"""R3: external-trigger support and strengthened duplicate prevention.

All GitHub and SMS interactions are simulated. FakeGitHub enforces label-name
uniqueness like the GitHub API (422 already_exists) so the atomic reservation
lock can be exercised, including deterministic interleaving of two runs.
"""
import contextlib
import importlib.util
import io
import json
import os
from pathlib import Path
import re
import unittest
from unittest.mock import Mock, patch
from urllib.parse import unquote

import pandas as pd

import run_record
from test_run_record import RecordHarness
from test_scheduled_sms_worker import load_worker

ROOT = Path(__file__).resolve().parents[1]
PRODUCTION = ROOT / '.github/workflows/scheduled-storm-sms.yml'


class FakeGitHub:
    """In-memory issues + labels ledger with GitHub's label-uniqueness rule and fault injection."""

    def __init__(self):
        self.issues, self.labels, self.comments, self.calls = [], set(), [], []
        self.fail = set()                 # {'list', 'label', 'issue', 'comment'}
        self.before_issue_create = None   # hook to interleave another run
        self.worker = None

    def bind(self, worker):
        self.worker = worker
        return self

    def _error(self):
        self.worker.fail('GitHub ledger unavailable; submission stopped. Check permissions and service availability.',
                         'duplicate_prevention_failure', 'ledger_unavailable')

    def __call__(self, method, endpoint, conflict_ok=False, **kwargs):
        self.calls.append((method, endpoint.split('?')[0]))
        if method == 'GET' and endpoint.startswith('issues?'):
            if 'list' in self.fail:
                self._error()
            page = int(re.search(r'[?&]page=(\d+)', endpoint).group(1))
            return [dict(i) for i in self.issues[(page - 1) * 100: page * 100]]
        if method == 'POST' and endpoint == 'labels':
            if 'label' in self.fail:
                self._error()
            name = kwargs['json']['name']
            if name in self.labels:
                if conflict_ok:
                    return {'_conflict': True}
                self._error()
            self.labels.add(name)
            return {'name': name, 'color': kwargs['json']['color']}
        if method == 'DELETE' and endpoint.startswith('labels/'):
            if 'delete' in self.fail:
                self._error()
            self.labels.discard(unquote(endpoint[len('labels/'):]))
            return {}
        if method == 'POST' and endpoint == 'issues':
            if self.before_issue_create:
                hook, self.before_issue_create = self.before_issue_create, None
                hook()
            if 'issue' in self.fail:
                self._error()
            issue = {'number': len(self.issues) + 1, 'title': kwargs['json']['title'], 'state': 'open'}
            self.issues.append(issue)
            if 'issue_uncertain' in self.fail:  # created server-side, but the response was lost
                self._error()
            return issue
        if method == 'POST' and endpoint.endswith('/comments'):
            if 'comment' in self.fail:
                self._error()
            self.comments.append(kwargs['json']['body'])
            return {}
        raise AssertionError(f'unexpected GitHub call {method} {endpoint}')


class DuplicatePrevention(RecordHarness):
    def setUp(self):
        super().setUp()
        self.ledger = FakeGitHub()
        self.send = Mock(return_value={'status': 'sent', 'sent': True})
        self.patches = [patch('sms_alert.sms_is_configured', return_value=True), patch('sms_alert.send_storm_sms', self.send)]
        for p in self.patches:
            p.start(); self.addCleanup(p.stop)

    def live(self, probability=.40, record_path=None, **env):
        worker = load_worker()
        with patch.object(worker, 'github', self.ledger.bind(worker)), patch.dict(os.environ, env):
            if record_path:
                os.environ['RUN_RECORD_FILE'] = str(record_path)
            r = self.run_worker(probability=probability, worker=worker)
        if record_path:
            r['record'] = json.loads(Path(record_path).read_text(encoding='utf-8'))
        return r

    def test_two_runs_same_forecast_hour_send_once(self):
        first, second = self.live(), self.live(RUN_TRIGGER_SOURCE='external_scheduler')
        self.assertEqual(self.send.call_count, 1)
        self.assertEqual((first['code'], second['code']), (0, 0))
        self.assertEqual(first['record']['reservation_lock'], 'created')
        self.assertEqual((second['record']['duplicate_prevention'], second['record']['sms_note']),
                         ('already_reserved', 'duplicate_suppressed'))
        self.assertEqual(len(self.ledger.issues), 1); self.assertEqual(len(self.ledger.labels), 1)

    def test_concurrent_runs_interleaved_lock_prevents_second_send(self):
        # Run B executes completely after A has taken the lock but before A's ledger issue exists:
        # B's issue scan finds nothing, so only the atomic label lock can stop it.
        b_record = Path(self.temp.name) / 'b.json'
        results = {}
        self.ledger.before_issue_create = lambda: results.setdefault('b', self.live(record_path=b_record))
        a = self.live()
        b = results['b']
        self.assertEqual(self.send.call_count, 1)
        self.assertEqual(a['record']['reservation_lock'], 'created')
        self.assertEqual((b['record']['reservation_lock'], b['record']['duplicate_prevention']), ('already_exists', 'already_reserved'))
        self.assertEqual((a['code'], b['code']), (0, 0))

    def test_concurrent_runs_without_lock_can_duplicate_documented_limit(self):
        # If the lock API is unavailable AND runs are not serialised, the issue ledger alone
        # cannot stop a duplicate. Recorded honestly; the concurrency group is the other safeguard.
        self.ledger.fail.add('label')
        b_record = Path(self.temp.name) / 'b.json'
        results = {}
        self.ledger.before_issue_create = lambda: results.setdefault('b', self.live(record_path=b_record))
        a = self.live()
        self.assertEqual(self.send.call_count, 2)
        self.assertEqual((a['record']['reservation_lock'], results['b']['record']['reservation_lock']), ('unavailable', 'unavailable'))

    def test_existing_reservations_suppress_sending(self):
        worker = load_worker()
        key = 'REAL-SHORT-V1-' + (self.now.floor('h') + pd.Timedelta(hours=1)).isoformat()
        for label, setup in [('issue only', lambda: self.ledger.issues.append({'number': 1, 'title': f'[SMS-LEDGER] {key}'})),
                             ('label only (earlier run crashed after locking)', lambda: self.ledger.labels.add(worker.lock_label_name(key))),
                             ('issue and label', lambda: (self.ledger.issues.append({'number': 1, 'title': f'[SMS-LEDGER] {key}'}),
                                                          self.ledger.labels.add(worker.lock_label_name(key))))]:
            with self.subTest(label):
                self.ledger.issues.clear(); self.ledger.labels.clear(); self.send.reset_mock()
                setup()
                r = self.live()
                self.assertEqual((r['code'], self.send.call_count, r['record']['duplicate_prevention']), (0, 0, 'already_reserved'))

    def test_ledger_list_failure_fails_closed(self):
        self.ledger.fail.add('list')
        r = self.live()
        self.assertEqual((r['code'], self.send.call_count), (1, 0))
        self.assertEqual((r['record']['error_category'], r['record']['reservation_lock']), ('duplicate_prevention_failure', 'not_attempted'))
        self.assertEqual(self.ledger.labels, set())

    def test_lock_unavailable_falls_back_to_previous_behaviour(self):
        self.ledger.fail.add('label')
        r = self.live()
        self.assertEqual((r['code'], self.send.call_count, r['record']['reservation_lock']), (0, 1, 'unavailable'))
        self.assertEqual(len(self.ledger.issues), 1)
        second = self.live()  # the issue ledger still stops a later run in the same hour
        self.assertEqual((second['code'], self.send.call_count), (0, 1))

    def test_issue_creation_failure_releases_lock_so_a_retry_can_warn(self):
        self.ledger.fail.add('issue')
        r = self.live()
        self.assertEqual((r['code'], self.send.call_count, r['record']['reservation_lock']), (1, 0, 'released'))
        self.assertEqual(r['record']['error_category'], 'duplicate_prevention_failure')
        self.assertEqual(self.ledger.labels, set())
        self.ledger.fail.clear()
        retry = self.live(GITHUB_RUN_ATTEMPT='2')
        self.assertEqual((retry['code'], self.send.call_count, retry['record']['reservation_lock']), (0, 1, 'created'))
        self.assertEqual(self.live()['code'], 0); self.assertEqual(self.send.call_count, 1)

    def test_uncertain_issue_creation_released_lock_still_never_duplicates(self):
        # The issue was created but the response was lost: the lock is released, yet the
        # retry finds the issue by title and sends nothing (no SMS was sent by either run).
        self.ledger.fail.add('issue_uncertain')
        r = self.live()
        self.assertEqual((r['code'], self.send.call_count, r['record']['reservation_lock']), (1, 0, 'released'))
        self.ledger.fail.clear()
        retry = self.live(GITHUB_RUN_ATTEMPT='2')
        self.assertEqual((retry['code'], self.send.call_count, retry['record']['duplicate_prevention']), (0, 0, 'already_reserved'))

    def test_lock_release_failure_suppresses_later_runs_documented_limit(self):
        # Fails safe against duplicates, at the cost of this forecast hour's warning.
        self.ledger.fail.update({'issue', 'delete'})
        r = self.live()
        self.assertEqual((r['code'], self.send.call_count, r['record']['reservation_lock']), (1, 0, 'release_failed'))
        self.ledger.fail.clear()
        retry = self.live(GITHUB_RUN_ATTEMPT='2')
        self.assertEqual((retry['code'], self.send.call_count, retry['record']['reservation_lock']), (0, 0, 'already_exists'))

    def test_issue_failure_without_lock_does_not_delete_anything(self):
        self.ledger.fail.update({'label', 'issue'})
        r = self.live()
        self.assertEqual((r['code'], self.send.call_count, r['record']['reservation_lock']), (1, 0, 'unavailable'))
        self.assertNotIn('DELETE', [m for m, _ in self.ledger.calls])

    def test_sms_failure_keeps_reservation_and_reruns_do_not_resend(self):
        self.send.return_value = {'status': 'failed', 'sent': False}
        r = self.live()
        self.assertEqual((r['code'], self.send.call_count), (1, 1))
        rerun = self.live(GITHUB_RUN_ATTEMPT='2')
        self.assertEqual((rerun['code'], self.send.call_count, rerun['record']['duplicate_prevention']), (0, 1, 'already_reserved'))

    def test_retried_and_duplicated_dispatches_send_once(self):
        runs = [self.live(RUN_TRIGGER_SOURCE='external_scheduler', RUN_SCHEDULED_FOR='2026-10-30T07:05:00Z'),
                self.live(RUN_TRIGGER_SOURCE='external_scheduler', RUN_SCHEDULED_FOR='2026-10-30T07:05:00Z'),  # duplicate dispatch
                self.live(RUN_TRIGGER_SOURCE='external_scheduler', GITHUB_RUN_ATTEMPT='2'),                      # re-run
                self.live(RUN_TRIGGER_SOURCE='github_schedule')]                                                   # cron backup
        self.assertEqual(self.send.call_count, 1)
        self.assertEqual([r['code'] for r in runs], [0, 0, 0, 0])

    def test_different_forecast_hours_are_not_over_suppressed(self):
        worker = load_worker()
        with patch.object(worker, 'github', self.ledger.bind(worker)):
            first = worker.reserve_hour('REAL-SHORT-V1-2026-10-30T08:00:00+00:00')
            second = worker.reserve_hour('REAL-SHORT-V1-2026-10-30T09:00:00+00:00')
            repeat = worker.reserve_hour('REAL-SHORT-V1-2026-10-30T08:00:00+00:00')
        self.assertEqual((first, second, repeat), (1, 2, None))

    def test_below_threshold_never_touches_ledger_or_lock(self):
        r = self.live(probability=.10)
        self.assertEqual((r['code'], self.send.call_count, self.ledger.calls), (0, 0, []))
        self.assertEqual(r['record']['reservation_lock'], 'not_attempted')


class LockPrimitives(unittest.TestCase):
    def test_label_names_are_deterministic_and_within_github_limit(self):
        worker = load_worker()
        for key in ('REAL-SHORT-V1-2026-10-30T08:00:00+00:00', 'CONNECTIVITY-TEST-RUN-40931080705', 'X' * 200):
            name = worker.lock_label_name(key)
            self.assertLessEqual(len(name), 50); self.assertTrue(name.startswith('sms-lock:'))
            self.assertEqual(name, worker.lock_label_name(key))
        self.assertNotEqual(worker.lock_label_name('X' * 200), worker.lock_label_name('X' * 199 + 'Y'))

    def http(self, status, payload):
        response = Mock(status_code=status)
        response.json.return_value = payload
        if status >= 400:
            import requests
            response.raise_for_status.side_effect = requests.HTTPError(f'{status}')
        else:
            response.raise_for_status.return_value = None
        return response

    def test_github_conflict_parsing(self):
        with patch.dict(os.environ, {'GITHUB_REPOSITORY': 'example/research', 'GH_TOKEN': 'dummy-only'}):
            worker = load_worker()
            exists = self.http(422, {'message': 'Validation Failed', 'errors': [{'resource': 'Label', 'code': 'already_exists', 'field': 'name'}]})
            invalid = self.http(422, {'message': 'Validation Failed', 'errors': [{'code': 'invalid', 'field': 'color'}]})
            created = self.http(201, {'name': 'sms-lock:k'})
            with patch.object(worker.requests, 'request', return_value=exists):
                self.assertEqual(worker.github('POST', 'labels', conflict_ok=True, json={}), {'_conflict': True})
                with self.assertRaises(worker.WorkerError):  # without conflict_ok, a conflict is an error
                    worker.github('POST', 'labels', json={})
            with patch.object(worker.requests, 'request', return_value=invalid):
                with self.assertRaises(worker.WorkerError):
                    worker.github('POST', 'labels', conflict_ok=True, json={})
                self.assertEqual(worker.acquire_reservation_lock('k'), 'unavailable')
            with patch.object(worker.requests, 'request', return_value=created):
                self.assertEqual(worker.acquire_reservation_lock('k'), 'created')
            with patch.object(worker.requests, 'request', return_value=self.http(201, {'name': 'something-else'})):
                self.assertEqual(worker.acquire_reservation_lock('k'), 'unverified')
            empty = self.http(204, None)
            empty.json.side_effect = ValueError('no body')
            with patch.object(worker.requests, 'request', return_value=empty) as request:
                self.assertEqual(worker.release_reservation_lock('REAL-SHORT-V1-2026-10-30T08:00:00+00:00'), 'released')
            method, url = request.call_args.args[:2]
            self.assertEqual(method, 'DELETE')
            self.assertTrue(url.endswith('/labels/sms-lock%3AREAL-SHORT-V1-2026-10-30T08%3A00%3A00%2B00%3A00'), url)
            with patch.object(worker.requests, 'request', return_value=self.http(404, {'message': 'Not Found'})):
                self.assertEqual(worker.release_reservation_lock('k'), 'release_failed')


class TriggerRecording(RecordHarness):
    def test_trigger_source_derivation(self):
        cases = [({'GITHUB_EVENT_NAME': 'schedule'}, 'github_schedule'),
                 ({'GITHUB_EVENT_NAME': 'workflow_dispatch'}, 'manual'),
                 ({'GITHUB_EVENT_NAME': 'workflow_dispatch', 'RUN_TRIGGER_SOURCE': 'external_scheduler'}, 'external_scheduler'),
                 ({'GITHUB_EVENT_NAME': 'schedule', 'RUN_TRIGGER_SOURCE': 'github_schedule'}, 'github_schedule'),
                 ({'GITHUB_EVENT_NAME': 'workflow_dispatch', 'RUN_TRIGGER_SOURCE': 'evil; rm -rf'}, 'manual'),
                 ({}, 'local'), ({'GITHUB_EVENT_NAME': 'push'}, 'unknown')]
        for env, expected in cases:
            with self.subTest(env=env):
                self.assertEqual(run_record.trigger_source(env), expected)

    def test_scheduled_slot_validation(self):
        self.assertEqual(run_record.scheduled_slot({})[0], 'not_available')
        self.assertEqual(run_record.scheduled_slot({'RUN_SCHEDULED_FOR': ''})[0], 'not_available')
        self.assertEqual(run_record.scheduled_slot({'RUN_SCHEDULED_FOR': '2026-10-30T07:05:00Z'})[0], '2026-10-30T07:05:00+00:00')
        self.assertEqual(run_record.scheduled_slot({'RUN_SCHEDULED_FOR': '2026-10-30T07:05Z'})[0], '2026-10-30T07:05:00+00:00')
        for bad in ('tomorrow', '2026-10-30 07:05:00', '2026-13-40T99:99:00Z', '2026-10-30T07:05:00+02:00', '<script>'):
            with self.subTest(bad=bad):
                self.assertEqual(run_record.scheduled_slot({'RUN_SCHEDULED_FOR': bad}), ('invalid', None))

    def test_end_to_end_record_fields(self):
        slot = (self.now.floor('h') + pd.Timedelta(minutes=5)).strftime('%Y-%m-%dT%H:%M:%SZ')
        os.environ.update(GITHUB_EVENT_NAME='workflow_dispatch', RUN_TRIGGER_SOURCE='external_scheduler', RUN_SCHEDULED_FOR=slot)
        r = self.run_worker(args=('--dry-run',))
        rec = r['record']
        self.assertEqual((rec['trigger'], rec['trigger_source']), ('workflow_dispatch', 'external_scheduler'))
        self.assertEqual(rec['scheduled_slot_utc'], pd.Timestamp(slot).isoformat())
        self.assertIsInstance(rec['dispatch_delay_seconds'], float)
        self.assertEqual(rec['reservation_lock'], 'not_attempted')

    def test_sanitise_enforces_trigger_enum(self):
        clean = run_record.sanitise_record(dict(run_record.new_record({}), trigger_source='spoofed'))
        self.assertEqual(clean['trigger_source'], 'unknown')

    def test_connectivity_test_refused_for_external_scheduler(self):
        os.environ.update(GITHUB_EVENT_NAME='workflow_dispatch', SMS_TEST_CONFIRMED='true', RUN_TRIGGER_SOURCE='external_scheduler')
        worker = load_worker()
        with patch('sms_alert.send_test_sms') as test_sms, patch('sms_alert.sms_is_configured', return_value=True), \
             patch('sms_alert._get_recipients', return_value=['x']), patch.object(worker, 'reserve_hour') as reserve:
            r = self.run_worker(args=('--test-sms',), worker=worker)
        test_sms.assert_not_called(); reserve.assert_not_called()
        self.assertEqual((r['code'], r['record']['error_category'], r['record']['error_detail']),
                         (1, 'configuration_failure', 'external_trigger_not_allowed'))

    def test_heartbeat_payload_and_summary_include_trigger_fields(self):
        os.environ.update(RUN_TRIGGER_SOURCE='external_scheduler', RUN_SCHEDULED_FOR='2026-10-30T07:05:00Z')
        self.run_worker(args=('--dry-run',))
        spec = importlib.util.spec_from_file_location('hb', ROOT / '20_send_heartbeat.py')
        hb = importlib.util.module_from_spec(spec); spec.loader.exec_module(hb)
        payload = json.loads(hb.build_payload(hb.load_record(self.record_file), {}))
        self.assertEqual((payload['trigger_source'], payload['scheduled_slot_utc']), ('external_scheduler', '2026-10-30T07:05:00+00:00'))
        self.assertNotIn('storm_probability', payload)
        spec = importlib.util.spec_from_file_location('pub', ROOT / '19_publish_run_record.py')
        pub = importlib.util.module_from_spec(spec); spec.loader.exec_module(pub)
        summary = pub.summary_markdown(pub.load_record(self.record_file))
        self.assertIn('| trigger_source | external_scheduler |', summary)


class WorkflowInputs(unittest.TestCase):
    def setUp(self):
        self.text = PRODUCTION.read_text(encoding='utf-8').replace('\r', '')

    def test_dispatch_inputs(self):
        block = self.text.split('workflow_dispatch:', 1)[1].split('  schedule:', 1)[0]
        self.assertIn('trigger_source:\n        description:', block)
        self.assertIn('type: choice', block)
        options = re.search(r'options:\n((?:\s+- \S+\n)+)', block).group(1)
        self.assertEqual(re.findall(r'- (\S+)', options), ['manual', 'external_scheduler'])
        self.assertIn('default: manual', block)
        self.assertIn("scheduled_for:\n        description:", block)
        self.assertIn('send_test_sms:', block); self.assertIn('default: false', block)

    def test_both_worker_steps_receive_trigger_env(self):
        expr = "RUN_TRIGGER_SOURCE: ${{ github.event_name == 'schedule' && 'github_schedule' || inputs.trigger_source || 'manual' }}"
        for step in ('Genuine forecast and automatic SMS check', 'Manual connectivity test (NO WEATHER WARNING)'):
            body = self.text.split(f'- name: {step}', 1)[1].split('\n      - ', 1)[0]
            self.assertIn(expr, body, step)
            self.assertIn('RUN_SCHEDULED_FOR: ${{ inputs.scheduled_for }}', body, step)

    def test_production_invariants_unchanged(self):
        self.assertIn("- cron: '12 * * * *'", self.text)
        self.assertIn('permissions:\n  contents: read\n  issues: write\nconcurrency:\n  group: matatiele-hourly-sms\n  cancel-in-progress: false', self.text)
        self.assertIn("if: ${{ github.event_name != 'workflow_dispatch' || inputs.send_test_sms != true }}", self.text)
        self.assertIn("if: ${{ github.event_name == 'workflow_dispatch' && inputs.send_test_sms == true }}", self.text)
        self.assertEqual(self.text.count('run: python 18_scheduled_sms_worker.py --live'), 1)
        self.assertNotIn('contents: write', self.text)


if __name__ == '__main__':
    unittest.main()
