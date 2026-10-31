"""The outlook builds exactly the live script's 29 inputs for every forecast hour (offline; real model)."""
import unittest
import unittest.mock

import numpy as np
import pandas as pd

import outlook
from inference_harness import MODEL_DIR, model_available, real_model, run_inference, synthetic_payload


@unittest.skipUnless(model_available(), 'model files not present')
class OutlookMatchesLiveScript(unittest.TestCase):
    def payload(self):
        hours = 16
        return synthetic_payload(start='2026-10-29T16:00', hours=hours,
                                 precipitation=list(np.linspace(0, 6, hours)), showers=list(np.linspace(0, 4, hours)),
                                 cape=list(np.linspace(-20, 900, hours)), cloud_cover=list(np.linspace(10, 100, hours)),
                                 wind_direction_10m=list(np.linspace(0, 350, hours)))

    def test_every_outlook_hour_uses_the_live_scripts_exact_inputs_and_score(self):
        payload = self.payload()
        features = (MODEL_DIR / 'live_model_features.txt').read_text(encoding='utf-8').split()
        rows = outlook.score(payload, real_model(), features, now=pd.Timestamp('2026-10-29T17:30Z'), hours=12)
        self.assertEqual([r['lead_hours'] for r in rows], list(range(1, 13)))
        for row in rows[:4] + rows[-2:]:
            with self.subTest(input_hour=str(row['input_hour_utc'])):
                captured = []
                live, error, _ = run_inference(payload, row['input_hour_utc'], capture=captured)
                self.assertIsNone(error)
                expected = captured[0][features].iloc[0]
                mine = pd.DataFrame([outlook.features_for(outlook.training_units(payload), row['input_hour_utc'])])[features].iloc[0]
                pd.testing.assert_series_equal(mine.astype(float), expected.astype(float), check_names=False, rtol=0, atol=0)
                self.assertAlmostEqual(row['score'], float(live['storm_probability']), places=12)

    def test_missing_hours_are_skipped_not_filled(self):
        payload = self.payload()
        payload['hourly']['temperature_2m'][6] = None   # one incomplete forecast hour
        features = (MODEL_DIR / 'live_model_features.txt').read_text(encoding='utf-8').split()
        rows = outlook.score(payload, real_model(), features, now=pd.Timestamp('2026-10-29T17:30Z'), hours=12)
        inputs = [r['input_hour_utc'] for r in rows]
        bad = pd.Timestamp('2026-10-29T22:00Z')
        self.assertNotIn(bad, inputs)                                # that hour has no current input
        self.assertNotIn(bad + pd.Timedelta(hours=1), inputs)        # and the next lacks its previous hour
        self.assertEqual(len(rows), 10)

    def test_first_exceedance_ignores_the_next_hour_and_uses_35_percent(self):
        rows = [{'lead_hours': 1, 'score': .9}, {'lead_hours': 2, 'score': .34}, {'lead_hours': 3, 'score': .35}, {'lead_hours': 4, 'score': .8}]
        self.assertEqual(outlook.first_exceedance(rows)['lead_hours'], 3)  # the next hour is the existing warning's job
        self.assertIsNone(outlook.first_exceedance(rows[:3][:2]))


import base64
import importlib.util
import os
import re
import tempfile
from pathlib import Path

from cryptography.fernet import Fernet

from inference_harness import ROOT, _Response

spec = importlib.util.spec_from_file_location('outlook_alert', ROOT / '27_outlook_alert.py')
outlook_alert = importlib.util.module_from_spec(spec); spec.loader.exec_module(outlook_alert)


def storm_payload():
    """A synthetic forecast whose later hours reach the threshold with the real model (no network)."""
    return synthetic_payload(start='2026-10-29T10:00', hours=16, precipitation=[0] * 6 + [5] * 10, showers=[0] * 6 + [4] * 10,
                             cape=[0] * 6 + [1500] * 10, cloud_cover=[20] * 6 + [100] * 10, dew_point_2m=[12] * 6 + [15] * 10)


class Session:
    def __init__(self, payload): self.payload = payload
    def get(self, *a, **k): return _Response(self.payload)


class GitHub:
    """Records issue requests; holds created issues in memory."""
    def __init__(self): self.issues, self.calls = [], []

    def __call__(self, method, url, token, payload=None, timeout=20):
        self.calls.append((method, url))
        if method == 'GET':
            return list(self.issues)
        self.issues.append({'number': len(self.issues) + 1, 'title': payload['title'], 'body': payload['body']})
        return self.issues[-1]


