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
        self.assertIn('<img class="risk-gauge-img" src="data:image/svg+xml;base64,', page)  # inline SVG would be removed by the sanitiser
        self.assertIn('alt="Model risk score 5%, warning threshold 35%"', page)

    def test_connectivity_failure_then_recovery(self):
        # 1. Normal: fresh forecast, estimate above the threshold.
        self.write_prediction(.41)
        page = self.html(self.app().run())
        self.assertIn('THRESHOLD REACHED', page)  # crossing the threshold is not reported as a warning record
        self.assertNotIn('WARNING TRIGGERED', page)
        self.assertIn('Live forecast data', page)
        # 2. The forecast service cannot be reached: the last known estimate is shown, flagged, and makes no decision.
        self.write_prediction(.41, fresh=False)
        at = self.app(inference_ok=False).run()
        page = self.html(at)
        self.assertIn('Outdated data', page)
        self.assertIn('Last risk score: 41% (out of date)', page)
        self.assertIn('NO DECISION', page)
        self.assertIn('warnings are never issued from out-of-date data', page)
        self.assertNotIn('THRESHOLD REACHED', page)
        text = ' '.join(m.value for m in self.app(inference_ok=False, view='text').run().markdown)
        self.assertIn('OUT OF DATE: last known information from', text)
        # 3. Connectivity returns: current information and a normal decision again.
        self.write_prediction(.05)
        page = self.html(self.app().run())
        self.assertIn('NO WARNING TRIGGERED', page)
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
        self.assertIn('<div class="risk-value">27%</div>', home)
        self.assertIn('Model risk score — not a calibrated probability', home)
        self.assertIn('Warning threshold: 35%', home)
        self.assertIn('NO WARNING TRIGGERED', home)


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


class VisualHomepage(unittest.TestCase):
    def status(self, probability, stale=False, simulated=False):
        from datetime import datetime
        from zoneinfo import ZoneInfo
        t = datetime(2026, 10, 30, 12, tzinfo=ZoneInfo('Africa/Johannesburg'))
        return rv.resident_status(probability, t, t, t, stale, simulated)

    def test_warning_decision_states(self):
        cases = [((.10, {'state': 'none'}), 'NO WARNING TRIGGERED', 'green'),
                 ((.10, {'state': 'unknown'}), 'NO WARNING TRIGGERED', 'green'),
                 ((.50, {'state': 'none'}), 'THRESHOLD REACHED', 'amber'),     # crossing alone is not a warning record
                 ((.50, {'state': 'unknown'}), 'THRESHOLD REACHED', 'amber'),
                 ((.50, {'state': 'dev'}), 'THRESHOLD REACHED', 'amber'),      # a development test is not a genuine warning
                 ((.50, {'state': 'genuine', 'issued': '13:05'}), 'WARNING TRIGGERED', 'red'),
                 ((None, {'state': 'none'}), 'NO DECISION', 'gray')]
        for (probability, record), title, tone in cases:
            with self.subTest(probability=probability, record=record):
                self.assertEqual(rv.warning_state(self.status(probability), record)[:2], (title, tone))
        self.assertEqual(rv.warning_state(self.status(.50, stale=True), {'state': 'none'})[0], 'NO DECISION')
        self.assertEqual(rv.warning_state(self.status(.05, simulated=True), {'state': 'none'})[0], 'SIMULATED WARNING')
        self.assertIn('13:05', rv.warning_state(self.status(.50), {'state': 'genuine', 'issued': '13:05'})[3])
        self.assertIn('could not be checked', rv.warning_state(self.status(.50), {'state': 'unknown'})[3])

    def test_gauge_draws_the_genuine_score_and_the_threshold_marker(self):
        import base64
        import math
        import re
        html = rv.gauge_svg(.27, 'amber')
        svg = base64.b64decode(re.search(r'base64,([^"]+)"', html).group(1)).decode()
        self.assertIn('stroke-dasharray="27.0 1000"', svg)  # filled to exactly the model score
        zero = base64.b64decode(re.search(r'base64,([^"]+)"', rv.gauge_svg(0, 'green')).group(1)).decode()
        self.assertEqual(zero.count('<path'), 1)  # a zero score draws only the empty track
        self.assertIn('>35%</text>', svg)
        angle = math.pi * (1 - .35)
        x1 = 110 + 71 * math.cos(angle)
        self.assertIn(f'x1="{x1:.1f}"', svg)  # the marker sits at 35% of the arc
        self.assertIn('alt="Model risk score 27%, warning threshold 35%"', html)
        self.assertEqual([rv.score_text(v) for v in (0, .003, .006, .27, 1, None, 1.5)], ['0%', '<1%', '1%', '27%', '100%', 'n/a', 'n/a'])

    def test_wording_is_a_score_not_a_chance(self):
        status = self.status(.27)
        page = rv.summary_html(status, .27, {'temperature': '18 °C', 'rain': '0.0 mm', 'wind': '1 m/s', 'gust': '3 m/s',
                                             'source': 'ECMWF forecast · 11:00 SAST', 'icon': ''}, {'state': 'none'})
        self.assertIn('Model-estimated storm risk', page)  # shown in capitals by the card-title style
        self.assertIn('Model risk score — not a calibrated probability', page)
        self.assertNotIn('chance of a storm', page)
        self.assertIn('Not a guarantee', page)

    def test_mobile_layout_puts_the_risk_score_and_decision_first(self):
        import dashboard_theme
        css = dashboard_theme.CSS
        self.assertIn('grid-template-areas:"weather risk period decision"', css)  # desktop: one row of four cards
        self.assertIn('grid-template-areas:"risk" "decision" "period" "weather"', css)  # phone: risk score and decision first


