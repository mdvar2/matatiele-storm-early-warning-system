"""Coverage metric (21_measure_execution_coverage.py) on synthetic run metadata; no network."""
import contextlib
import importlib.util
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('coverage21', ROOT / '21_measure_execution_coverage.py')
cov = importlib.util.module_from_spec(spec)
spec.loader.exec_module(cov)

PATH = '.github/workflows/scheduled-storm-sms.yml'


def run(i, when, event='schedule', conclusion='success', path=PATH):
    return {'id': i, 'event': event, 'conclusion': conclusion, 'created_at': when, 'run_started_at': when, 'path': path}


class CoverageMetric(unittest.TestCase):
    def test_perfect_hourly_schedule(self):
        runs = [run(h, f'2026-11-01T{h:02d}:12:00Z') for h in range(24)]
        res = cov.measure(runs)
        self.assertEqual((res['slots'], res['covered_slots'], res['slot_coverage']), (24, 24, 1.0))
        self.assertEqual((res['freshness_75min'], res['gaps_over_75min'], res['gap_minutes_max']), (1.0, 0, 60.0))
        self.assertEqual(res['start_minute_median'], 12.0)

    def test_sparse_schedule_and_success_coverage(self):
        runs = [run(1, '2026-11-01T00:20:00Z'), run(2, '2026-11-01T04:40:00Z', conclusion='failure'),
                run(3, '2026-11-01T09:05:00Z')]
        res = cov.measure(runs)
        self.assertEqual((res['slots'], res['covered_slots'], res['success_slots']), (10, 3, 2))
        self.assertEqual((res['slot_coverage'], res['success_coverage']), (0.3, 0.2))
        # Boundaries 01:00..09:00: fresh only at 01:00 (40 min after 00:20) and 05:00 (20 min after 04:40).
        self.assertEqual((res['freshness_boundaries'], res['freshness_75min']), (9, round(2 / 9, 4)))
        self.assertEqual(res['conclusions'], {'failure': 1, 'success': 2})

    def test_two_runs_in_one_slot_count_once(self):
        runs = [run(1, '2026-11-01T00:05:00Z', 'workflow_dispatch'), run(2, '2026-11-01T00:12:00Z'),
                run(3, '2026-11-01T01:05:00Z', 'workflow_dispatch')]
        both = cov.measure(runs, ('schedule', 'workflow_dispatch'))
        self.assertEqual((both['runs'], both['covered_slots'], both['slots'], both['run_to_slot_ratio']), (3, 2, 2, 1.5))
        self.assertEqual(cov.measure(runs, ('schedule',))['runs'], 1)

    def test_freshness_limit_is_inclusive_75_minutes(self):
        on_limit = cov.measure([run(1, '2026-11-01T00:45:00Z'), run(2, '2026-11-01T02:30:00Z')])
        # 01:00 is 15 min after 00:45; 02:00 is exactly 75 min after 00:45.
        self.assertEqual(on_limit['freshness_75min'], 1.0)
        late = cov.measure([run(1, '2026-11-01T00:44:00Z'), run(2, '2026-11-01T02:30:00Z')])  # 76 min at 02:00
        self.assertEqual(late['freshness_75min'], 0.5)

    def test_explicit_window_counts_empty_hours_and_ignores_other_workflows(self):
        runs = [run(1, '2026-11-01T05:12:00Z'), run(2, '2026-11-01T06:12:00Z', path='.github/workflows/verify-monitoring.yml'),
                run(3, '2026-11-02T05:12:00Z')]
        res = cov.measure(runs, start=cov.parse_time('2026-11-01T00:00:00Z'), end=cov.parse_time('2026-11-01T23:59:59Z'))
        self.assertEqual((res['slots'], res['runs'], res['covered_slots']), (24, 1, 1))
        self.assertIn('error', cov.measure([], ('schedule',)))

    def test_cli_reads_saved_pages_and_deduplicates(self):
        rows = [run(h, f'2026-11-01T{h:02d}:12:00Z') for h in range(4)]
        with tempfile.TemporaryDirectory() as tmp:
            a, b = Path(tmp) / 'p1.json', Path(tmp) / 'p2.json'
            a.write_text(json.dumps({'total_count': 4, 'workflow_runs': rows[:3]}), encoding='utf-8')
            b.write_text(json.dumps(rows[2:]), encoding='utf-8')
            out = io.StringIO()
            with contextlib.redirect_stdout(out), patch.object(cov.urllib.request, 'urlopen', side_effect=AssertionError('no network')):
                cov.main(['--runs-json', str(a), str(b), '--events', 'schedule', '--json'])
        res = json.loads(out.getvalue())[0]
        self.assertEqual((res['runs'], res['slot_coverage']), (4, 1.0))

    def test_fetch_is_get_only_and_validates_repository(self):
        with self.assertRaises(ValueError):
            cov.fetch_runs('not a repo')
        seen = []

        class Response(io.BytesIO):
            def __enter__(self): return self
            def __exit__(self, *a): return False

        def fake_urlopen(request, timeout):
            seen.append((request.get_method(), request.full_url))
            return Response(json.dumps({'workflow_runs': [run(1, '2026-11-01T00:12:00Z')]}).encode())
        with patch.object(cov.urllib.request, 'urlopen', fake_urlopen):
            rows = cov.fetch_runs('example/research', since='2026-11-01')
        self.assertEqual(len(rows), 1)
        self.assertEqual(seen[0][0], 'GET')
        self.assertIn('/actions/workflows/scheduled-storm-sms.yml/runs?per_page=100&page=1&created=%3E%3D2026-11-01', seen[0][1])


if __name__ == '__main__':
    unittest.main()
