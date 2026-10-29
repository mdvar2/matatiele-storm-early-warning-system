"""R2 heartbeat monitoring: mapping, isolation, bounded retries and redaction.

All network operations are replaced by a fake sender: no real heartbeat request,
forecast request, GitHub call or SMS occurs. Records come from the real R1 worker
code path (via the R1 test harness) to prove compatibility.
"""
import contextlib
import importlib.util
import io
import json
import os
from pathlib import Path
import socket
import unittest
import urllib.error
from unittest.mock import patch

import run_record
from test_run_record import (RecordHarness, failed_process, OUT_MODEL_OK, OUT_REQUEST,
                             DUMMY_NUMBER, DUMMY_SID, DUMMY_TOKEN, DUMMY_GH)
from test_scheduled_sms_worker import load_worker

ROOT = Path(__file__).resolve().parents[1]
URLS = {'HC_EXECUTION_URL': 'https://hc-ping.example/aaaaaaaa-1111', 'HC_FORECAST_URL': 'https://hc-ping.example/bbbbbbbb-2222',
        'HC_FAILURE_URL': 'https://hc-ping.example/cccccccc-3333', 'HC_WARNING_URL': 'https://hc-ping.example/dddddddd-4444'}
CHECK_OF = {v: k for k, v in {'HB-1': URLS['HC_EXECUTION_URL'], 'HB-2': URLS['HC_FORECAST_URL'],
                              'HB-3': URLS['HC_FAILURE_URL'], 'HB-4': URLS['HC_WARNING_URL']}.items()}


