"""Resident-facing dashboard: wording, guidance, stale data, simulation isolation and admin access.

Unit tests cover resident_view.py. Integration tests run the real 16_dashboard.py with
Streamlit's AppTest in a temporary copy: inference is replaced by a synthetic prediction
file, the network is refused, Twilio is unconfigured and every send path is guarded.
"""
import ast
import datetime as dt
import hashlib
import math
import os
import re
import shutil
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

import pandas as pd
import requests

import resident_view as rv
import sms_alert
from forecast_timing import model_input_hour

ROOT = Path(__file__).resolve().parents[1]
SAST = 'Africa/Johannesburg'
ADMIN_TEST_PASSWORD = 'test-only-password'
# Deterministic dashboard clock: mid-hour, away from any hour or day boundary.
FIXED_NOW = dt.datetime(2026, 10, 30, 10, 20, tzinfo=dt.timezone(dt.timedelta(hours=2)))


class FrozenDateTime(dt.datetime):
    """datetime whose now() is FIXED_NOW; the dashboard imports it as `datetime` while patched."""

    @classmethod
    def now(cls, tz=None):
        return FIXED_NOW.replace(tzinfo=None) if tz is None else FIXED_NOW.astimezone(tz)


def dashboard_risk():
    """The dashboard's own risk() function, executed in isolation."""
    tree = ast.parse((ROOT / '16_dashboard.py').read_text(encoding='utf-8'))
    node = next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == 'risk')
    namespace = {'math': math}
    exec(compile(ast.Module(body=[node], type_ignores=[]), '<risk>', 'exec'), namespace)
    return namespace['risk']


class RiskClassification(unittest.TestCase):
    def test_bands_and_boundaries(self):
        cases = [(0, 'LOW'), (.0999, 'LOW'), (.10, 'ELEVATED'), (.1999, 'ELEVATED'), (.20, 'MODERATE'),
                 (.3499, 'MODERATE'), (.35, 'WARNING'), (.60, 'WARNING'), (1, 'WARNING'),
                 (float('nan'), 'UNAVAILABLE'), (float('inf'), 'UNAVAILABLE'), (-.01, 'UNAVAILABLE'),
                 (1.01, 'UNAVAILABLE'), (None, 'UNAVAILABLE'), ('x', 'UNAVAILABLE')]
        for probability, expected in cases:
            with self.subTest(probability=probability):
                self.assertEqual(rv.classify(probability), expected)

    def test_matches_dashboard_risk_and_unchanged_threshold(self):
        risk = dashboard_risk()
        for p in (0, .05, .0999, .1, .15, .2, .3, .3499, .35, .5, .6, 1, float('nan'), -1, 2):
            with self.subTest(p=p):
                self.assertEqual(rv.classify(p), risk(p, .35)[0])
        self.assertEqual(rv.THRESHOLD, .35)
        text = (ROOT / '16_dashboard.py').read_text(encoding='utf-8')
        self.assertIn('threshold=.35', text)
        self.assertIn('WARNING_THRESHOLD = .35', (ROOT / '18_scheduled_sms_worker.py').read_text(encoding='utf-8'))


