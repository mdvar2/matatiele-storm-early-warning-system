"""Recovery of abandoned duplicate-SMS locks and the lock-permission probe (all simulated, no network).

An abandoned lock is a label whose holder run ended before creating the ledger
issue (crash, cancellation, failed release, lost label response). Because an SMS
is only sent after the issue exists, such a lock can be taken over, but only
when the holder run has provably ended and a fresh ledger scan finds no issue.
"""
import importlib.util
import io
import json
import os
from pathlib import Path
import re
import unittest
from unittest.mock import patch

from test_r3_trigger import LedgerHarness, PRODUCTION, ROOT
from test_scheduled_sms_worker import load_worker

class LockRecovery(LedgerHarness):
    def key(self):
        import pandas as pd
        return 'REAL-SHORT-V1-' + (self.now.floor('h') + pd.Timedelta(hours=1)).isoformat()

    def plant_lock(self, generation=1, run='111', attempt='1', description=None):
        worker = load_worker()
        lock_key = self.key() if generation == 1 else f'{self.key()}#gen{generation}'
        name = worker.lock_label_name(lock_key)
        self.ledger.labels.add(name)
        self.ledger.descriptions[name] = (description if description is not None else
                                          f'Duplicate-SMS lock for one forecast hour. Do not delete. run={run} attempt={attempt}')
        return name

    def test_abandoned_lock_of_finished_run_is_recovered_once(self):
        self.plant_lock(run='111')
        self.ledger.run_status['111'] = 'completed'
        r = self.live(GITHUB_RUN_ID='222')
        self.assertEqual((r['code'], self.send.call_count, r['record']['reservation_lock']), (0, 1, 'recovered'))
        self.assertEqual(len(self.ledger.issues), 1)
        later = self.live(GITHUB_RUN_ID='333')
        self.assertEqual((later['code'], self.send.call_count, later['record']['duplicate_prevention']), (0, 1, 'already_reserved'))

    def test_lock_of_running_holder_is_never_taken_over(self):
        for status in ('in_progress', 'queued', 'waiting', 'pending', 'requested'):
            with self.subTest(status=status):
                self.ledger.labels.clear(); self.send.reset_mock()
                self.plant_lock(run='111')
                self.ledger.run_status['111'] = status
                r = self.live(GITHUB_RUN_ID='222')
                self.assertEqual((r['code'], self.send.call_count, r['record']['reservation_lock']), (0, 0, 'already_exists'))

    def test_unprovable_holder_keeps_suppression(self):
        cases = {'old-format lock without holder': ({'description': 'Duplicate-SMS lock for one forecast hour. Do not delete.'}, set()),
                 'empty description': ({'description': ''}, set()),
                 'run status not readable (no actions: read)': ({}, {'runs'}),
                 'label lookup fails': ({}, {'label_get'})}
        for label, (plant, faults) in cases.items():
            with self.subTest(label):
                self.ledger.labels.clear(); self.ledger.fail = set(faults); self.send.reset_mock()
                self.plant_lock(run='111', **plant)
                r = self.live(GITHUB_RUN_ID='222')
                self.assertEqual((r['code'], self.send.call_count, r['record']['reservation_lock']), (0, 0, 'held_holder_unknown'))

    def test_holder_that_reserved_before_ending_is_found_by_rescan(self):
        # Our first scan saw no issue; the holder then created it (and sent) and ended.
        self.plant_lock(run='111')
        title = f'[SMS-LEDGER] {self.key()}'
        self.ledger.before_label_get = lambda: self.ledger.issues.append({'number': 9, 'title': title})
        r = self.live(GITHUB_RUN_ID='222')
        self.assertEqual((r['code'], self.send.call_count, r['record']['reservation_lock']), (0, 0, 'already_exists'))
        self.assertEqual(r['record']['duplicate_prevention'], 'already_reserved')

    def test_same_run_rerun_recovers_without_reading_run_status(self):
        self.plant_lock(run='40832590994', attempt='1')
        self.ledger.fail.add('runs')  # proves the decision used the attempt number only
        r = self.live(GITHUB_RUN_ID='40832590994', GITHUB_RUN_ATTEMPT='2')
        self.assertEqual((r['code'], self.send.call_count, r['record']['reservation_lock']), (0, 1, 'recovered'))

    def test_same_attempt_or_later_attempt_holder_is_active(self):
        for attempt in ('2', '3'):
            with self.subTest(holder_attempt=attempt):
                self.ledger.labels.clear(); self.send.reset_mock()
                self.plant_lock(run='40832590994', attempt=attempt)
                r = self.live(GITHUB_RUN_ID='40832590994', GITHUB_RUN_ATTEMPT='2')
                self.assertEqual((self.send.call_count, r['record']['reservation_lock']), (0, 'already_exists'))

    def test_two_concurrent_recoveries_send_once(self):
        self.plant_lock(run='111')
        b_record = Path(self.temp.name) / 'b.json'
        results = {}
        # B runs completely while A holds generation 2 but has not yet created the issue.
        self.ledger.run_status['222'] = 'in_progress'
        self.ledger.before_issue_create = lambda: results.setdefault(
            'b', self.live(record_path=b_record, GITHUB_RUN_ID='333'))
        a = self.live(GITHUB_RUN_ID='222')
        b = results['b']
        self.assertEqual(self.send.call_count, 1)
        self.assertEqual((a['record']['reservation_lock'], b['record']['reservation_lock']), ('recovered', 'already_exists'))

    def test_takeover_is_bounded(self):
        for generation in (1, 2, 3):
            self.plant_lock(generation=generation, run=str(100 + generation))
        r = self.live(GITHUB_RUN_ID='222')
        self.assertEqual((r['code'], self.send.call_count, r['record']['reservation_lock']), (0, 0, 'generations_exhausted'))

    def test_lost_label_response_then_issue_failure_is_recoverable(self):
        # Label created server-side but its response was lost -> 'unavailable', nothing to release;
        # the issue POST then fails. Before recovery this suppressed the hour permanently.
        self.ledger.fail.update({'label_uncertain', 'issue'})
        first = self.live(GITHUB_RUN_ID='111')
        self.assertEqual((first['code'], self.send.call_count, first['record']['reservation_lock']), (1, 0, 'unavailable'))
        self.assertEqual(len(self.ledger.labels), 1)
        self.ledger.fail.clear()
        retry = self.live(GITHUB_RUN_ID='222')
        self.assertEqual((retry['code'], self.send.call_count, retry['record']['reservation_lock']), (0, 1, 'recovered'))

    def test_crash_between_lock_and_issue_is_recoverable(self):
        def crash():
            raise SystemExit('runner lost')  # not a WorkerError: no release, like a killed process
        self.ledger.before_issue_create = crash
        with self.assertRaises(SystemExit):
            self.live(GITHUB_RUN_ID='111')
        self.assertEqual((len(self.ledger.labels), len(self.ledger.issues), self.send.call_count), (1, 0, 0))
        retry = self.live(GITHUB_RUN_ID='222')
        self.assertEqual((retry['code'], self.send.call_count, retry['record']['reservation_lock']), (0, 1, 'recovered'))