def load_heartbeat():
    spec = importlib.util.spec_from_file_location('heartbeat', ROOT / '20_send_heartbeat.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class FakeSender:
    """Records every ping; returns (status, body) like http_send. Scripted effects per call."""

    def __init__(self, effects=None):
        self.calls, self.effects = [], list(effects or [])

    def __call__(self, url, body, timeout):
        self.calls.append((url, body, timeout))
        if self.effects:
            effect = self.effects.pop(0)
            if isinstance(effect, BaseException):
                raise effect
            return effect
        return 200, b'OK'

    def pings(self):
        out = []
        for url, _, _ in self.calls:
            base = next(b for b in CHECK_OF if url.startswith(b))
            out.append((CHECK_OF[base], url[len(base):]))
        return out


class HeartbeatHarness(RecordHarness):
    def setUp(self):
        super().setUp()
        os.environ.update(URLS)
        self.hb = load_heartbeat()

    def heartbeat(self, argv=(), sender=None, environ=None):
        sender = sender or FakeSender()
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            code, results = self.hb.main(list(argv), environ=dict(os.environ) if environ is None else environ,
                                         sender=sender, sleep=lambda s: None)
        return code, results, sender, out.getvalue()

    def record_from_worker(self, probability=.10, worker=None, **kwargs):
        self.run_worker(probability=probability, worker=worker, **kwargs)
        return self.record_file

    def warning_run(self, send=None, reserve=7, report_error=None, configured=True, ledger_down=False):
        worker = load_worker()
        send_kwargs = {'side_effect': send} if isinstance(send, Exception) else {'return_value': send or {'status': 'sent', 'sent': True}}
        ledger = (patch.object(worker.requests, 'request', side_effect=worker.requests.ConnectionError('down'))
                  if ledger_down else patch.object(worker, 'reserve_hour', return_value=reserve))
        with patch('sms_alert.sms_is_configured', return_value=configured), patch('sms_alert.send_storm_sms', **send_kwargs), \
             ledger, patch.object(worker, 'report', side_effect=report_error):
            self.run_worker(probability=.40, worker=worker)


class Semantics(HeartbeatHarness):
    def test_execution_start_pings_hb1_start_only_without_body(self):
        code, results, sender, _ = self.heartbeat(['--start'])
        self.assertEqual(code, 0)
        self.assertEqual(sender.pings(), [('HB-1', '/start')])
        self.assertIsNone(sender.calls[0][1] or None)

    def test_successful_execution_with_valid_prediction(self):
        self.record_from_worker(probability=.10)
        code, results, sender, _ = self.heartbeat()
        self.assertEqual(code, 0)
        self.assertEqual(sender.pings(), [('HB-3', ''), ('HB-2', ''), ('HB-1', '')])
        self.assertEqual(set(results.values()), {'sent'})

    def test_failed_execution_and_forecast_failure(self):
        stdout = OUT_MODEL_OK + OUT_REQUEST + 'HTTP status: 503\n\nLive forecast request failed.\n'
        self.run_worker(subprocess_effect=failed_process(stdout))
        code, _, sender, _ = self.heartbeat()
        self.assertEqual(code, 0)
        self.assertEqual(sender.pings(), [('HB-3', '/fail'), ('HB-1', '')])  # no HB-2, no HB-4
        body = json.loads(sender.calls[0][1])
        self.assertEqual((body['error_category'], body['error_detail'], body['forecast_retrieval']),
                         ('forecast_retrieval_failure', 'http_503', 'failed'))

    def test_stale_prediction_is_not_a_valid_prediction(self):
        stale = dict(self.row, forecast_retrieved_at='2020-01-01T00:00:00+00:00')
        self.run_worker(rows=[stale])
        _, _, sender, _ = self.heartbeat()
        self.assertEqual(sender.pings(), [('HB-3', '/fail'), ('HB-1', '')])

    def test_genuine_warning_failures_ping_hb4_first(self):
        cases = {'provider failed': dict(send={'status': 'failed', 'sent': False}),
                 'partial': dict(send={'status': 'partial', 'sent': False}),
                 'provider exception': dict(send=RuntimeError('provider')),
                 'ledger unavailable': dict(ledger_down=True),
                 'sms not configured': dict(configured=False)}
        for label, kwargs in cases.items():
            with self.subTest(label):
                self.record_file.unlink(missing_ok=True)
                self.warning_run(**kwargs)
                _, _, sender, _ = self.heartbeat()
                self.assertEqual(sender.pings()[:2], [('HB-4', '/fail'), ('HB-3', '/fail')])

    def test_accepted_or_suppressed_warnings_never_ping_hb4(self):
        cases = {'sent': dict(), 'provider duplicate': dict(send={'status': 'duplicate', 'sent': False}),
                 'already reserved (duplicate suppression)': dict(reserve=None),
                 'sent but ledger comment failed': dict(report_error=RuntimeError('comment failed'))}
        for label, kwargs in cases.items():
            with self.subTest(label):
                self.record_file.unlink(missing_ok=True)
                self.warning_run(**kwargs)
                _, _, sender, _ = self.heartbeat()
                checks = [c for c, _ in sender.pings()]
                self.assertNotIn('HB-4', checks)
                expected_hb3 = '/fail' if label.startswith('sent but') else ''
                self.assertIn(('HB-3', expected_hb3), sender.pings())

    def test_dry_run_and_connectivity_tests_never_ping_hb4(self):
        self.run_worker(args=('--dry-run',), probability=.9)
        _, _, sender, _ = self.heartbeat()
        self.assertNotIn('HB-4', [c for c, _ in sender.pings()])
        os.environ.update(GITHUB_EVENT_NAME='workflow_dispatch', SMS_TEST_CONFIRMED='true')
        worker = load_worker()
        with patch('sms_alert.sms_is_configured', return_value=True), patch('sms_alert._get_recipients', return_value=['x']), \
             patch('sms_alert.send_test_sms', return_value={'status': 'failed', 'sent': False}), \
             patch.object(worker, 'reserve_hour', return_value=3), patch.object(worker, 'report'):
            self.run_worker(args=('--test-sms',), worker=worker)
        _, _, sender, _ = self.heartbeat()
        self.assertEqual(sender.pings(), [('HB-3', '/fail'), ('HB-1', '')])

    def test_hb4_never_receives_a_success_ping(self):
        """A later successful run must not conceal an unresolved genuine warning failure."""
        hb = self.hb
        for record in ([run_record.new_record()] + [dict(run_record.new_record(), **changes) for changes in (
                {'worker_exit_code': 0, 'mode': 'live', 'warning_decision': 'warning_eligible', 'sms_submission': 'sent'},
                {'worker_exit_code': 0, 'mode': 'live', 'warning_decision': 'below_threshold'},
                {'worker_exit_code': 1, 'mode': 'live', 'warning_decision': 'warning_eligible', 'sms_submission': 'failed'})]):
            self.assertNotIn(('HB-4', ''), hb.plan_pings(record))

    def test_missing_record_is_a_classified_failure(self):
        os.environ['RUN_RECORD_FILE'] = str(Path(self.temp.name) / 'does-not-exist.json')
        _, _, sender, _ = self.heartbeat()
        self.assertEqual(sender.pings(), [('HB-3', '/fail'), ('HB-1', '')])
        self.assertEqual(json.loads(sender.calls[0][1])['record_type'], 'worker_record_missing')


class Configuration(HeartbeatHarness):
    def test_missing_configuration_skips_safely(self):
        self.record_from_worker()
        env = {k: v for k, v in os.environ.items() if k not in URLS}
        code, results, sender, out = self.heartbeat(environ=env)
        self.assertEqual(code, 0); self.assertEqual(sender.calls, [])
        self.assertEqual(set(results.values()), {'skipped_not_configured'})
        self.assertIn('no heartbeat secrets configured', out)

    def test_partial_configuration_pings_only_configured_checks(self):
        self.record_from_worker()
        env = {k: v for k, v in os.environ.items() if k not in ('HC_FORECAST_URL', 'HC_WARNING_URL')}
        _, results, sender, _ = self.heartbeat(environ=env)
        self.assertEqual(sorted(c for c, _ in sender.pings()), ['HB-1', 'HB-3'])
        self.assertEqual(results['HB-2'], 'skipped_not_configured')

    def test_invalid_endpoint_is_skipped_without_revealing_it(self):
        self.record_from_worker()
        for bad in ('http://insecure.example/abc', 'not a url', 'https://hc-ping.example/x y', 'ftp://x/y'):
            with self.subTest(bad=bad):
                env = dict(os.environ, HC_EXECUTION_URL=bad)
                _, results, sender, out = self.heartbeat(environ=env)
                self.assertEqual(results['HB-1'], 'skipped_invalid_endpoint')
                self.assertNotIn(bad, out)
                self.assertNotIn('HB-1', [c for c, _ in sender.pings()])

    def test_rejected_endpoint_is_not_retried(self):
        self.record_from_worker()
        err = urllib.error.HTTPError(URLS['HC_FAILURE_URL'], 404, 'Not Found', {}, None)
        _, results, sender, _ = self.heartbeat(sender=FakeSender([err]))
        self.assertEqual(results['HB-3'], 'endpoint_not_found')
        self.assertEqual([c for c, _ in sender.pings()].count('HB-3'), 1)


class Resilience(HeartbeatHarness):
    def test_timeout_is_bounded_and_retried(self):
        self.record_from_worker()
        timeout = urllib.error.URLError(socket.timeout('timed out'))
        _, results, sender, _ = self.heartbeat(sender=FakeSender([timeout] * 3))
        self.assertEqual(results['HB-3'], 'timeout')
        self.assertEqual([c for c, _ in sender.pings()].count('HB-3'), 3)
        self.assertTrue(all(t <= self.hb.ATTEMPT_TIMEOUT_S for _, _, t in sender.calls))
        self.assertEqual(results['HB-1'], 'sent')  # later checks still attempted

    def test_total_time_budget_stops_further_attempts(self):
        self.record_from_worker()
        ticks = iter([0, 0, 59.5, 59.9, 61, 61, 61, 61, 61, 61, 61, 61])
        with patch.object(self.hb.time, 'monotonic', side_effect=lambda: next(ticks, 999)):
            out = io.StringIO()
            with contextlib.redirect_stdout(out):
                code, results = self.hb.main([], environ=dict(os.environ), sender=FakeSender([TimeoutError()] * 9),
                                             sleep=lambda s: None, clock=lambda: 0)
        self.assertEqual(code, 0)
        self.assertTrue(any(v.endswith('time_budget') for v in results.values()), results)

    def test_monitoring_service_unavailable(self):
        self.record_from_worker()
        unavailable = urllib.error.HTTPError(URLS['HC_FAILURE_URL'], 503, 'Unavailable', {}, None)
        refused = urllib.error.URLError(ConnectionRefusedError('refused'))
        effects = [unavailable] * 3 + [refused] * 3 + [refused] * 3
        code, results, sender, out = self.heartbeat(sender=FakeSender(effects))
        self.assertEqual(code, 0)
        self.assertEqual((results['HB-3'], results['HB-2'], results['HB-1']), ('http_503', 'network_error', 'network_error'))
        self.assertIn('::warning::Heartbeat: HB-3 http_503', out)

    def test_unexpected_errors_never_raise(self):
        self.record_from_worker()
        code, results, _, _ = self.heartbeat(sender=FakeSender([ValueError('odd')] * 12))
        self.assertEqual(code, 0)
        self.assertTrue(all(v.startswith('error_') for v in results.values()))
        with patch.object(self.hb, 'plan_pings', side_effect=RuntimeError('boom')):
            code, results, _, out = self.heartbeat()
        self.assertEqual(code, 0); self.assertIn('unexpected heartbeat error (RuntimeError)', out)

    def test_works_without_run_record_module(self):
        self.record_from_worker()
        self.hb.run_record = None
        code, _, sender, _ = self.heartbeat()
        self.assertEqual(code, 0); self.assertTrue(sender.calls)

    def test_heartbeat_cannot_change_worker_outcome(self):
        """The worker exits before heartbeats run; heartbeats are a separate process and step."""
        worker = load_worker()
        with patch('sms_alert.sms_is_configured', return_value=True), \
             patch('sms_alert.send_storm_sms', return_value={'status': 'sent', 'sent': True}) as send, \
             patch.object(worker, 'reserve_hour', return_value=2), patch.object(worker, 'report'):
            r = self.run_worker(probability=.40, worker=worker)
        before = self.record_file.read_bytes()
        code, _, _, _ = self.heartbeat(sender=FakeSender([OSError('down')] * 12))
        self.assertEqual((r['code'], code, send.call_count), (0, 0, 1))
        self.assertEqual(self.record_file.read_bytes(), before)  # record is read-only to heartbeats


class Privacy(HeartbeatHarness):
    def test_payload_excludes_probability_free_text_and_identifiers(self):
        self.warning_run(send={'status': 'failed', 'sent': False})
        _, _, sender, _ = self.heartbeat()
        body = json.loads(sender.calls[0][1])
        for key in ('storm_probability', 'unvalidated_probability', 'error_message', 'ledger_issue_number',
                    'workflow_run_id', 'commit', 'forecast_retrieved_utc', 'sms_note'):
            self.assertNotIn(key, body)
        self.assertLessEqual(len(sender.calls[0][1]), self.hb.MAX_BODY_BYTES)
        self.assertEqual(set(body), set(self.hb.PAYLOAD_FIELDS))

    def test_planted_sensitive_values_never_leave(self):
        record = dict(run_record.new_record(), worker_exit_code=1, error_detail=f'oops {DUMMY_NUMBER}',
                      exception_type=DUMMY_SID, sms_submission=DUMMY_TOKEN)
        self.record_file.write_text(json.dumps(record), encoding='utf-8')
        _, _, sender, out = self.heartbeat()
        sent = b''.join(b for _, b, _ in sender.calls if b).decode() + out
        for secret in (DUMMY_NUMBER, DUMMY_SID, DUMMY_TOKEN, DUMMY_GH, *URLS.values()):
            self.assertNotIn(secret, sent)

    def test_body_withheld_if_secret_detected(self):
        payload = self.hb.build_payload({'error_detail': 'x', 'error_category': 'none'},
                                        dict(os.environ, HC_EXECUTION_URL='https://hc-ping.example/none'))
        self.assertTrue(payload)
        leaked = self.hb.build_payload({'error_detail': DUMMY_TOKEN}, dict(os.environ))
        self.assertEqual(leaked, b'')

    def test_ping_urls_never_logged(self):
        self.record_from_worker()
        for effects in ([], [urllib.error.URLError('down')] * 12):
            _, _, _, out = self.heartbeat(sender=FakeSender(effects))
            for url in URLS.values():
                self.assertNotIn(url, out)
            self.assertNotIn('hc-ping', out)


class Transport(unittest.TestCase):
    def test_http_send_uses_bounded_timeout_post_with_body_and_get_without(self):
        hb = load_heartbeat()
        captured = []

        reads = []

        class Response:
            status = 200
            def __enter__(self): return self
            def __exit__(self, *a): return False
            def read(self, n=-1):
                reads.append(n)
                return (b'OK' + b'x' * 500)[:n] if n >= 0 else b'OK' + b'x' * 500

        def fake_urlopen(request, timeout):
            captured.append((request.get_method(), request.full_url, request.data, timeout))
            return Response()
        with patch.object(hb.urllib.request, 'urlopen', side_effect=fake_urlopen):
            status, body = hb.http_send('https://hc-ping.example/u/fail', b'{"a":1}', 8)
            hb.http_send('https://hc-ping.example/u/start', b'', 5)
        self.assertEqual(status, 200)
        self.assertEqual(captured[0], ('POST', 'https://hc-ping.example/u/fail', b'{"a":1}', 8))
        self.assertEqual(captured[1], ('GET', 'https://hc-ping.example/u/start', None, 5))
        self.assertEqual(reads, [hb.MAX_RESPONSE_BYTES + 1] * 2)  # bounded read, never unbounded
        self.assertEqual(len(body), hb.MAX_RESPONSE_BYTES + 1)
        self.assertEqual(hb.classify_response(status, body), ('unexpected_response_oversized', False))


class ResponseValidation(HeartbeatHarness):
    """HTTP 200 alone is never proof of acceptance (documented Healthchecks.io responses)."""

    def classify(self, status, body):
        return self.hb.classify_response(status, body)

    def test_valid_successful_response(self):
        for body in (b'OK', b'OK\n', b'  OK\r\n'):
            self.assertEqual(self.classify(200, body), ('sent', False))
        self.record_from_worker()
        _, results, _, _ = self.heartbeat(sender=FakeSender([(200, b'OK')] * 3))
        self.assertEqual(set(results.values()), {'sent'})

    def test_documented_rejections_and_strict_matching(self):
        cases = {b'OK (not found)': 'endpoint_not_found', b'OK (rate limited)': 'rate_limited',
                 b'': 'unexpected_response_empty', b'   \n': 'unexpected_response_empty',
                 b'NOT OK': 'unexpected_response', b'OKAY': 'unexpected_response', b'ok': 'unexpected_response',
                 b'OK (not found) trailing': 'unexpected_response', b'<html>captive portal</html>': 'unexpected_response',
                 b'OK' + b' ' * 100: 'unexpected_response_oversized'}
        for body, outcome in cases.items():
            with self.subTest(body=body):
                self.assertEqual(self.classify(200, body), (outcome, False))
        self.assertEqual(self.classify(200, None), ('unexpected_response', False))

    def test_non_200_statuses(self):
        self.assertEqual(self.classify(201, b'Created'), ('http_201', False))
        self.assertEqual(self.classify(204, b''), ('http_204', False))
        self.assertEqual(self.classify(400, b''), ('invalid_url_format', False))
        self.assertEqual(self.classify(404, b''), ('endpoint_not_found', False))
        self.assertEqual(self.classify(409, b''), ('ambiguous_endpoint', False))
        self.assertEqual(self.classify(429, b''), ('rate_limited', False))
        self.assertEqual(self.classify(500, b''), ('http_500', True))
        self.assertEqual(self.classify(503, b''), ('http_503', True))

    def test_unknown_or_deleted_url_is_not_sent_and_not_retried(self):
        self.record_from_worker()
        responses = [(200, b'OK (not found)')] * 3  # unknown and deleted checks both answer "OK (not found)"
        _, results, sender, out = self.heartbeat(sender=FakeSender(responses))
        self.assertEqual(set(results.values()), {'endpoint_not_found'})
        self.assertEqual(len(sender.calls), 3)  # one attempt per check, no retries
        self.assertIn('::warning::Heartbeat: HB-1 endpoint_not_found', out)
        slug_deleted = urllib.error.HTTPError(URLS['HC_FAILURE_URL'], 404, 'Not Found', {}, None)
        _, results, sender, _ = self.heartbeat(sender=FakeSender([slug_deleted]))
        self.assertEqual(results['HB-3'], 'endpoint_not_found'); self.assertEqual(len(sender.calls), 3)

    def test_rate_limited_is_not_blindly_retried(self):
        self.record_from_worker()
        _, results, sender, _ = self.heartbeat(sender=FakeSender([(200, b'OK (rate limited)')]))
        self.assertEqual(results['HB-3'], 'rate_limited')
        self.assertEqual([c for c, _ in sender.pings()].count('HB-3'), 1)
        slug_429 = urllib.error.HTTPError(URLS['HC_FAILURE_URL'], 429, 'Too Many', {}, None)
        _, results, sender, _ = self.heartbeat(sender=FakeSender([slug_429]))
        self.assertEqual(results['HB-3'], 'rate_limited')
        self.assertEqual([c for c, _ in sender.pings()].count('HB-3'), 1)

    def test_unexpected_and_oversized_bodies_are_not_sent_or_echoed(self):
        self.record_from_worker()
        leaky = b'OK (not found) ' + URLS['HC_FAILURE_URL'].encode() + b' ' + DUMMY_TOKEN.encode()
        for response, outcome in [((200, b'<html>login</html>'), 'unexpected_response'),
                                  ((200, b''), 'unexpected_response_empty'),
                                  ((200, leaky), 'unexpected_response_oversized'),  # 78 bytes > limit
                                  ((200, b'OK (not found) ' + DUMMY_TOKEN[:8].encode()), 'unexpected_response'),
                                  ((200, b'OK' + b'x' * 200), 'unexpected_response_oversized')]:
            with self.subTest(outcome=outcome):
                _, results, sender, out = self.heartbeat(sender=FakeSender([response]))
                self.assertEqual(results['HB-3'], outcome)
                self.assertEqual([c for c, _ in sender.pings()].count('HB-3'), 1)
                for fragment in ('<html>', 'login', DUMMY_TOKEN, URLS['HC_FAILURE_URL'], 'hc-ping'):
                    self.assertNotIn(fragment, out)

    def test_server_errors_are_retried_within_bounds(self):
        self.record_from_worker()
        _, results, sender, _ = self.heartbeat(sender=FakeSender([(500, b''), (502, b''), (200, b'OK')]))
        self.assertEqual(results['HB-3'], 'sent')
        self.assertEqual([c for c, _ in sender.pings()].count('HB-3'), 3)

    def test_rejected_hb3_and_hb4_failure_pings_are_never_marked_sent(self):
        self.warning_run(send={'status': 'failed', 'sent': False})
        rejected = [(200, b'OK (not found)'), (200, b'OK (rate limited)')]
        _, results, sender, out = self.heartbeat(sender=FakeSender(rejected + [(200, b'OK')] * 2))
        self.assertEqual(sender.pings()[:2], [('HB-4', '/fail'), ('HB-3', '/fail')])
        self.assertEqual((results['HB-4'], results['HB-3']), ('endpoint_not_found', 'rate_limited'))
        self.assertIn('::warning::Heartbeat: HB-4 endpoint_not_found', out)
        self.assertIn('::warning::Heartbeat: HB-3 rate_limited', out)
        self.assertNotIn('HB-4 sent', out); self.assertNotIn('HB-3 sent', out)


class WorkflowAndCode(unittest.TestCase):
    def setUp(self):
        self.workflow = (ROOT / '.github/workflows/scheduled-storm-sms.yml').read_text(encoding='utf-8')
        self.lines = self.workflow.splitlines()

    def step(self, name):
        start = next(i for i, l in enumerate(self.lines) if l.strip() == f'- name: {name}')
        end = next((i for i in range(start + 1, len(self.lines)) if self.lines[i].startswith('      - ')), len(self.lines))
        return '\n'.join(self.lines[start:end]), start

    def test_steps_are_isolated_and_ordered(self):
        start_step, s = self.step('Heartbeat - run started (monitoring only)')
        end_step, e = self.step('Heartbeat - report outcome (monitoring only)')
        _, publish = self.step('Publish sanitised run record (monitoring only)')
        _, worker = self.step('Genuine forecast and automatic SMS check')
        checkout = next(i for i, l in enumerate(self.lines) if 'actions/checkout@v4' in l)
        setup = next(i for i, l in enumerate(self.lines) if 'actions/setup-python@v5' in l)
        self.assertTrue(checkout < s < setup < worker < publish < e)
        for text in (start_step, end_step):
            self.assertIn('continue-on-error: true', text); self.assertIn('timeout-minutes: 2', text)
        self.assertIn('if: ${{ always() }}', end_step)
        self.assertIn('run: python3 20_send_heartbeat.py --start', start_step)
        self.assertIn('run: python3 20_send_heartbeat.py', end_step)

    def test_secrets_only_reach_heartbeat_steps(self):
        job_env = self.workflow.split('    steps:', 1)[0]
        for name in URLS:
            self.assertNotIn(name, job_env)
            holders = [i for i, l in enumerate(self.lines) if name in l]
            for i in holders:
                step_name = next(self.lines[j] for j in range(i, -1, -1) if self.lines[j].startswith('      - '))
                self.assertIn('Heartbeat', step_name, name)
            self.assertTrue(all(f'${{{{ secrets.{name} }}}}' in self.lines[i] for i in holders))

    def test_existing_configuration_unchanged(self):
        self.assertIn("- cron: '12 * * * *'", self.workflow)
        # R3 lock recovery added read-only `actions: read`; nothing else may change.
        self.assertIn('permissions:\n  contents: read\n  issues: write\n'
                      '  # Read-only: lets a later run confirm that the holder of an abandoned SMS lock has ended.\n'
                      '  actions: read\nconcurrency:', self.workflow.replace('\r', ''))
        self.assertIn("RUN_RECORD_PUBLISH: 'false'", self.workflow)
        self.assertEqual(self.workflow.count('python 18_scheduled_sms_worker.py --live'), 1)
        self.assertEqual(self.workflow.count('python 18_scheduled_sms_worker.py --test-sms'), 1)

    def test_no_ping_urls_hardcoded_anywhere_tracked(self):
        import re
        pattern = re.compile(r'https?://hc-ping\.com/[0-9a-fA-F-]{8,}')
        for path in ['20_send_heartbeat.py', '.github/workflows/scheduled-storm-sms.yml', 'run_record.py',
                     '19_publish_run_record.py', '18_scheduled_sms_worker.py', 'README_SMS_SETUP.md']:
            self.assertIsNone(pattern.search((ROOT / path).read_text(encoding='utf-8')), path)

    def test_heartbeat_code_is_stdlib_and_never_touches_sms_or_ledger(self):
        import ast
        source = (ROOT / '20_send_heartbeat.py').read_text(encoding='utf-8')
        tree = ast.parse(source)
        modules = {a.name.split('.')[0] for n in ast.walk(tree) if isinstance(n, ast.Import) for a in n.names}
        modules |= {n.module.split('.')[0] for n in ast.walk(tree) if isinstance(n, ast.ImportFrom)}
        self.assertLessEqual(modules, {'json', 'os', 're', 'sys', 'time', 'urllib', 'pathlib', 'run_record'})
        for forbidden in ('send_storm_sms', 'send_test_sms', 'twilio', 'messages.create', 'SMS-LEDGER', 'subprocess', 'predict_proba', 'joblib'):
            self.assertNotIn(forbidden, source)


if __name__ == '__main__':
    unittest.main()
