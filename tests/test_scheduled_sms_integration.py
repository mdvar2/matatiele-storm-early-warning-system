"""Historical replay only: real SMS decision code, mocked provider and GitHub.

Historical ERA5 evaluation is deliberately NOT passed off as current ECMWF.
Replay bypasses the worker's fresh-forecast gate; a separate test verifies that
the production gate rejects this historical input. No network or SMS is used.
"""
import contextlib
import io
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock, patch

import joblib
import pandas as pd
import sms_alert
from test_scheduled_sms_worker import load_worker

ROOT = Path(__file__).resolve().parents[1]
HISTORY = ROOT / 'outputs/model_live/live_model_test_predictions.csv'


@unittest.skipUnless(HISTORY.is_file(), 'Genuine historical evaluation file unavailable')
class HistoricalWorkerIntegrationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        directory = HISTORY.parent
        frame = pd.read_csv(HISTORY)
        frame = frame[(frame.latitude == -30.25) & (frame.longitude == 28.75)]
        row = frame[frame.live_model_probability.between(.4066666666, .4066666668)].iloc[0]
        features = (directory / 'live_model_features.txt').read_text().splitlines()
        model = joblib.load(directory / 'random_forest_live_model.pkl')
        cls.probability = float(model.predict_proba(pd.DataFrame([row[features].to_dict()], columns=features))[0][1])
        if abs(cls.probability - float(row.live_model_probability)) > 1e-12:
            raise AssertionError('Saved historical probability does not match the trained model')
        cls.target = pd.to_datetime(row.valid_time, utc=True) + pd.Timedelta(hours=1)
        cls.row = pd.Series({'forecast_source': 'Historical ERA5 evaluation (NOT current forecast)',
            'forecast_input_time': pd.to_datetime(row.valid_time, utc=True).isoformat(),
            'forecast_retrieved_at': pd.to_datetime(row.valid_time, utc=True).isoformat(),
            'prediction_for': cls.target.isoformat(), 'storm_probability': cls.probability,
            'decision_threshold': .35, 'temperature_c': float(row.t2m) - 273.15,
            'dewpoint_c': float(row.d2m) - 273.15, 'pressure_msl_hpa': float(row.msl)/100,
            'precipitation_mm': float(row.tp)*1000, 'cape': float(row.cape),
            'wind_gust_ms': float(row.i10fg), 'latitude': float(row.latitude),
            'longitude': float(row.longitude)})

    def setUp(self):
        self.environment = patch.dict(os.environ, {'ENABLE_REAL_SMS': 'true', 'GITHUB_ACTIONS': 'true',
            'GITHUB_REPOSITORY': 'example/research', 'GH_TOKEN': 'dummy-only',
            'TWILIO_ACCOUNT_SID': 'dummy-only', 'TWILIO_AUTH_TOKEN': 'dummy-only',
            'TWILIO_FROM_NUMBER': '+15555550100', 'ALERT_TO_NUMBERS': '+15555550101'}, clear=True)
        self.environment.start()
        self.addCleanup(self.environment.stop)
        self.ledger = []
        self.client = Mock()

    def github(self, method, endpoint, **kwargs):
        if method == 'GET':
            return list(self.ledger)
        if endpoint == 'issues':
            issue = {'number': 1, 'title': kwargs['json']['title'], 'state': 'closed'}
            self.ledger.append(issue)
            return issue
        return {}

    def replay(self, fails=False):
        worker = load_worker()
        # Each replay has a fresh runner filesystem; only the fake GitHub ledger persists.
        with tempfile.TemporaryDirectory(prefix='historical-worker-', dir=ROOT/'outputs') as directory, \
             patch.object(sms_alert, 'SMS_LOG_FILE', Path(directory)/'sms.csv'), \
             patch.object(sms_alert, '_create_twilio_client', return_value=self.client), \
             patch.object(worker, 'github', side_effect=self.github), \
             patch.object(worker.subprocess, 'run'), \
             patch.object(worker.PREDICTION.__class__, 'is_file', return_value=True), \
             patch.object(worker.pd, 'read_csv', return_value=pd.DataFrame([self.row])), \
             patch.object(worker, 'validate_prediction', return_value=(self.row, self.probability, self.target)), \
             contextlib.redirect_stdout(io.StringIO()):
            if fails:
                with self.assertRaises(worker.WorkerError):
                    worker.main(['--live'])
            else:
                worker.main(['--live'])

    def test_historical_4067_submission_and_fresh_runner_duplicate(self):
        self.assertAlmostEqual(self.probability, .4066666666666667)
        self.client.messages.create.return_value = Mock(sid='mock-historical-sid', status='queued')
        self.replay()
        body = self.client.messages.create.call_args.kwargs['body']
        self.assertIn('MATATIELE MODEL ALERT', body)
        self.assertIn('Storm risk 41%', body)
        self.assertIn('SAST', body)
        self.assertIn('Check SAWS', body)
        self.replay()
        self.assertEqual(self.client.messages.create.call_count, 1)
        self.assertEqual(len(self.ledger), 1)

    def test_historical_failures_and_uncertainty_block_fresh_runner_retry(self):
        for response in [Mock(sid='mock-sid', status='failed'), TimeoutError('mock timeout'),
                         Mock(sid='', status='queued'), Mock(sid='mock-sid', status='unknown')]:
            with self.subTest(response=type(response).__name__):
                self.ledger.clear()
                self.client.reset_mock()
                self.client.messages.create.side_effect = response if isinstance(response, Exception) else None
                self.client.messages.create.return_value = response
                self.replay(fails=True)
                self.replay()
                self.assertEqual(self.client.messages.create.call_count, 1)

    def test_partial_recipients_require_review_and_block_fresh_runner(self):
        with patch.dict(os.environ, {'ALERT_TO_NUMBERS': '+15555550101,+15555550102'}):
            self.client.messages.create.side_effect = [Mock(sid='mock-sid', status='queued'), TimeoutError('mock timeout')]
            self.replay(fails=True)
            self.replay()
        self.assertEqual(self.client.messages.create.call_count, 2)
        self.assertEqual(len(self.ledger), 1)

    def test_production_gate_rejects_historical_replay(self):
        worker = load_worker()
        now = pd.Timestamp.now(tz='UTC')
        with self.assertRaises(worker.WorkerError):
            worker.validate_prediction(pd.DataFrame([self.row]), now, now)


if __name__ == '__main__':
    unittest.main()