class LockMetadata(unittest.TestCase):
    def test_description_names_holder_within_github_limit(self):
        with patch.dict(os.environ, {'GITHUB_RUN_ID': '99999999999999999999', 'GITHUB_RUN_ATTEMPT': '999999'}):
            worker = load_worker()
            text = worker.lock_description()
        self.assertLessEqual(len(text), 100)
        self.assertEqual(worker._HOLDER.search(text).groups(), ('99999999999999999999', '999999'))
        with patch.dict(os.environ, {'GITHUB_RUN_ID': 'abc', 'GITHUB_RUN_ATTEMPT': '1'}):
            self.assertIsNone(worker._HOLDER.search(worker.lock_description()))

    def test_generation_labels_are_distinct_and_valid(self):
        worker = load_worker()
        key = 'REAL-SHORT-V1-2026-10-30T08:00:00+00:00'
        names = [worker.lock_label_name(key if g == 1 else f'{key}#gen{g}') for g in (1, 2, 3)]
        self.assertEqual(len(set(names)), 3)
        self.assertTrue(all(len(n) <= 50 and n.startswith('sms-lock:') for n in names))
        self.assertEqual(names[0], 'sms-lock:' + key)  # generation 1 unchanged from R3


spec = importlib.util.spec_from_file_location('probe22', ROOT / '22_probe_lock_permissions.py')
probe = importlib.util.module_from_spec(spec)
spec.loader.exec_module(probe)