@unittest.skipUnless(model_available(), 'model files not present')
class EarlyAlertStep(unittest.TestCase):
    NOW = pd.Timestamp('2026-10-29T11:30Z')

    def env(self, **extra):
        work = Path(tempfile.mkdtemp())
        env = {'SMS_DELIVERY_MODE': 'outbox', 'SUBSCRIBER_STORE': 'file', 'SUBSCRIBER_STORE_PATH': str(work / 'subscribers.json'),
               'SMS_OUTBOX_PATH': str(work / 'outbox.jsonl'), 'SUBSCRIBER_ENCRYPTION_KEY': Fernet.generate_key().decode(),
               'SUBSCRIBER_HASH_KEY': base64.urlsafe_b64encode(os.urandom(32)).decode(), 'GITHUB_REPOSITORY': 'owner/repo', 'GH_TOKEN': 'x'}
        env.update(extra)
        return env

    def subscribe(self, env, phone, relay):
        import subscriptions as subs
        from subscriber_store import open_store
        store, gateway = open_store(env.get), subs.gateway_from_config(env.get)
        subs.request_code(store, gateway, phone, 'subscribe', consent=True, relay=relay)
        code = re.search(r'code is (\d{6})', gateway.recent(1)[0]['body']).group(1)
        subs.verify_code(store, phone, code, 'subscribe')
        return gateway

    def test_disabled_reports_the_outlook_and_does_nothing_else(self):
        github = GitHub()
        summary = outlook_alert.run(self.env(), now=self.NOW, session=Session(storm_payload()), request=github)
        self.assertEqual(summary['early_alert'], 'due_but_disabled')
        self.assertEqual(github.calls, [])  # no record, no SMS
        self.assertEqual(summary['early_alert_key'], 'OUTLOOK-V1-2026-10-29-evening')  # first hour 17:00-18:00 UTC = 19:00 SAST

    def test_enabled_records_once_and_sends_labelled_alerts_to_residents_and_relays(self):
        env = self.env(OUTLOOK_ALERTS_ENABLED='true', SUBSCRIBER_ALERTS_ENABLED='true')
        gateway = self.subscribe(env, '082 000 0001', relay=False)
        self.subscribe(env, '082 000 0002', relay=True)
        github = GitHub()
        summary = outlook_alert.run(env, now=self.NOW, session=Session(storm_payload()), request=github)
        self.assertEqual((summary['early_alert'], summary['sms']['recipients']), ('recorded', 2))
        self.assertEqual([i['title'] for i in github.issues], ['[OUTLOOK] OUTLOOK-V1-2026-10-29-evening'])
        self.assertIn('not an official warning', github.issues[0]['body'])
        warnings = [m['body'] for m in gateway.recent(10) if m['kind'] == 'warning']
        self.assertEqual(len(warnings), 2)
        self.assertTrue(all(b.startswith('TEST ONLY') and 'EARLY STORM ALERT' in b and 'Not certain' in b for b in warnings))
        self.assertEqual(sum('COMMUNITY RELAY' in b for b in warnings), 1)  # the relay's copy asks them to pass it on
        again = outlook_alert.run(env, now=self.NOW + pd.Timedelta(hours=1), session=Session(storm_payload()), request=github)
        self.assertEqual(again['early_alert'], 'already_alerted')  # same block: no second record, no second SMS
        self.assertEqual(len([m for m in gateway.recent(20) if m['kind'] == 'warning']), 2)

    def test_quiet_outlook_and_failures_never_alert_or_fail_the_job(self):
        quiet = outlook_alert.run(self.env(OUTLOOK_ALERTS_ENABLED='true'), now=pd.Timestamp('2026-10-29T17:30Z'),
                                  session=Session(synthetic_payload(start='2026-10-29T16:00', hours=16)), request=GitHub())
        self.assertEqual(quiet['early_alert'], 'none')
        with unittest.mock.patch.object(outlook_alert, 'run', side_effect=ConnectionError('offline')):
            self.assertEqual(outlook_alert.main({}), 0)


import json as _json
from unittest.mock import patch as _patch

from test_resident_dashboard import ADMIN_TEST_PASSWORD, DashboardHarness