class SafetyGuidance(unittest.TestCase):
    def all_text(self):
        parts = [rv.MODEL_NOTE, rv.OFFICIAL_NOTE, rv.COVERAGE, rv.STALE_EXPLANATION]
        parts += list(rv.HEADLINES.values()) + list(rv.EXPLANATIONS.values())
        parts += list(rv.ACT_NOW.values()) + list(rv.PREPARE.values())
        return ' '.join(parts)

    def test_every_level_covers_the_five_topics(self):
        for level in ('LOW', 'ELEVATED', 'MODERATE', 'WARNING', 'UNAVAILABLE', 'bogus'):
            with self.subTest(level=level):
                advice = rv.guidance(level)
                self.assertEqual([topic for topic, _ in advice['items']],
                                 ['Lightning', 'Flooding', 'Roads', 'Rivers', 'Livestock'])
                self.assertTrue(all(text.strip() for _, text in advice['items']))
                self.assertIn('not an official weather warning', advice['note'])
                self.assertIn('SAWS', advice['note'])

    def test_urgency_matches_level(self):
        self.assertEqual(rv.guidance('WARNING')['action'], 'Act now')
        self.assertEqual(dict(rv.guidance('WARNING')['items']), rv.ACT_NOW)
        self.assertEqual(rv.guidance('MODERATE')['action'], 'Get ready')
        for level in ('LOW', 'ELEVATED', 'MODERATE'):
            self.assertEqual(dict(rv.guidance(level)['items']), rv.PREPARE)
        self.assertEqual(dict(rv.guidance('UNAVAILABLE')['items']), rv.ACT_NOW)
        self.assertIn('lightning', rv.ACT_NOW['Lightning'].lower())
        self.assertIn('flood water', rv.ACT_NOW['Flooding'])
        self.assertIn('Do not cross rivers', rv.ACT_NOW['Rivers'])

    def test_no_invented_contact_numbers_and_no_guarantees(self):
        text = self.all_text()
        self.assertIsNone(re.search(r'\d{3,}', text), 'no phone or emergency numbers may be shown')
        lowered = text.lower()
        for claim in ('no storm will', 'there will be no storm', 'you are safe', 'guaranteed', 'completely safe'):
            self.assertNotIn(claim, lowered)
        # "safe" may appear only in cautionary forms ("do not assume it is safe", "if it is safe").
        for match in re.finditer(r'it is safe', lowered):
            self.assertRegex(lowered[max(0, match.start() - 10):match.start()], r'(assume |if )$')
        self.assertIn('not a guarantee', rv.EXPLANATIONS['LOW'])
        self.assertIn('not been independently validated', rv.MODEL_NOTE)
        self.assertIn('not an official weather warning', rv.MODEL_NOTE)


class ResidentStatus(unittest.TestCase):
    start = pd.Timestamp('2026-10-30T14:00', tz=SAST)
    end = pd.Timestamp('2026-10-30T15:00', tz=SAST)
    updated = pd.Timestamp('2026-10-30T13:12', tz=SAST)

    def status(self, probability, stale=False, simulated=False, start=start, end=end):
        return rv.resident_status(probability, start, end, self.updated, stale, simulated)

    def test_fresh_low_is_an_estimate_not_a_guarantee(self):
        s = self.status(.04)
        self.assertEqual((s['level'], s['guidance_level'], s['tone']), ('LOW', 'LOW', 'green'))
        self.assertIn('model estimate', s['headline'])
        self.assertIn('not a guarantee', s['explanation'])
        self.assertEqual(s['estimate'], 'Model estimate: 4% chance of a storm')
        self.assertEqual(s['period'], '30 Oct 14:00 - 15:00 (SAST)')
        self.assertEqual(s['updated'], '30 Oct 2026 13:12 SAST')
        self.assertIn('Matatiele', s['coverage'])
        self.assertFalse(s['simulated']); self.assertEqual(s['label'], '')

    def test_fresh_warning(self):
        s = self.status(.41)
        self.assertEqual((s['level'], s['guidance_level'], s['tone']), ('WARNING', 'WARNING', 'red'))
        self.assertIn('take precautions now', s['headline'])

    def test_stale_data_is_never_presented_as_current(self):
        for probability in (.04, .41):
            with self.subTest(probability=probability):
                s = self.status(probability, stale=True)
                self.assertEqual(s['headline'], rv.STALE_HEADLINE)
                self.assertEqual((s['guidance_level'], s['tone'], s['stale']), ('UNAVAILABLE', 'gray', True))
                self.assertTrue(s['estimate'].startswith('Last estimate'))
                self.assertIn('Do not rely on it', s['explanation'])

    def test_missing_or_invalid_probability(self):
        for probability in (float('nan'), None, 1.5):
            with self.subTest(probability=probability):
                s = self.status(probability)
                self.assertEqual((s['level'], s['guidance_level'], s['estimate']), ('UNAVAILABLE', 'UNAVAILABLE', 'No model estimate'))
                self.assertIn('Do not assume it is safe', s['explanation'])
        self.assertEqual(self.status(.04, start=None)['period'], 'Forecast period unavailable')

    def test_simulation_is_fixed_labelled_and_ignores_genuine_inputs(self):
        for genuine, stale in ((.02, False), (.02, True), (float('nan'), True)):
            with self.subTest(genuine=genuine, stale=stale):
                s = self.status(genuine, stale=stale, simulated=True)
                self.assertEqual((s['level'], s['guidance_level'], s['simulated']), ('WARNING', 'WARNING', True))
                self.assertEqual(s['estimate'], 'Simulated model output: 60%')
                self.assertEqual(s['label'], rv.SIMULATION_LABEL)
                self.assertIn('NOT A REAL', s['label'])

    def test_html_is_escaped(self):
        s = self.status(.04)
        s['headline'] = '<script>alert(1)</script>'
        self.assertNotIn('<script>', rv.card_html(s))
        self.assertIn('&lt;script&gt;', rv.card_html(s))

    def test_text_only_page_contents(self):
        page = rv.text_only_page(self.status(.04), rv.guidance('LOW'))
        for part in ('Low storm risk', '30 Oct 14:00 - 15:00 (SAST)', '30 Oct 2026 13:12 SAST', 'Safety advice: Be prepared',
                     '**Lightning:**', '**Livestock:**', 'not an official weather warning'):
            self.assertIn(part, page)
        simulated = rv.text_only_page(self.status(.04, simulated=True), rv.guidance('WARNING'))
        self.assertTrue(simulated.startswith(f'**{rv.SIMULATION_LABEL}**'))