ENV = {'GITHUB_ACTIONS': 'true', 'GITHUB_REPOSITORY': 'example/research', 'GH_TOKEN': 'dummy-only',
       'GITHUB_RUN_ID': '40931080705', 'GITHUB_RUN_ATTEMPT': '1'}


def fake_api(statuses):
    calls = []

    def request(method, url, token, payload=None):
        calls.append((method, url, payload))
        result = statuses[{'POST': 'create', 'DELETE': 'delete', 'GET': 'runs'}[method]]
        if isinstance(result, Exception):
            raise result
        return result
    request.calls = calls
    return request


class PermissionProbe(unittest.TestCase):
    OK = {'create': 201, 'delete': 204, 'runs': 200}

    def statuses(self, **changes):
        return {**self.OK, **changes}

    def test_all_permissions_ok_and_only_probe_label_touched(self):
        api = fake_api(self.statuses())
        self.assertEqual(probe.probe(ENV, api), {'lock_label_permission': 'ok', 'run_status_permission': 'ok'})
        methods = [(m, u.split('/repos/example/research/')[1]) for m, u, _ in api.calls]
        self.assertEqual(methods, [('POST', 'labels'), ('DELETE', 'labels/sms-probe%3A40931080705-1'), ('GET', 'actions/runs/40931080705')])
        self.assertEqual(api.calls[0][2]['name'], 'sms-probe:40931080705-1')
        self.assertFalse(any('issues' in u or 'sms-lock' in u for _, u, _ in api.calls))

    def test_failure_classification(self):
        cases = [(dict(create=403), 'create_forbidden', 'ok'), (dict(create=500), 'create_error', 'ok'),
                 (dict(create=422), 'ok', 'ok'), (dict(delete=403), 'delete_forbidden', 'ok'),
                 (dict(delete=404), 'delete_error', 'ok'), (dict(runs=403), 'ok', 'forbidden'),
                 (dict(runs=502), 'ok', 'error'), (dict(create=OSError('down')), 'create_error', 'ok'),
                 (dict(runs=OSError('down')), 'ok', 'error')]
        for change, label_result, runs_result in cases:
            with self.subTest(change=change):
                result = probe.probe(ENV, fake_api(self.statuses(**change)))
                self.assertEqual((result['lock_label_permission'], result['run_status_permission']), (label_result, runs_result))

    def test_failed_create_skips_delete(self):
        api = fake_api(self.statuses(create=403))
        probe.probe(ENV, api)
        self.assertNotIn('DELETE', [m for m, _, _ in api.calls])

    def test_not_attempted_outside_actions_or_without_identity(self):
        for change in ({'GITHUB_ACTIONS': ''}, {'GH_TOKEN': ''}, {'GITHUB_REPOSITORY': 'bad repo'}, {'GITHUB_RUN_ID': ''}):
            with self.subTest(change=change):
                api = fake_api({})
                self.assertEqual(set(probe.probe({**ENV, **change}, api).values()), {'not_attempted'})
                self.assertEqual(api.calls, [])

    def test_main_updates_sanitised_record_and_always_exits_zero(self):
        import tempfile, contextlib
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / 'record.json'
            path.write_text(json.dumps({'schema_version': 1, 'record_type': 'worker_run', 'outcome': 'completed',
                                        'error_category': 'none'}), encoding='utf-8')
            out = io.StringIO()
            with contextlib.redirect_stdout(out):
                self.assertEqual(probe.main({**ENV, 'RUN_RECORD_FILE': str(path)}, fake_api(self.statuses(runs=403))), 0)
            record = json.loads(path.read_text(encoding='utf-8'))
            self.assertEqual((record['lock_label_permission'], record['run_status_permission'], record['outcome']),
                             ('ok', 'forbidden', 'completed'))
            self.assertIn('::warning::', out.getvalue()); self.assertNotIn('dummy-only', out.getvalue())
            with contextlib.redirect_stdout(io.StringIO()):
                self.assertEqual(probe.main({**ENV, 'RUN_RECORD_FILE': str(Path(tmp) / 'missing.json')}, fake_api(self.statuses())), 0)

                def explode(*a, **k):
                    raise RuntimeError('boom')
                self.assertEqual(probe.main({**ENV, 'RUN_RECORD_FILE': str(path)}, explode), 0)