class OfflinePageFiles(unittest.TestCase):
    def test_page_service_worker_and_serving(self):
        static = ROOT / 'static'
        page = (static / 'offline.html').read_text(encoding='utf-8')
        worker = (static / 'sw.js').read_text(encoding='utf-8')
        self.assertIn("fetch('status.json'", page)
        self.assertIn("serviceWorker.register('sw.js')", page)
        self.assertIn('localStorage', page)                      # second fallback when no service worker copy exists
        self.assertIn('Calls need mobile network coverage', page)
        self.assertIn('not an official weather warning service', page)
        for name in ('offline.html', 'manifest.webmanifest', 'icon.svg'):
            self.assertIn(f"'{name}'", worker)                   # kept for offline use
        self.assertIn("caches.match('status.json')", worker)     # last status when the network is down
        self.assertIn("'X-Offline-Copy': '1'", worker)            # saved copies are marked...
        self.assertIn("r.headers.get('X-Offline-Copy')", page)    # ...so the page never calls them live data
        self.assertEqual(_json.loads((static / 'manifest.webmanifest').read_text(encoding='utf-8'))['start_url'], 'offline.html')
        self.assertIn('enableStaticServing = true', (ROOT / '.streamlit' / 'config.toml').read_text(encoding='utf-8'))
        self.assertIn('static/status.json', (ROOT / '.gitignore').read_text(encoding='utf-8'))
        self.assertNotRegex(page, r'https?://')                  # self-contained: nothing to download


class OfflineStatus(unittest.TestCase):
    def status(self, probability, stale=False):
        import resident_view as rv
        from datetime import datetime
        from zoneinfo import ZoneInfo
        t = datetime(2026, 10, 31, 12, tzinfo=ZoneInfo('Africa/Johannesburg'))
        return rv.resident_status(probability, t, t, t, stale, False)

    def test_build_uses_the_genuine_decision_and_lists_emergency_numbers(self):
        import offline_page
        data = offline_page.build(self.status(.05), .05, {'state': 'none'}, [])
        self.assertEqual((data['risk_score'], data['risk_level'], data['decision']), ('5%', 'LOW RISK', 'NO WARNING TRIGGERED'))
        self.assertEqual([c[0] for c in data['emergency']], ['10111', '10177', '112'])
        self.assertNotRegex(_json.dumps(data), r'\+27|0[6-8]\d{8}')   # no phone numbers of people
        stale = offline_page.build(self.status(.5, stale=True), .5, {'state': 'none'}, [])
        self.assertEqual((stale['risk_level'], stale['decision']), ('OUT OF DATE', 'NO DECISION'))

    def test_write_only_when_content_changes(self):
        import offline_page
        path = Path(tempfile.mkdtemp()) / 'static' / 'status.json'
        data = offline_page.build(self.status(.05), .05, {'state': 'none'}, [])
        self.assertTrue(offline_page.write(path, data))
        self.assertFalse(offline_page.write(path, dict(data, generated_utc='later', generated_sast='later')))
        self.assertTrue(offline_page.write(path, offline_page.build(self.status(.4), .4, {'state': 'none'}, [])))


@unittest.skipUnless(model_available(), 'model files not present')
class HomeOutlookAndOfflineStatus(DashboardHarness):
    def status_file(self):
        return _json.loads((self.tmp / 'static' / 'status.json').read_text(encoding='utf-8'))

    def test_outlook_card_shows_an_early_alert_from_the_real_model(self):
        self.write_prediction(.05)
        payload = storm_payload()
        # The harness clock is 30 Oct 2026 10:20 SAST (08:20 UTC); shift the synthetic storm forecast onto it.
        payload['hourly']['time'] = pd.date_range('2026-10-30T07:00', periods=16, freq='h').strftime('%Y-%m-%dT%H:%M').tolist()
        with _patch('outlook.fetch', return_value=payload), _patch('joblib.load', return_value=real_model()):
            at = self.app().run()
        page = self.html(at)
        self.assertIn('Storm-risk outlook', page)
        self.assertIn('EARLY ALERT: raised storm risk from about', page)
        self.assertIn('unvalidated', page)
        self.assertIn('NO WARNING TRIGGERED', page)  # the outlook never changes the next-hour decision
        self.assertTrue(self.status_file()['early_alert'].startswith('Raised storm risk from about'))

    def test_no_forecast_means_no_outlook_and_the_status_file_is_genuine(self):
        self.write_prediction(.05)
        at = self.app(admin='1').run()
        self.assertIn('Outlook unavailable', self.html(at))  # the harness blocks the network
        self.assertEqual(self.status_file()['risk_score'], '5%')
        next(t for t in at.text_input if t.label == 'Administrator Password').input(ADMIN_TEST_PASSWORD)
        next(b for b in at.button if b.label == 'Unlock Admin Controls').click().run()
        at.toggle(key='presentation_test_mode').set_value(True).run()   # simulated 60% on screen
        at.toggle(key='demo_offline').set_value(True).run()            # demonstration outage for this session
        data = self.status_file()
        self.assertEqual((data['risk_score'], data['risk_level']), ('5%', 'LOW RISK'))  # neither reaches the shared file
        self.assertIn('Offline access', self.html(self.app().run()))