class SmsPreviewNeverSends(unittest.TestCase):
    def test_preview_matches_worker_text_and_touches_no_provider(self):
        target = '2026-10-30T15:00:00+02:00'
        with patch.object(sms_alert, '_send_warning', side_effect=AssertionError('send attempted')) as send, \
             patch.object(sms_alert, '_create_twilio_client', side_effect=AssertionError('Twilio used')) as client:
            preview = rv.sms_preview(target)
        send.assert_not_called(); client.assert_not_called()
        self.assertEqual(preview, sms_alert._build_warning_message('Matatiele', target, .60, .35, 0, 0, 0, 0))
        self.assertIn('Storm risk 60%', preview)
        self.assertIn('30 Oct 14:00-15:00 SAST', preview)
        self.assertEqual(rv.sms_preview(''), 'Preview unavailable: no valid forecast period.')

    def test_resident_module_cannot_send(self):
        tree = ast.parse((ROOT / 'resident_view.py').read_text(encoding='utf-8'))
        imported = {(n.module, a.name) for n in ast.walk(tree) if isinstance(n, ast.ImportFrom) for a in n.names}
        self.assertEqual({i for i in imported if i[0] == 'sms_alert'}, {('sms_alert', '_build_warning_message')})
        modules = {a.name for n in ast.walk(tree) if isinstance(n, ast.Import) for a in n.names}
        self.assertFalse(modules & {'requests', 'twilio', 'streamlit', 'subprocess', 'sms_alert'})
        called = {n.func.attr if isinstance(n.func, ast.Attribute) else getattr(n.func, 'id', '')
                  for n in ast.walk(tree) if isinstance(n, ast.Call)}
        self.assertFalse({c for c in called if c.startswith('send') or c in {'open', 'write_text', 'to_csv', 'create'}})


SECTIONS = ('🏠 Dashboard', '🚨 Alerts', '🌦️ Live Forecast', '🗺️ Weather Map', '🛟 Safety Advice', '📈 Risk Analysis',
            '🕒 Historical Data', 'ℹ️ About')  # internal page keys behind the navigation labels