class PredictionLog(unittest.TestCase):
    def test_log_shows_only_saved_rows_and_never_invents_a_warning(self):
        rows = [('31 Oct 10:00–11:00', '10:00 SAST', '6%', 'No warning', 'Hourly worker'),
                ('31 Oct 09:00–10:00', '09:00 SAST', '41%', 'Threshold reached', 'Hourly worker'),
                ('31 Oct 08:00–09:00', '08:00 SAST', '52%', 'Warning', 'Dashboard')]
        page = rv.prediction_log_html(rows)
        self.assertEqual(page.count('<tr><td>'), 3)
        self.assertIn('log-decision tone-amber">Threshold reached', page)
        self.assertIn('log-decision tone-red">Warning', page)
        self.assertIn('not a calibrated probability', page)
        self.assertIn('No saved predictions yet.', rv.prediction_log_html([]))


class HomeDashboardData(DashboardHarness):
    def test_home_log_and_variables_come_from_saved_records(self):
        import pandas as pd
        self.write_prediction(.27)
        at = self.app().run()
        page = self.html(at)
        history = pd.read_csv(self.model / 'prediction_history.csv')
        self.assertEqual(history['storm_probability'].tolist(), [.27])
        self.assertEqual(page.count('class="log-decision'), 1)  # one saved run, one row
        self.assertIn('<b>27%</b>', page)
        self.assertIn('No warning</span>', page)
        self.assertIn('Key weather variables', page)
        self.assertIn('the inputs behind the current risk score', page)
        for label in ('Rainfall', 'Wind speed', 'Temperature', 'Dew point', 'CAPE (storm energy)', 'Pressure'):
            self.assertIn(f'<small>{label}</small>', page)
        self.assertIn('Prediction period', page)
        self.assertIn('Fresh data', page)