class ReferenceLayout(DashboardHarness):
    def test_banner_reports_the_real_data_state_and_next_refresh(self):
        self.write_prediction(.05)
        page = self.html(self.app().run())
        self.assertIn('class="banner"', page)
        self.assertIn('Matatiele, Eastern Cape', page)
        self.assertIn('System online', page)
        self.assertIn('Next refresh in ~', page)
        self.assertIn('Protecting Matatiele through earlier warnings', page)  # sidebar card
        self.write_prediction(.05, fresh=False)
        stale = self.html(self.app(inference_ok=False).run())
        self.assertIn('Saved data · last update', stale)
        self.assertNotIn('System online', stale)

    def test_risk_line_appears_only_with_genuine_outlook_scores(self):
        import dashboard_theme
        self.write_prediction(.05)
        at = self.app().run()   # no forecast in the harness: no outlook scores
        charts = [c.proto.spec for c in at.get('vega_lite_chart')]
        self.assertFalse(any('Storm-risk score (%)' in spec and '"mark": {"type": "line", "color": "#d93449"' in spec for spec in charts))
        self.assertIn('body:has([data-testid=stSidebar][aria-expanded="true"]) .st-key-top_nav_bar {display:none}', dashboard_theme.CHROME_CSS)  # top bar only when the side menu is closed
        self.assertIn('app/static/matatiele_storm_banner.jpg', dashboard_theme.CHROME_CSS)  # the supplied artwork, served from ./static
        self.assertIn('app/static/matatiele_storm_banner_small.jpg', dashboard_theme.CHROME_CSS)  # a smaller file for phones
        self.assertTrue((ROOT / 'static' / 'matatiele_storm_banner.jpg').stat().st_size < 200_000)
        self.assertIn('Illustrative artwork of Matatiele, not current weather', dashboard_theme.banner_html(
            __import__('datetime').datetime(2026, 11, 1, 9, 15), True, 'Next refresh in ~12 min'))


class LiveStateChrome(unittest.TestCase):
    def test_countdown_status_and_motion(self):
        import dashboard_theme as t
        from datetime import datetime
        now = datetime(2026, 11, 1, 9, 15)
        self.assertEqual(t.refresh_text(datetime(2026, 11, 1, 9, 27), now), 'Next refresh in ~12 min')
        self.assertEqual(t.refresh_text(datetime(2026, 11, 1, 9, 10), now), 'Refreshing now')
        self.assertEqual(t.refresh_text(None, now), 'Refreshes every 15 min')
        fresh, stale = t.banner_html(now, True, 'x'), t.banner_html(now, False, 'x', '01 Nov 08:00 SAST')
        self.assertIn('bn-chip ok', fresh); self.assertNotIn('Saved data', fresh)
        self.assertIn('bn-chip stale', stale); self.assertIn('last update 01 Nov 08:00 SAST', stale); self.assertNotIn('System online', stale)
        self.assertIn('.bn-chip.ok i {background:#16a34a;animation:pulse', t.CHROME_CSS)       # pulse only when current
        self.assertNotIn('.bn-chip.stale i {background:#d97706;animation', t.CHROME_CSS)
        self.assertIn('.chip.stale .dot {animation:none}', t.CHROME_CSS)
        self.assertIn('@media (prefers-reduced-motion: reduce) {.bn-chip.ok i,.bn-updated,.summary-grid.just-updated {animation:none!important}}', t.CHROME_CSS)
        self.assertIn('class="bn-updated">Updated', t.banner_html(now, True, 'x', just_updated=True))
