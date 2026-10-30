"""Model evidence, the SMS simulation, low-data freshness and the connectivity-failure path (all offline)."""
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import resident_view as rv
import subscriber_alerts
from test_resident_dashboard import ROOT, DashboardHarness

EVIDENCE = json.loads((ROOT / 'docs' / 'model_evidence.json').read_text(encoding='utf-8'))


class ModelEvidence(unittest.TestCase):
    def test_evidence_is_internally_consistent_and_uses_the_deployed_threshold(self):
        self.assertEqual(EVIDENCE['threshold_in_use'], 0.35)
        self.assertEqual((ROOT / 'outputs' / 'model_live' / 'live_selected_threshold.txt').read_text().strip(), '0.35')
        rows = {round(r['threshold'], 2): r for r in EVIDENCE['threshold_comparison']}
        self.assertTrue({0.35, 0.40} <= set(rows))
        for row in rows.values():
            self.assertEqual(row['TP'] + row['FP'] + row['FN'] + row['TN'], EVIDENCE['held_out']['rows'])
            self.assertEqual(row['TP'] + row['FN'], EVIDENCE['held_out']['storm_hours'])
            self.assertEqual(row['warnings'], row['TP'] + row['FP'])
            self.assertAlmostEqual(row['precision'], row['TP'] / (row['TP'] + row['FP']))
            self.assertAlmostEqual(row['recall'], row['TP'] / (row['TP'] + row['FN']))
        self.assertAlmostEqual(sum(g['importance'] for g in EVIDENCE['feature_importance_groups']), 1.0, places=6)
        self.assertIn('optimistic', EVIDENCE['held_out']['note'])
        self.assertIn('proxy', EVIDENCE['labels'])

    def test_importances_match_the_saved_model(self):
        model_file = ROOT / 'outputs' / 'model_live' / 'random_forest_live_model.pkl'
        if not model_file.exists():
            self.skipTest('model file not present')
        import joblib
        model = joblib.load(model_file)
        features = (ROOT / 'outputs' / 'model_live' / 'live_model_features.txt').read_text(encoding='utf-8').split()
        importance = dict(zip(features, model.feature_importances_))
        for top in EVIDENCE['feature_importance_top10']:
            self.assertAlmostEqual(importance[top['feature']], top['importance'])


class RiskAnalysisAndHome(DashboardHarness):
    def test_risk_analysis_shows_genuine_evidence_without_overclaiming(self):
        self.write_prediction(.05)
        at = self.go(self.app().run(), 'Risk Analysis')
        text = self.html(at) + ' '.join(c.value for c in at.caption) + ' '.join(m.value for m in at.markdown)
        for phrase in ('Patterns learned from historical weather data', 'not what causes storms', '35% (in use)', '40%',
                       'Persistence baseline', 'selection bias', 'proxy storm labels', 'The model was not calibrated',
                       'No claim is made that a Random Forest is better', 'No confidence interval is calculated',
                       'validation year'):
            self.assertIn(phrase, text)
        self.assertNotIn('optimal threshold', text.lower())
        self.assertTrue(at.get('vega_lite_chart'))  # the importance chart

    def test_low_data_view_states_decision_and_freshness(self):
        self.write_prediction(.05)
        page = ' '.join(m.value for m in self.app(view='text').run().markdown)
        self.assertIn('**Warning decision:** Below the 35% warning threshold: no warning.', page)
        self.assertIn('**Information status:** Current', page)

    def test_home_gauge_is_an_image_with_its_value_as_text(self):
        self.write_prediction(.05)
        page = self.html(self.app().run())
        self.assertIn('<img class="mini-gauge" src="data:image/svg+xml;base64,', page)  # inline SVG would be removed by the sanitiser
        self.assertIn('alt="Model-estimated storm risk 5%, warning threshold 35%"', page)

    def test_connectivity_failure_then_recovery(self):
        # 1. Normal: fresh forecast, estimate above the threshold.
        self.write_prediction(.41)
        page = self.html(self.app().run())
        self.assertIn('At or above the 35% warning threshold: warning condition met.', page)
        self.assertIn('Live forecast data', page)
        # 2. The forecast service cannot be reached: the last known estimate is shown, flagged, and makes no decision.
        self.write_prediction(.41, fresh=False)
        at = self.app(inference_ok=False).run()
        page = self.html(at)
        self.assertIn('Outdated data', page)
        self.assertIn('Last estimate: 41%', page)
        self.assertIn('No warning decision: the information is out of date', page)
        self.assertNotIn('warning condition met', page)
        text = ' '.join(m.value for m in self.app(inference_ok=False, view='text').run().markdown)
        self.assertIn('OUT OF DATE: last known information from', text)
        # 3. Connectivity returns: current information and a normal decision again.
        self.write_prediction(.05)
        page = self.html(self.app().run())
        self.assertIn('Below the 35% warning threshold: no warning.', page)
        self.assertNotIn('Outdated data', page)