TOP_SECTIONS = ('🏠 Dashboard', '🌦️ Live Forecast', '🗺️ Weather Map', '🛟 Safety Advice')  # top bar; the rest are in the ☰ menu


class DashboardHarness(unittest.TestCase):
    """The real 16_dashboard.py, run hermetically with Streamlit's AppTest. Defines no tests."""

    @classmethod
    def setUpClass(cls):
        from streamlit.testing.v1 import AppTest  # noqa: F401  (skip cleanly if unavailable)
        cls.tmp = Path(tempfile.mkdtemp(prefix='resident-dashboard-'))
        for name in ('16_dashboard.py', 'app_config.py', 'forecast_timing.py', 'sms_alert.py', 'resident_view.py', 'dashboard_theme.py',
                     'resident_pages.py', 'subscriptions.py', 'subscriber_store.py', 'subscriber_alerts.py',
                     'resident_alerts.py', 'official_portal.py', 'emergency_contacts.py', 'warning_events.py', 'officials.py', 'icons.py'):
            shutil.copy(ROOT / name, cls.tmp / name)
        shutil.copytree(ROOT / 'components', cls.tmp / 'components')
        (cls.tmp / '12_live_forecast_and_predict.py').write_text('# placeholder: subprocess.run is patched\n')
        cls.model = cls.tmp / 'outputs' / 'model_live'
        cls.model.mkdir(parents=True)
        (cls.model / 'live_selected_threshold.txt').write_text('0.35\n')

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.tmp, ignore_errors=True)

    def setUp(self):
        import streamlit as st
        st.cache_resource.clear()
        for name in ('dashboard_forecast_prediction.csv', 'prediction_history.csv', 'regional_ecmwf_forecast.csv'):
            (self.model / name).unlink(missing_ok=True)
        env = {k: v for k, v in os.environ.items() if not k.startswith(('TWILIO_', 'ALERT_TO', 'ADMIN_PASSWORD'))}
        env['ADMIN_PASSWORD'] = ADMIN_TEST_PASSWORD
        self.env = patch.dict(os.environ, env, clear=True); self.env.start(); self.addCleanup(self.env.stop)
        # Settings come only from this test environment: never the project's real secrets file.
        import app_config
        env_only = lambda name: os.getenv(name, '').strip()  # noqa: E731
        guards = [patch.object(app_config, 'get_setting', env_only), patch.object(sms_alert, 'get_setting', env_only),
                  patch('requests.get', side_effect=requests.ConnectionError('network disabled in tests')),
                  patch.object(sms_alert, '_send_warning', side_effect=AssertionError('SMS send attempted')),
                  patch.object(sms_alert, '_create_twilio_client', side_effect=AssertionError('Twilio used'))]
        self.mocks = [g.start() for g in guards]
        for g in guards: self.addCleanup(g.stop)

    def write_prediction(self, probability=.05, fresh=True):
        now = pd.Timestamp(FIXED_NOW).tz_convert(SAST)
        start = model_input_hour(now, next_complete=True)
        when = now if fresh else now - pd.Timedelta(hours=3)
        row = {'forecast_source': 'Open-Meteo ECMWF', 'forecast_retrieved_at': when.isoformat(),
               'prediction_generated_at': when.isoformat(), 'forecast_input_time': start.isoformat(),
               'prediction_for': (start + pd.Timedelta(hours=1)).isoformat(), 'storm_probability': probability,
               'decision_threshold': .35, 'temperature_c': 18.0, 'precipitation_mm': 0.0, 'cape': 0.0,
               'wind_gust_ms': 3.0, 'cloud_cover_percent': 10.0, 'pressure_msl_hpa': 1018.0}
        pd.DataFrame([row]).to_csv(self.model / 'dashboard_forecast_prediction.csv', index=False)

    def app(self, inference_ok=True, **query):
        from streamlit.testing.v1 import AppTest
        at = AppTest.from_file(str(self.tmp / '16_dashboard.py'), default_timeout=120)
        for key, value in query.items():
            at.query_params[key] = value
        self.inference = patch('subprocess.run', return_value=Mock(returncode=0 if inference_ok else 1))
        self.inference.start(); self.addCleanup(self.inference.stop)
        clock = patch('datetime.datetime', FrozenDateTime)
        clock.start(); self.addCleanup(clock.stop)
        return at

    @staticmethod
    def html(at):
        return '\n'.join(element.proto.body for element in at.get('html'))

    def button(self, at, label):
        return next(b for b in at.button if b.label == label)

    def go(self, at, section):
        """Navigate with the top navigation bar (sections keep their internal names, e.g. 'Safety Advice')."""
        target = next(o for o in SECTIONS if o.endswith(section))
        if target in TOP_SECTIONS:
            next(g for g in at.button_group if g.key == 'top_nav').set_value(target).run()
        else:  # Alerts and the research sections are in the side (☰) menu
            next(b for b in at.button if b.key == 'menu_' + target.split(' ', 1)[1]).click().run()
        return at

    def digest(self):
        return {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(self.model.glob('*.csv'))}

    def login(self, at):
        next(t for t in at.text_input if t.label == 'Administrator Password').input(ADMIN_TEST_PASSWORD)
        self.button(at, 'Unlock Admin Controls').click().run()
        self.assertTrue(at.session_state['admin_authenticated'])


