"""Controlled CAPE normalisation: rule, real inference script, worker validation and SMS isolation.

No network: Open-Meteo is replaced by supplied payloads, GitHub by FakeGitHub and
Twilio by mocks. Inference tests use the project's real Random Forest and threshold.
"""
import math
import subprocess
import tempfile
from pathlib import Path
import unittest
from unittest.mock import patch

import numpy as np
import pandas as pd

import cape_normalisation as rule
import inference_harness as harness
from test_r3_trigger import LedgerHarness
from test_scheduled_sms_worker import load_worker

ROOT = Path(__file__).resolve().parents[1]
INPUT_HOUR = '2026-10-29T19:00:00Z'
needs_model = unittest.skipUnless(harness.model_available(), 'Random Forest files not present in this checkout')


class Rule(unittest.TestCase):
    def test_boundaries_and_types(self):
        cases = [(-10, (0.0, 'normalised')), (-30.0, (0.0, 'normalised')), (0, (0.0, 'unchanged')),
                 (-0.0, (-0.0, 'unchanged')), (-50, (0.0, 'normalised')), (-50.0, (0.0, 'normalised')),
                 (-50.0001, (None, 'invalid')), (-60, (None, 'invalid')), (-110, (None, 'invalid')), (-1e12, (None, 'invalid')),
                 (1e-9, (1e-9, 'unchanged')), (2150.0, (2150.0, 'unchanged')), (np.float64(-10.0), (0.0, 'normalised')),
                 (np.float32(-20.0), (0.0, 'normalised')), (np.int64(5), (5.0, 'unchanged')),
                 (None, (None, 'invalid')), (float('nan'), (None, 'invalid')), (np.nan, (None, 'invalid')),
                 (float('inf'), (None, 'invalid')), (float('-inf'), (None, 'invalid')),
                 ('-10', (None, 'invalid')), ('abc', (None, 'invalid')), (True, (None, 'invalid')), (False, (None, 'invalid')),
                 (pd.NA, (None, 'invalid')), ([0], (None, 'invalid'))]
        for value, expected in cases:
            with self.subTest(value=value):
                self.assertEqual(rule.normalise_cape(value), expected)

    def test_tolerance_is_the_documented_provisional_value(self):
        self.assertEqual(rule.CAPE_NEGATIVE_TOLERANCE_J_KG, 50.0)

    def test_consistency_check(self):
        self.assertTrue(rule.consistent(0.0, -10.0, 'normalised'))
        self.assertTrue(rule.consistent(120.0, 120.0, 'unchanged'))
        self.assertTrue(rule.consistent(-60.0, -60.0, 'invalid'))
        self.assertTrue(rule.consistent(None, float('nan'), 'invalid'))
        for reported, raw, status in [(0.0, -10.0, 'unchanged'), (-10.0, -10.0, 'normalised'), (0.0, -60.0, 'normalised'),
                                      (0.0, 5.0, 'normalised'), (6.0, 5.0, 'unchanged'), (0.0, -10.0, 'repaired'),
                                      (0.0, None, 'normalised'), (True, -10.0, 'normalised')]:
            with self.subTest(reported=reported, raw=raw, status=status):
                self.assertFalse(rule.consistent(reported, raw, status))


def old_script():
    """Inference script as deployed before the change (25a6dc9), for equivalence checks."""
    try:
        text = subprocess.run(['git', 'show', '25a6dc9:12_live_forecast_and_predict.py'], cwd=ROOT,
                              capture_output=True, text=True, check=True).stdout
    except Exception:
        return None
    path = Path(tempfile.mkdtemp(prefix='old12-')) / '12_live_forecast_and_predict.py'
    path.write_text(text, encoding='utf-8')
    return path