class SmsSimulation(unittest.TestCase):
    def test_simulation_labels_messages_sends_nothing_and_is_idempotent(self):
        out = Path(tempfile.mkdtemp()) / 'steps.json'
        env = {k: v for k, v in os.environ.items() if not k.startswith(('TWILIO_', 'SUBSCRIBER_', 'SMS_', 'ALERT_TO'))}
        run = subprocess.run([sys.executable, str(ROOT / '26_sms_simulation_demo.py'), '--out', str(out)], cwd=ROOT, env=env,
                             capture_output=True, text=True, timeout=120)
        self.assertEqual(run.returncode, 0, run.stderr)
        steps = {s['step']: s for s in json.loads(out.read_text(encoding='utf-8'))}
        sms = steps['Simulated SMS written to the local outbox (not sent)']
        self.assertTrue(sms['body'].startswith(subscriber_alerts.TEST_PREFIX))
        self.assertEqual(sms['delivery_status'], ['outbox'])  # recorded as simulated, never as delivered
        self.assertNotIn('0001', sms['to'][:-2])  # masked number only
        self.assertEqual(steps['Same warning run again']['worker_result']['subscriber_recipients'], 0)
        failure = steps['Provider failure']
        self.assertTrue(failure['warning_still_recorded'])
        self.assertEqual(failure['delivery_status'], 'uncertain')
        self.assertEqual(steps['Summary']['messages_sent_to_a_phone'], 0)

    def test_live_message_wording_is_unchanged(self):
        class RealGateway:
            mode, real = 'twilio', True
        env = {'SUBSCRIBER_ALERTS_ENABLED': 'true'}
        bodies = []
        with patch('subscriptions.gateway_from_config', return_value=RealGateway()), \
                patch('subscriber_store.open_store', return_value=object()), \
                patch.object(subscriber_alerts, 'deliver_warning', side_effect=lambda store, gw, key, body, *a: bodies.append(body) or
                             {'recipients': 0, 'submitted': 0, 'failed': 0, 'uncertain': 0}):
            subscriber_alerts.run_for_worker('2026-10-30T12:00:00+00:00', .5, .35, env)
        self.assertTrue(bodies[0].startswith('MATATIELE MODEL ALERT'))


class DecisionWording(unittest.TestCase):
    def test_decision_and_freshness_for_each_state(self):
        from datetime import datetime
        from zoneinfo import ZoneInfo
        t = datetime(2026, 10, 30, 12, tzinfo=ZoneInfo('Africa/Johannesburg'))
        self.assertIn('warning condition met', rv.resident_status(.5, t, t, t, False)['decision'])
        self.assertIn('no warning', rv.resident_status(.1, t, t, t, False)['decision'])
        stale = rv.resident_status(.5, t, t, t, True)
        self.assertIn('never issued from out-of-date data', stale['decision'])
        self.assertTrue(stale['freshness'].startswith('OUT OF DATE'))
        self.assertIn('no current model estimate', rv.resident_status(None, t, t, t, False)['decision'])
        self.assertIn('on screen only', rv.resident_status(.05, t, t, t, False, simulated=True)['decision'])


if __name__ == '__main__':
    unittest.main()