class DashboardApp(DashboardHarness):
    def test_public_view_is_resident_first_without_admin_controls(self):
        self.write_prediction(.05)
        at = self.app().run()
        self.assertFalse(at.exception)
        page = self.html(at)
        self.assertNotIn('class="kpi', page)  # technical status cards live in About, not on Home
        self.assertIn('Low storm risk (model estimate)', page)
        self.assertIn('not a guarantee', page)
        self.assertIn('Be prepared', page)
        self.assertIn('not been independently validated', self.html(self.go(at, 'Risk Analysis')))  # full caveat: Risk Analysis
        self.assertNotIn('SIMULATION', page)
        self.assertFalse([e for e in at.expander if 'Administrator Access' in e.label])
        self.assertFalse([b for b in at.button if 'Test SMS' in b.label or 'Unlock' in b.label])
        self.assertEqual([t for t in at.toggle if t.key == 'presentation_test_mode'], [])
        self.assertEqual(len(at.code), 0)

    def test_stale_prediction_is_flagged_for_residents(self):
        self.write_prediction(.41, fresh=False)
        at = self.app(inference_ok=False).run()
        page = self.html(at)
        self.assertIn(rv.STALE_HEADLINE, page)
        self.assertIn('Last estimate: 41%', page)
        self.assertNotIn('take precautions now', page)
        self.assertIn('If you see signs of a storm', page)

    def test_admin_login_requires_flag_and_correct_password(self):
        self.write_prediction(.05)
        at = self.app(admin='1').run()
        self.assertTrue([e for e in at.expander if 'Administrator Access' in e.label])
        at.text_input[0].input('wrong-password')
        self.button(at, 'Unlock Admin Controls').click().run()
        self.assertFalse(at.session_state['admin_authenticated'])
        self.assertIn('Incorrect password.', [e.value for e in at.error])
        self.assertEqual([t for t in at.toggle if t.key == 'presentation_test_mode'], [])
        self.login(at)
        self.assertEqual([t.label for t in at.toggle if t.key == 'presentation_test_mode'], ['Warning simulation (on screen only)'])

    def test_simulation_is_on_screen_only_and_reverts(self):
        self.write_prediction(.05)
        at = self.app(admin='1').run()
        self.login(at)
        before = self.digest()
        at.toggle(key='presentation_test_mode').set_value(True).run()
        page = self.html(at)
        self.assertIn(rv.SIMULATION_LABEL, page)
        self.assertIn('Simulated model output: 60%', page)
        self.assertIn('Storm warning (model): take precautions now', page)
        self.assertIn('Act now', page)
        self.assertIn('>5.0%<', self.html(self.go(at, 'Risk Analysis')))  # Risk Analysis keeps the genuine output
        self.go(at, 'Dashboard')
        self.assertEqual(len(at.code), 1)
        self.assertIn('Storm risk 60%', at.code[0].value)
        self.assertFalse([b for b in at.button if 'Test SMS' in b.label])
        self.assertEqual(self.digest(), before)  # no prediction or history record changed
        for guard in self.mocks[3:]:
            guard.assert_not_called()
        at.toggle(key='presentation_test_mode').set_value(False).run()
        page = self.html(at)
        self.assertNotIn(rv.SIMULATION_LABEL, page)
        self.assertIn('Low storm risk (model estimate)', page)
        self.assertEqual(len(at.code), 0)
        self.assertEqual(self.digest(), before)

    def test_dashboard_clock_is_frozen(self):
        self.write_prediction(.05)
        at = self.app().run()
        self.assertIn('30 October 2026 &nbsp; 10:20 SAST', self.html(at))
        self.assertIn('30 Oct 11:00 - 12:00 (SAST)', self.html(at))

    def test_settings_are_test_only(self):
        import app_config
        self.assertEqual(app_config.get_setting('ADMIN_PASSWORD'), ADMIN_TEST_PASSWORD)
        self.assertEqual(sms_alert.get_setting('TWILIO_AUTH_TOKEN'), '')
        self.assertFalse(sms_alert.sms_is_configured())

    def navigate(self, at, label):
        self.go(at, label)

    def test_url_parameters_alone_never_grant_admin_or_simulation(self):
        self.write_prediction(.05)
        for query in ({'admin': '1'}, {'admin': '1', 'admin_authenticated': 'true', 'presentation_test_mode': 'true'},
                      {'view': 'text', 'admin': '1'}, {'admin': 'true'}):
            with self.subTest(query=query):
                at = self.app(**query).run()
                self.assertFalse(at.session_state['admin_authenticated'])
                self.assertEqual([t for t in at.toggle if t.key == 'presentation_test_mode'], [])
                page = self.html(at) + '\n'.join(m.value for m in at.markdown)
                self.assertNotIn(rv.SIMULATION_LABEL, page)
                self.assertFalse([b for b in at.button if 'Test SMS' in b.label])

    def test_text_view_never_shows_admin_controls_or_operations(self):
        self.write_prediction(.05)
        at = self.app(view='text', admin='1').run()
        self.assertFalse([e for e in at.expander if 'Administrator Access' in e.label])
        self.assertFalse([b for b in at.button if 'Unlock' in b.label or 'Test SMS' in b.label])
        text = '\n'.join(m.value for m in at.markdown)
        for operational in ('GitHub', 'Twilio', 'Operational status', 'ACTIONS ONLY'):
            self.assertNotIn(operational, text)
        # A signed-in administrator who opens the text view also gets the public page only.
        signed_in = self.app(admin='1').run()
        self.login(signed_in)
        signed_in.toggle(key='presentation_test_mode').set_value(True).run()
        signed_in.query_params['view'] = 'text'
        signed_in.run()
        self.assertEqual([t for t in signed_in.toggle if t.key == 'presentation_test_mode'], [])
        self.assertFalse([e for e in signed_in.expander if 'Administrator Access' in e.label])
        self.assertNotIn(rv.SIMULATION_LABEL, '\n'.join(m.value for m in signed_in.markdown))

    def test_wrong_password_cannot_enable_simulation(self):
        self.write_prediction(.05)
        at = self.app(admin='1').run()
        for attempt in ('', 'Test-only-password', ADMIN_TEST_PASSWORD + ' ', 'x' * 64):
            with self.subTest(attempt=attempt):
                at.text_input[0].input(attempt)
                self.button(at, 'Unlock Admin Controls').click().run()
                self.assertFalse(at.session_state['admin_authenticated'])
                self.assertEqual([t for t in at.toggle if t.key == 'presentation_test_mode'], [])
        at.session_state['presentation_test_mode'] = True
        at.run()
        self.assertNotIn(rv.SIMULATION_LABEL, self.html(at))

    def test_repeated_wrong_passwords_lock_sign_in_for_every_session(self):
        self.write_prediction(.05)
        at = self.app(admin='1').run()
        for _ in range(10):
            next(t for t in at.text_input if t.label == 'Administrator Password').input('wrong-password')
            self.button(at, 'Unlock Admin Controls').click().run()
        fresh = self.app(admin='1').run()  # a new browser session shares the server-wide limit
        next(t for t in fresh.text_input if t.label == 'Administrator Password').input(ADMIN_TEST_PASSWORD)
        self.button(fresh, 'Unlock Admin Controls').click().run()
        self.assertFalse(fresh.session_state['admin_authenticated'])
        self.assertIn('Too many failed sign-in attempts. Try again in 15 minutes.', [e.value for e in fresh.error])

    def test_operational_information_is_admin_only(self):
        self.write_prediction(.05)
        at = self.app(admin='1').run()
        self.navigate(at, 'Alerts')
        public = self.html(at)
        about = self.html(self.go(at, 'About'))  # how warnings reach people: one diagram, on About
        for step in ('Forecast', 'Random Forest', 'Warning decision', 'Warning record', 'Warning view', 'Acknowledgement', 'SMS to subscribers'):
            self.assertIn(f'<b>{step}</b>', about)
        self.assertIn('Optional · not enabled', about)  # SMS state shown honestly (registration is off in tests)
        self.navigate(at, 'Alerts')
        for operational in ('MANAGED BY GITHUB ACTIONS', 'ACTIONS ONLY'):
            self.assertNotIn(operational, public)
        self.assertNotIn('Operational status (administrators)', '\n'.join(m.value for m in at.markdown))
        self.login(at)
        admin = self.html(at)
        self.assertIn('MANAGED BY GITHUB ACTIONS', admin)
        self.assertIn('Operational status (administrators)', '\n'.join(m.value for m in at.markdown))

    def test_safety_advice_page_is_public(self):
        self.write_prediction(.05)
        at = self.app().run()
        self.navigate(at, 'Safety Advice')
        page = self.html(at)
        self.assertIn('Be prepared', page)  # advice for the current status
        self.assertIn('Act now', page)       # full advice for when a storm is close
        self.assertNotIn('class="kpi', page)

    def test_simulation_cannot_be_enabled_without_admin(self):
        self.write_prediction(.05)
        at = self.app().run()
        at.session_state['presentation_test_mode'] = True
        at.run()
        self.assertNotIn(rv.SIMULATION_LABEL, self.html(at))
        self.assertFalse(at.session_state['presentation_test_mode'])

    def test_text_only_view(self):
        self.write_prediction(.05)
        at = self.app(view='text').run()
        self.assertFalse(at.exception)
        text = '\n'.join(m.value for m in at.markdown)
        for part in ('Low storm risk (model estimate)', 'Forecast period', 'Last update', 'Safety advice: Be prepared', '**Rivers:**'):
            self.assertIn(part, text)
        self.assertEqual(len(at.get('deck_gl_json_chart')), 0)
        self.assertEqual(len(at.get('arrow_vega_lite_chart')), 0)
        self.assertNotIn('class="kpi', self.html(at))

    def test_genuine_prediction_file_is_preserved(self):
        self.write_prediction(.27)
        written = (self.model / 'dashboard_forecast_prediction.csv').read_bytes()
        at = self.app().run()
        self.assertIn('Raised storm risk: stay alert (model estimate)', self.html(at))
        self.assertIn('Model estimate: 27% chance of a storm', self.html(at))
        self.assertEqual((self.model / 'dashboard_forecast_prediction.csv').read_bytes(), written)
        history = pd.read_csv(self.model / 'prediction_history.csv')
        self.assertEqual(history['storm_probability'].tolist(), [.27])  # genuine value, never 0.60


if __name__ == '__main__':
    unittest.main()