class HeartbeatPayloadHeadroom(unittest.TestCase):
    def test_every_payload_field_at_realistic_maximum_still_fits(self):
        # Before this check, adding fields silently emptied failure-run payloads at the old 1000-byte cap.
        spec = importlib.util.spec_from_file_location('hb_headroom', ROOT / '20_send_heartbeat.py')
        hb = importlib.util.module_from_spec(spec); spec.loader.exec_module(hb)
        record = {k: 'x' * 32 for k in hb.PAYLOAD_FIELDS}  # longer than any enumerated value or ISO time
        record.update(worker_exit_code=1, forecast_http_status=503, duration_seconds=599.9, dispatch_delay_seconds=86400.0)
        body = hb.build_payload(record, {})
        self.assertGreater(len(body), 0)
        self.assertLessEqual(len(body), hb.MAX_BODY_BYTES)
        self.assertEqual(set(json.loads(body)), set(hb.PAYLOAD_FIELDS))


class ActionVersions(unittest.TestCase):
    def test_both_workflows_use_node24_action_majors(self):
        # v4 / v5 run on the deprecated Node.js 20; v7 of both run on Node.js 24 with the same inputs used here.
        for name in ('scheduled-storm-sms.yml', 'verify-monitoring.yml'):
            text = (ROOT / '.github' / 'workflows' / name).read_text(encoding='utf-8')
            uses = re.findall(r'uses: (actions/[a-z-]+@\S+)', text)
            self.assertEqual(sorted(uses), ['actions/checkout@v7', 'actions/setup-python@v7'], name)
            self.assertIn("python-version: '3.12'", text); self.assertIn('cache: pip', text)


class WorkflowPermissions(unittest.TestCase):
    def setUp(self):
        self.text = PRODUCTION.read_text(encoding='utf-8').replace('\r', '')

    def test_only_read_only_actions_permission_added(self):
        block = self.text.split('permissions:\n', 1)[1].split('concurrency:', 1)[0]
        grants = re.findall(r'^  ([a-z-]+): (\w+)$', block, re.M)
        self.assertEqual(grants, [('contents', 'read'), ('issues', 'write'), ('actions', 'read')])

    def test_probe_step_is_monitoring_only_and_before_publisher(self):
        step = self.text.split('- name: Probe duplicate-lock permissions (monitoring only)', 1)[1].split('\n      - ', 1)[0]
        for line in ('if: ${{ always() }}', 'continue-on-error: true', 'timeout-minutes: 2',
                     'RUN_RECORD_FILE: ${{ runner.temp }}/run_record.json', 'run: python3 22_probe_lock_permissions.py'):
            self.assertIn(line, step)
        order = [self.text.index(s) for s in ('run: python 18_scheduled_sms_worker.py --test-sms',
                                              'run: python3 22_probe_lock_permissions.py',
                                              'run: python 19_publish_run_record.py', 'run: python3 20_send_heartbeat.py\n')]
        self.assertEqual(order, sorted(order))


if __name__ == '__main__':
    unittest.main()