class DurablePredictionLog(unittest.TestCase):
    """The Home log and Historical Data read the worker's public [RUN-LOG] records (no network in these tests)."""

    def record(self, target, probability, validation='passed', finished='2026-10-31T10:05:00+00:00'):
        return {'record_type': 'worker_run', 'prediction_validation': validation, 'storm_probability': probability,
                'prediction_target_utc': target, 'forecast_input_utc': target.replace('T11', 'T10'), 'finished_utc': finished}

    def comment(self, record):
        return {'body': 'Run record (sanitised; monitoring only).\n\n```json\n' + json.dumps(record) + '\n```'}

    def test_parse_and_filter_records(self):
        import prediction_log as pl
        self.assertIsNone(pl.parse_comment('no record here'))
        self.assertIsNone(pl.parse_comment('```json\n{"record_type": "other"}\n```'))
        records = [self.record('2026-10-31T11:00:00+00:00', .06), self.record('2026-10-31T11:00:00+00:00', .07, finished='2026-10-31T10:40:00+00:00'),
                   self.record('2026-10-31T12:00:00+00:00', None, validation='not_applicable'),  # connectivity test: no score
                   self.record('2026-10-31T13:00:00+00:00', 1.4)]                                # invalid: never shown
        frame = pl.worker_frame([pl.parse_comment(self.comment(r)['body']) for r in records])
        self.assertEqual(frame['storm_probability'].tolist(), [.07])  # one row per hour, the latest record
        self.assertEqual(frame['source'].tolist(), [pl.WORKER])

    def test_fetch_reads_only_run_log_issues_and_recent_comments(self):
        import prediction_log as pl
        from datetime import datetime, timezone
        calls = []

        class Response:
            def __init__(self, data): self.data = data
            def raise_for_status(self): pass
            def json(self): return self.data

        class Session:
            def get(inner, url, params=None, **kwargs):
                calls.append((url, params))
                if url.endswith('/issues'):
                    return Response([{'number': 7, 'title': '[RUN-LOG] 2026-10'}, {'number': 3, 'title': '[SMS-LEDGER] REAL-SHORT-V1-x'},
                                     {'number': 1, 'title': '[RUN-LOG] 2025-01'}])
                return Response([self.comment(self.record('2026-10-31T11:00:00+00:00', .06))])

        records = pl.fetch_records('owner/repo', Session(), now=datetime(2026, 10, 31, 12, tzinfo=timezone.utc))
        self.assertEqual(len(records), 1)
        comment_calls = [c for c in calls if '/comments' in c[0]]
        self.assertEqual([c[0].rsplit('/issues/', 1)[1] for c in comment_calls], ['7/comments'])  # only this month's run log
        self.assertTrue(comment_calls[0][1]['since'].startswith('2026-10-23'))  # recent records only

    def test_worker_records_win_and_dashboard_runs_fill_other_hours(self):
        import pandas as pd
        import prediction_log as pl
        worker = pl.worker_frame([self.record('2026-10-31T11:00:00+00:00', .06)])
        local = pd.DataFrame({'prediction_for': ['2026-10-31 11:00:00+00:00', '2026-10-31 12:00:00+00:00'], 'storm_probability': [.5, .02],
                              'forecast_input_time': ['2026-10-31 10:00:00+00:00', '2026-10-31 11:00:00+00:00']})
        runs = pl.combine(worker, local)
        self.assertEqual(list(zip(runs['storm_probability'], runs['source'])), [(.06, pl.WORKER), (.02, pl.DASHBOARD)])
        self.assertTrue(pl.combine(pl.worker_frame([]), pd.DataFrame()).empty)


class RunLogOnHome(DashboardHarness):
    def test_unreachable_run_log_falls_back_to_saved_runs_and_says_so(self):
        self.write_prediction(.27)
        page = self.html(self.app().run())  # the harness blocks the network, so GitHub cannot be reached
        self.assertIn('<td>Dashboard</td>', page)
        self.assertIn('(unreachable just now)', page)
        self.assertIn('Recorded by', page)


class PublisherReaderRoundTrip(unittest.TestCase):
    def test_reader_parses_what_the_publisher_posts(self):
        import importlib.util
        import prediction_log as pl
        import run_record
        spec = importlib.util.spec_from_file_location('publisher', ROOT / '19_publish_run_record.py')
        publisher = importlib.util.module_from_spec(spec); spec.loader.exec_module(publisher)
        record = run_record.new_record() if hasattr(run_record, 'new_record') else {'schema_version': run_record.SCHEMA_VERSION, 'record_type': 'worker_run'}
        record.update({'prediction_validation': 'passed', 'storm_probability': 0.0533, 'prediction_target_utc': '2026-10-31T11:00:00+00:00',
                       'forecast_input_utc': '2026-10-31T10:00:00+00:00', 'finished_utc': '2026-10-31T10:12:30+00:00', 'started_utc': '2026-10-31T10:12:00+00:00'})
        posted = []

        def request(method, url, token, payload=None, timeout=20):
            if method == 'GET':
                return [{'number': 9, 'title': '[RUN-LOG] 2026-10'}]
            posted.append(payload['body'])
            return {}
        self.assertTrue(publisher.publish(record, {'GITHUB_REPOSITORY': 'owner/repo', 'GH_TOKEN': 'x'}, request))
        frame = pl.worker_frame([pl.parse_comment(posted[0])])
        self.assertEqual(frame['storm_probability'].tolist(), [0.0533])