@needs_model
class InferenceScript(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.old = old_script()

    def run_new(self, capture=None, **overrides):
        return harness.run_inference(harness.synthetic_payload(**overrides), INPUT_HOUR, capture=capture)

    def test_negative_cape_is_zero_in_the_model_input_and_recorded(self):
        for current, previous in ((-10.0, -30.0), (-50.0, -10.0), (-30.0, 0.0)):
            with self.subTest(current=current, previous=previous):
                seen = []
                row, error, _ = self.run_new(capture=seen, cape=[0.0, previous, current, 0.0])
                self.assertIsNone(error)
                frame = seen[0]
                self.assertEqual((frame['cape'].iloc[0], frame['previous_cape'].iloc[0]), (0.0, 0.0))
                self.assertEqual((row['cape'], row['cape_raw'], row['previous_cape'], row['previous_cape_raw']),
                                 (0.0, current, 0.0, previous))
                self.assertEqual(row['cape_normalisation'], 'normalised')
                self.assertEqual(row['previous_cape_normalisation'], 'unchanged' if previous == 0 else 'normalised')

    def test_cape_below_tolerance_is_not_repaired(self):
        seen = []
        row, error, _ = self.run_new(capture=seen, cape=[0.0, -60.0, -120.0, 0.0])
        self.assertIsNone(error)  # as before: the worker, not inference, rejects it
        self.assertEqual((seen[0]['cape'].iloc[0], seen[0]['previous_cape'].iloc[0]), (-120.0, -60.0))
        self.assertEqual((row['cape_normalisation'], row['previous_cape_normalisation']), ('invalid', 'invalid'))

    def test_missing_current_cape_still_stops_inference(self):
        row, error, _ = self.run_new(cape=[0.0, 0.0, None, 0.0])
        self.assertIsNone(row)
        self.assertIn('unavailable', str(error))

    def test_nonnumeric_cape_still_stops_inference(self):
        row, error, _ = self.run_new(cape=[0.0, 0.0, 'n/a', 0.0])
        self.assertIsNone(row); self.assertIsNotNone(error)

    def test_nonnegative_cape_unchanged_from_deployed_script(self):
        if self.old is None:
            self.skipTest('git history unavailable')
        payloads = [dict(cape=0.0), dict(cape=[0.0, 40.0, 10.0, 0.0]),
                    dict(cape=[300.0, 900.0, 2150.0, 1500.0], precipitation=[0.0, 2.0, 6.5, 9.0], showers=[0.0, 1.5, 5.0, 8.0],
                         dew_point_2m=15.5, temperature_2m=22.0, wind_gusts_10m=[8.0, 12.0, 17.0, 20.0], cloud_cover=95.0,
                         pressure_msl=1008.0, surface_pressure=850.0)]
        for overrides in payloads:
            with self.subTest(overrides=overrides):
                old_seen, new_seen = [], []
                old_row, old_error, _ = harness.run_inference(harness.synthetic_payload(**overrides), INPUT_HOUR, self.old, old_seen)
                new_row, new_error, _ = harness.run_inference(harness.synthetic_payload(**overrides), INPUT_HOUR, capture=new_seen)
                self.assertIsNone(old_error); self.assertIsNone(new_error)
                pd.testing.assert_frame_equal(old_seen[0], new_seen[0])
                self.assertEqual(old_row['storm_probability'], new_row['storm_probability'])
                for key in set(old_row) - {'forecast_retrieved_at', 'prediction_generated_at'}:
                    self.assertEqual(str(old_row[key]), str(new_row[key]), key)
                self.assertEqual(new_row['cape_normalisation'], 'unchanged')

    def test_normalised_run_equals_deployed_script_given_zero_cape(self):
        if self.old is None:
            self.skipTest('git history unavailable')
        old_seen, new_seen = [], []
        harness.run_inference(harness.synthetic_payload(cape=[0.0, 0.0, 0.0, 0.0]), INPUT_HOUR, self.old, old_seen)
        harness.run_inference(harness.synthetic_payload(cape=[0.0, -20.0, -10.0, 0.0]), INPUT_HOUR, capture=new_seen)
        pd.testing.assert_frame_equal(old_seen[0], new_seen[0])


def prediction_row(now, **changes):
    row = {'forecast_source': 'Open-Meteo ECMWF', 'forecast_retrieved_at': now.isoformat(),
           'forecast_input_time': now.floor('h').isoformat(),
           'prediction_for': (now.floor('h') + pd.Timedelta(hours=1)).isoformat(), 'storm_probability': .10,
           'decision_threshold': .35, 'temperature_c': 20, 'dewpoint_c': 15, 'pressure_msl_hpa': 1012,
           'precipitation_mm': 1, 'cape': 0.0, 'wind_gust_ms': 10, 'latitude': -30.30, 'longitude': 28.80,
           'cape_raw': -10.0, 'cape_normalisation': 'normalised',
           'previous_cape': 0.0, 'previous_cape_raw': 0.0, 'previous_cape_normalisation': 'unchanged'}
    row.update(changes)
    return row


class WorkerValidation(unittest.TestCase):
    def setUp(self):
        self.worker = load_worker()
        self.worker.RECORD.clear()
        self.now = pd.Timestamp.now(tz='UTC')

    def check(self, **changes):
        data = pd.DataFrame([prediction_row(self.now, **changes)])
        return self.worker.validate_prediction(data, self.now - pd.Timedelta(seconds=1), self.now)

    def assert_fails(self, detail, **changes):
        with self.assertRaises(self.worker.WorkerError) as caught:
            self.check(**changes)
        self.assertEqual((caught.exception.category, caught.exception.detail), ('invalid_forecast_data', detail))

    def test_consistent_normalisation_passes_and_is_recorded(self):
        for raw in (-10.0, -30.0, -50.0):
            with self.subTest(raw=raw):
                self.worker.RECORD.clear()
                self.check(cape_raw=raw)
                rec = self.worker.RECORD
                self.assertEqual((rec['cape_normalisation'], rec['cape_original_j_kg']), ('normalised', raw))
                self.assertEqual((rec['previous_cape_normalisation'], rec['previous_cape_original_j_kg']), ('unchanged', 0.0))

    def test_nonnegative_cape_passes_unchanged(self):
        self.check(cape=0.0, cape_raw=0.0, cape_normalisation='unchanged')
        self.check(cape=1830.0, cape_raw=1830.0, cape_normalisation='unchanged')
        self.assertEqual(self.worker.RECORD['cape_normalisation'], 'unchanged')

    def test_below_tolerance_is_invalid(self):
        self.assert_fails('physical_values_invalid', cape=-60.0, cape_raw=-60.0, cape_normalisation='invalid')
        self.assert_fails('physical_values_invalid', previous_cape=-75.0, previous_cape_raw=-75.0, previous_cape_normalisation='invalid')

    def test_missing_nan_and_infinite_raw_values_are_invalid(self):
        for raw in (None, float('nan'), float('inf'), float('-inf'), 'abc'):
            with self.subTest(raw=raw):
                self.worker.RECORD.clear()
                self.assert_fails('physical_values_invalid', previous_cape=float('nan'), previous_cape_raw=raw,
                                  previous_cape_normalisation='invalid')

    def test_inconsistent_reports_fail_closed(self):
        for changes in (dict(cape_normalisation='unchanged'),                            # raw -10 claimed unchanged
                        dict(cape=-10.0),                                                # normalised but not zero
                        dict(cape_raw=-60.0),                                            # beyond tolerance, claimed normalised
                        dict(cape=5.0, cape_raw=5.0),                                    # non-negative, claimed normalised
                        dict(cape_normalisation='repaired'),                             # unknown status
                        dict(previous_cape_normalisation=None),                          # partial report
                        dict(previous_cape=3.0)):                                        # previous value altered
            with self.subTest(changes=changes):
                self.worker.RECORD.clear()
                self.assert_fails('cape_normalisation_inconsistent', **changes)

    def test_prediction_files_without_report_keep_previous_rules(self):
        data = pd.DataFrame([{k: v for k, v in prediction_row(self.now).items()
                              if k not in ('cape_raw', 'cape_normalisation', 'previous_cape', 'previous_cape_raw',
                                           'previous_cape_normalisation')}])
        self.worker.validate_prediction(data.assign(cape=12.0), self.now - pd.Timedelta(seconds=1), self.now)
        self.assertEqual(self.worker.RECORD['cape_normalisation'], 'not_reported')
        with self.assertRaises(self.worker.WorkerError) as caught:
            self.worker.validate_prediction(data.assign(cape=-10.0), self.now - pd.Timedelta(seconds=1), self.now)
        self.assertEqual(caught.exception.detail, 'physical_values_invalid')


class WarningPathIsolation(LedgerHarness):
    """End-to-end live worker runs: SMS and ledger only for consistent, valid, above-threshold rows."""

    def use_row(self, **changes):
        self.row = prediction_row(self.now, **changes)

    def test_above_threshold_with_normalised_cape_sends_once_and_records(self):
        self.use_row(cape_raw=-10.0)
        r = self.live(probability=.62)
        self.assertEqual((r['code'], self.send.call_count, len(self.ledger.issues)), (0, 1, 1))
        rec = r['record']
        self.assertEqual((rec['warning_decision'], rec['sms_submission']), ('warning_eligible', 'sent'))
        self.assertEqual((rec['cape_normalisation'], rec['cape_original_j_kg']), ('normalised', -10.0))
        self.assertEqual(self.send.call_args.kwargs['cape'], 0.0)
        self.assertAlmostEqual(self.send.call_args.kwargs['storm_probability'], .62)
        self.assertEqual(self.send.call_args.kwargs['threshold'], .35)
        again = self.live(probability=.62)
        self.assertEqual((again['code'], self.send.call_count), (0, 1))

    def test_below_threshold_with_normalised_cape_touches_nothing(self):
        self.use_row(cape_raw=-30.0)
        r = self.live(probability=.20)
        self.assertEqual((r['code'], self.send.call_count, self.ledger.calls), (0, 0, []))
        self.assertEqual(r['record']['warning_decision'], 'below_threshold')

    def test_invalid_or_inconsistent_cape_never_reaches_sms_or_ledger(self):
        for changes in (dict(cape=-60.0, cape_raw=-60.0, cape_normalisation='invalid'),
                        dict(previous_cape=float('nan'), previous_cape_raw=float('nan'), previous_cape_normalisation='invalid'),
                        dict(cape_normalisation='unchanged'),
                        dict(cape=-10.0, cape_raw=-10.0, cape_normalisation='unchanged')):
            with self.subTest(changes=changes):
                self.ledger.calls.clear(); self.send.reset_mock()
                self.use_row(**changes)
                r = self.live(probability=.95)
                self.assertEqual((r['code'], self.send.call_count, self.ledger.calls), (1, 0, []))
                self.assertEqual(r['record']['error_category'], 'invalid_forecast_data')

    def test_forecast_retrieval_failure_is_unchanged(self):
        failure = subprocess.CalledProcessError(1, ['python'], output=('All live-compatible model files found.\n'
                                                'Random Forest loaded successfully.\nHTTP status: 503\n'
                                                'Live forecast request failed.\n'), stderr='')
        self.use_row()
        worker = load_worker()
        with patch.object(worker, 'github', self.ledger.bind(worker)):
            r = self.run_worker(probability=.95, worker=worker, subprocess_effect=failure)
        self.assertEqual((r['code'], self.send.call_count, self.ledger.calls), (1, 0, []))
        rec = r['record']
        self.assertEqual(rec['error_category'], 'forecast_retrieval_failure')
        self.assertEqual((rec['cape_normalisation'], rec['previous_cape_normalisation']), ('not_attempted', 'not_attempted'))


if __name__ == '__main__':
    unittest.main()
