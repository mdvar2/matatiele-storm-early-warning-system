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


def contrast(a, b):
    def luminance(hex_colour):
        rgb = [int(hex_colour[i:i + 2], 16) / 255 for i in (1, 3, 5)]
        lin = [c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4 for c in rgb]
        return 0.2126 * lin[0] + 0.7152 * lin[1] + 0.0722 * lin[2]
    high, low = sorted((luminance(a), luminance(b)), reverse=True)
    return (high + 0.05) / (low + 0.05)


class FinalRefinements(DashboardHarness):
    def test_emergency_contacts_are_on_the_safety_page_with_a_homepage_shortcut(self):
        import emergency_contacts
        self.write_prediction(.05)
        at = self.app().run()
        self.assertNotIn('class="contacts-card', self.html(at))
        next(b for b in at.button if b.key == 'home_contacts').click().run()
        self.assertEqual(at.session_state['dashboard_page'], '🛟 Safety Advice')
        page = self.html(at)
        self.assertLess(page.index('advice-grid'), page.index('id="emergency-contacts"'))  # after the safety guidance
        for number in ('10111', '10177', '112'):
            self.assertIn(f'href="tel:{number}"', page)
        self.assertIn(emergency_contacts.NOTE, page)
        self.assertEqual(len(at.get('iframe')), 1)  # the scroll-to-contacts helper ran once
        self.assertNotIn('scroll_to_contacts', at.session_state)
        self.go(at, 'Dashboard'); self.go(at, 'Safety Advice')
        self.assertEqual(len(at.get('iframe')), 0)  # opening Safety normally does not jump down

    def test_low_data_view_lists_emergency_numbers_as_plain_text(self):
        self.write_prediction(.05)
        text = ' '.join(m.value for m in self.app(view='text').run().markdown)
        for line in ('10111: Police (SAPS)', '10177: Ambulance and fire', '112: Any emergency from a cellphone',
                     'Calls need mobile network coverage'):
            self.assertIn(line, text)

    def test_sms_registration_stays_disabled_and_details_are_on_the_alerts_page(self):
        self.write_prediction(.05)
        at = self.go(self.app().run(), 'Alerts')
        next(g for g in at.button_group if g.key == 'alerts_view').set_value(rv_alerts().VIEWS[1]).run()
        page = self.html(at)
        for part in ('SMS service status', 'Public registration:</b> Not yet available.', 'SMS is not active on this deployment',
                     'not proof of delivery', 'POPIA'):
            self.assertIn(part, page)
        self.assertIn('SMS registration is not open yet', ' '.join(i.value for i in at.info))
        self.assertFalse([t for t in at.text_input if 'phone' in t.label.lower() or 'number' in t.label.lower()])

    def test_about_card_names_the_threshold_not_a_warning_level(self):
        self.write_prediction(.05)
        page = self.html(self.go(self.app().run(), 'About'))
        self.assertIn('Warning threshold', page)
        self.assertIn('Model-risk score required to trigger a warning decision.', page)
        self.assertNotIn('Warning level', page)
        self.assertNotIn('Next-hour estimate', page)

    def test_threshold_and_model_score_are_labelled_apart_on_home(self):
        self.write_prediction(.27)
        home = self.html(self.app().run())
        self.assertIn('Model estimate: 27% chance of a storm', home)
        self.assertIn('Warning threshold: 35%', home)
        self.assertIn('Below the 35% warning threshold: no warning.', home)


def rv_alerts():
    import resident_alerts
    return resident_alerts


class CommunicationStatus(unittest.TestCase):
    def status(self, settings, events_error=None):
        import resident_alerts
        script = getattr(self, 'script', ROOT / '26_sms_simulation_demo.py')  # the module may be cached from a harness copy
        with patch.object(resident_alerts, 'SIMULATION_SCRIPT', script):
            return {label: (state, tone) for label, state, tone in resident_alerts.communication_status(settings.get, events_error)}

    def test_states_follow_configuration(self):
        self.assertEqual(self.status({}), {'Dashboard alerts': ('Available', 'ok'), 'SMS simulation': ('Available', 'ok'),
                                           'Public SMS delivery': ('Disabled', 'off')})
        self.assertEqual(self.status({'SMS_DELIVERY_MODE': 'outbox'})['SMS simulation'], ('Active on this deployment', 'ok'))
        self.assertEqual(self.status({'SMS_DELIVERY_MODE': 'twilio'})['Public SMS delivery'], ('Controlled test only', 'warn'))
        # outbox is refused against the real store, so it falls back to disabled
        self.assertEqual(self.status({'SMS_DELIVERY_MODE': 'outbox', 'SUBSCRIBER_STORE': 'github'})['SMS simulation'], ('Available', 'ok'))
        self.assertEqual(self.status({}, 'unreachable')['Dashboard alerts'], ('Warning record unreachable', 'warn'))

    def test_missing_simulation_is_reported(self):
        self.script = Path('does-not-exist.py')
        self.assertEqual(self.status({})['SMS simulation'], ('Unavailable', 'off'))


class DisclaimerAndEvidence(unittest.TestCase):
    def test_disclaimer_link_is_readable_in_both_themes(self):
        import dashboard_theme
        css = dashboard_theme.CSS
        self.assertIn('.research-notice a {color:#6b2f00!important', css)
        self.assertGreaterEqual(contrast('#6b2f00', '#fff5dc'), 7)
        self.assertIn('.research-notice a {color:#ffe08a!important}', css)
        self.assertGreaterEqual(contrast('#ffe08a', '#3d3216'), 7)
        self.assertIn('.research-notice a:focus-visible', css)

    def test_evidence_is_reproduced_from_committed_inputs(self):
        for path in ('docs/evidence/held_out_test_set.csv.gz', 'evaluation_reports/ml_evaluation_2026-10-29/test_metrics.csv'):
            ignored = subprocess.run(['git', 'check-ignore', '-q', path], cwd=ROOT).returncode == 0
            self.assertFalse(ignored, f'{path} would not be committed')
        run = subprocess.run([sys.executable, str(ROOT / '25_build_model_evidence.py'), '--check'], cwd=ROOT,
                             capture_output=True, text=True, timeout=300)
        self.assertEqual(run.returncode, 0, run.stdout + run.stderr)
        self.assertIn('CHECK PASSED', run.stdout)
