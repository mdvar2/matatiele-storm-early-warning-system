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
        home = self.app().run()
        self.assertIn('Save for offline use', self.html(home))
        saved = next(b for b in home.get('download_button') if b.proto.label == 'Save for offline use')
        self.assertFalse(saved.proto.disabled)


class ReferenceLayout(DashboardHarness):
    def test_banner_reports_the_real_data_state_and_next_refresh(self):
        self.write_prediction(.05)
        page = self.html(self.app().run())
        self.assertIn('class="banner"', page)
        self.assertIn('Matatiele, Eastern Cape', page)
        self.assertIn('System online', page)
        self.assertRegex(page, r'Next refresh in \d\d:\d\d')  # a real countdown, ticking on the device
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
        self.assertIn('Illustrative Matatiele storm landscape artwork — not current weather.', dashboard_theme.banner_html(
            __import__('datetime').datetime(2026, 11, 1, 9, 15), True, 'Next refresh in 12:00'))


class LiveStateChrome(unittest.TestCase):
    def test_countdown_status_and_motion(self):
        import dashboard_theme as t
        from datetime import datetime
        now = datetime(2026, 11, 1, 9, 15)
        self.assertEqual(t.refresh_text(datetime(2026, 11, 1, 9, 27, 30), now), 'Next refresh in 12:30')
        self.assertEqual(t.refresh_text(datetime(2026, 11, 1, 9, 10), now), 'Refreshing now')
        self.assertEqual(t.refresh_text(None, now), 'Refreshes every 15 min')
        fresh, stale = t.banner_html(now, True, 'x'), t.banner_html(now, False, 'x', '01 Nov 08:00 SAST')
        self.assertIn('bn-chip ok', fresh); self.assertNotIn('Saved data', fresh)
        self.assertIn('bn-chip stale', stale); self.assertIn('last update 01 Nov 08:00 SAST', stale); self.assertNotIn('System online', stale)
        self.assertIn('.bn-chip.ok i {background:#16a34a;animation:ring 2s', t.CHROME_CSS)     # ring only when current
        self.assertNotIn('.bn-chip.stale i {background:#d97706;animation', t.CHROME_CSS)
        self.assertIn('.chip.stale .dot {animation:none}', t.CHROME_CSS)
        self.assertIn('@media (prefers-reduced-motion: reduce) {.bn-chip.ok i,.chip .dot,.chip:not(.stale) .dot,.bn-updated,.summary-grid.just-updated,.risk-arc.animate {animation:none!important}}', t.CHROME_CSS)
        self.assertIn('class="bn-updated">Updated just now', t.banner_html(now, True, 'x', update_state='updated'))
        self.assertIn('Connection restored · latest data retrieved', t.banner_html(now, True, 'x', update_state='restored'))
        self.assertNotIn('bn-updated', fresh)                                                  # nothing without new data
        timer = t.banner_html(now, True, 'x', next_refresh_ms=1000, now_ms=500)
        self.assertIn('data-next="1000" data-now="500"', timer)
        self.assertIn("win.setInterval(tick, 1000)", t.LIVE_CLOCK_JS)                          # ticks on the device
        self.assertNotIn('fetch(', t.LIVE_CLOCK_JS)                                            # never contacts the server


class GaugeMovesOnlyOnRealChange(DashboardHarness):
    def test_sweep_only_when_the_genuine_score_changes(self):
        self.write_prediction(.05)
        at = self.app().run()
        self.assertNotIn('risk-arc animate', self.html(at))            # first view: no movement
        at.run()
        self.assertNotIn('risk-arc animate', self.html(at))            # same score again: still no movement
        self.write_prediction(.27)
        at.run()
        page = self.html(at)
        self.assertIn('risk-arc animate', page)                         # a genuinely new score: sweep from 5% to 27%
        self.assertIn('--to:0.2700;--from:0.0500', page)
        at.run()
        self.assertNotIn('risk-arc animate', self.html(at))


class StylesheetSurvivesTheSanitiser(unittest.TestCase):
    def test_no_tag_like_text_or_control_characters_in_the_stylesheet(self):
        """Streamlit's HTML sanitiser removes a whole <style> block whose text contains '<' followed by a letter or '/'
        (found in a real browser: the page lost all styling). Control characters would corrupt it too."""
        import re
        import dashboard_theme
        for mode in ('light', 'dark'):
            css = dashboard_theme.theme_css(mode)
            self.assertEqual(re.findall(r'<[/\w]', css), [], mode)
            self.assertFalse([c for c in css if ord(c) < 32 and c not in '\n\r\t'], mode)
        self.assertIn("syntax:'\\3C number>'", dashboard_theme.CHROME_CSS)



class OfflineHotfix(unittest.TestCase):
    """The offline page never renders blank, and the downloaded copy works with no server at all."""

    def page(self):
        return (ROOT / 'static' / 'offline.html').read_text(encoding='utf-8')

    def visible_without_script(self, page):
        import re
        return re.sub(r'<script.*?</script>', '', page, flags=re.S)

    def test_plain_html_shell_is_visible_even_without_javascript(self):
        shell = ' '.join(self.visible_without_script(self.page()).split())  # whitespace normalised
        for text in ('Matatiele', 'Storm Early Warning System', 'No saved warning information yet',
                     'Open this offline page once while connected to save the latest warning information for later use.',
                     'href="tel:10111"', 'href="tel:10177"', 'href="tel:112"', 'Lightning', 'Flooding', 'Roads', 'Rivers', 'Livestock',
                     'cannot receive new warnings without a connection'):
            self.assertIn(text, shell)
        self.assertNotRegex(self.page(), r'(src|href)="https?://')        # nothing to download: no CDN, fonts or images
        self.assertNotIn('matatiele_storm_banner', self.page())          # the header artwork is not loaded

    def test_script_handles_missing_and_corrupt_data_without_blanking(self):
        page = self.page()
        self.assertIn("try { var s = JSON.parse(localStorage.getItem(KEY) || 'null'); return valid(s) ? s : null; } catch (e) { return null; }", page)
        self.assertIn("function valid(s) { return !!s && typeof s === 'object' && typeof s.generated_utc === 'string' && 'risk_score' in s; }", page)
        self.assertIn('No connection: showing the last saved information', page)
        self.assertIn('Saved information may be out of date.', page)
        self.assertIn('store(result.s);  // replaced only after a valid new status was read', page)
        self.assertIn('Never blank', page)
        self.assertIn('if (s) { try { render(s); } catch (e) {} setStatus(statusText, connected); }', page)  # a bad field never hides the status
        worker = (ROOT / 'static' / 'sw.js').read_text(encoding='utf-8')
        self.assertIn("text.indexOf('data-matatiele-offline')", worker)   # never caches a platform or error page as this page
        self.assertIn("typeof data.generated_utc !== 'string'", worker)    # never caches an invalid status

    def test_downloaded_copy_embeds_genuine_safe_data(self):
        import offline_page
        import resident_view as rv
        from datetime import datetime
        from zoneinfo import ZoneInfo
        t = datetime(2026, 11, 1, 2, 16, tzinfo=ZoneInfo('Africa/Johannesburg'))
        data = offline_page.build(rv.resident_status(.27, t, t, t, False), .27, {'state': 'none'}, [])
        data['period'] = 'x</script><script>alert(1)</script>'          # hostile text cannot escape the data block
        page = offline_page.download_html(data, ROOT / 'static' / 'offline.html')
        self.assertIn('"risk_score": "27%"', page)
        self.assertIn('NO WARNING TRIGGERED', page)
        self.assertNotIn('</script><script>alert', page)
        self.assertEqual(page.count('id="embedded-status">null<'), 0)
        self.assertNotRegex(page, r'\+27\d|0[6-8]\d{8}')              # no personal phone numbers
        for private in ('subscriber', 'phone_encrypted', 'TWILIO', 'password', 'token'):
            self.assertNotIn(private, page)
        self.assertLess(len(page.encode('utf-8')), 25_000)               # five tabs and the saved outlook: still small for any phone



class SaveForOfflineOnHome(DashboardHarness):
    def test_home_offers_a_genuine_saved_copy_and_survives_a_missing_template(self):
        self.write_prediction(.27)
        at = self.app().run()
        saved = next(b for b in at.get('download_button') if b.proto.label == 'Save for offline use')
        self.assertFalse(saved.proto.disabled)
        self.assertTrue(saved.proto.url)
        template = self.tmp / 'static' / 'offline.html'
        hidden = template.with_suffix('.hidden')
        template.rename(hidden)
        try:
            at = self.app().run()
            self.assertFalse(at.exception)                               # Home still renders in full
            self.assertIn('NO WARNING TRIGGERED', self.html(at))
            self.assertTrue(next(b for b in at.get('download_button') if b.proto.label == 'Save for offline use').proto.disabled)
        finally:
            hidden.rename(template)


class OfflineDashboard(unittest.TestCase):
    """The saved copy is a small offline dashboard: five tabs of genuine saved information, nothing recomputed."""

    def page(self):
        return (ROOT / 'static' / 'offline.html').read_text(encoding='utf-8')

    def snapshot(self, outlook_rows=None, warnings=()):
        import offline_page
        import resident_view as rv
        from datetime import datetime
        from zoneinfo import ZoneInfo
        t = datetime(2026, 11, 1, 3, 15, tzinfo=ZoneInfo('Africa/Johannesburg'))
        return offline_page.build(rv.resident_status(.12, t, t, t, False), .12, {'state': 'none'}, list(warnings), None,
                                  now=t, outlook=outlook_rows,
                                  weather={'temperature': '18.0 °C', 'rain': '0.0 mm', 'wind': '2.0 m/s', 'gust': '3.0 m/s',
                                           'source': 'ECMWF forecast · 02:00 SAST', 'icon': '<img src="x">'},
                                  forecast=[{'hour': '04:00', 'rain': '0.1 mm', 'wind': '3.0 m/s', 'temperature': '17.0 °C', 'phone': 'x'}])

    def test_tabs_and_every_section_are_readable_without_javascript(self):
        import re
        shell = ' '.join(re.sub(r'<script.*?</script>', '', self.page(), flags=re.S).split())
        for tab in ('href="#home"', 'href="#outlook"', 'href="#alerts"', 'href="#safety"', 'href="#more"'):
            self.assertIn(tab, shell)
        for text in ('Saved model outlook — unvalidated beyond one hour', 'Map unavailable offline — reconnect to view forecast rainfall map.',
                     'New weather forecasts, new model results and new warnings need a connection', 'env(safe-area-inset-bottom)'):
            self.assertIn(text, shell)
        page = self.page()
        self.assertIn('No storm warning was active when this information was saved.', page)
        self.assertNotIn('No storm warning now', page)               # the device cannot know the current state
        self.assertIn("'OFFLINE — SAVED INFORMATION'", page)
        self.assertIn("past ? ' past' : ''", page)                   # outlook hours that have passed are marked historical
        self.assertNotRegex(page, r'https?://')

    def test_snapshot_saves_genuine_outlook_threshold_weather_and_nothing_else(self):
        rows = [{'lead_hours': lead, 'target_end_utc': f'2026-11-01T{lead:02d}:00:00+00:00', 'score': .1 * lead, 'input_hour_utc': 'x'}
                for lead in range(1, 5)]
        data = self.snapshot(rows)
        self.assertEqual(data['schema'], 2)
        self.assertEqual(data['threshold'], '35%')
        self.assertEqual([r['hour'] for r in data['outlook']], ['03:00', '04:00', '05:00'])   # lead 2-4 only; start of each hour (SAST)
        self.assertEqual([r['above'] for r in data['outlook']], [False, False, True])          # 20%, 30%, 40% against 35%
        self.assertEqual(data['outlook'][2]['score'], '40%')
        self.assertNotIn('icon', data['weather'])                                               # only the listed text fields
        self.assertEqual(data['forecast'], [{'hour': '04:00', 'rain': '0.1 mm', 'wind': '3.0 m/s', 'temperature': '17.0 °C'}])
        self.assertEqual(self.snapshot()['outlook'], [])                                       # no outlook: none saved, none invented

    def test_only_a_valid_current_result_may_replace_the_saved_snapshot(self):
        import offline_page
        import resident_view as rv
        from datetime import datetime
        from zoneinfo import ZoneInfo
        t = datetime(2026, 11, 1, 3, tzinfo=ZoneInfo('Africa/Johannesburg'))
        good = self.snapshot()
        stale = offline_page.build(rv.resident_status(.5, t, t, t, True), .5, {'state': 'none'}, [])
        missing = offline_page.build(rv.resident_status(float('nan'), t, t, t, False), float('nan'), {'state': 'none'}, [])
        self.assertTrue(offline_page.current(good))
        self.assertFalse(offline_page.current(stale)); self.assertFalse(offline_page.current(missing))
        path = Path(tempfile.mkdtemp()) / 'status.json'
        self.assertIsNone(offline_page.read_saved(path))
        path.write_text('{not json', encoding='utf-8'); self.assertIsNone(offline_page.read_saved(path))
        path.write_text(_json.dumps(stale), encoding='utf-8'); self.assertIsNone(offline_page.read_saved(path))
        offline_page.write(path, good); self.assertEqual(offline_page.read_saved(path)['risk_score'], '12%')

    def test_saved_copy_keeps_warnings_and_contains_no_private_data(self):
        import offline_page
        from datetime import datetime, timezone
        event = {'end': datetime(2026, 11, 1, 3, tzinfo=timezone.utc), 'start': datetime(2026, 11, 1, 2, tzinfo=timezone.utc)}
        with unittest.mock.patch('warning_events.period_text', return_value='04:00-05:00 SAST'):
            page = offline_page.download_html(self.snapshot(warnings=[event]), ROOT / 'static' / 'offline.html')
        self.assertIn('"warnings": [{"title": "Storm warning", "period": "04:00-05:00 SAST"}]', page)
        for private in ('subscriber', 'phone_encrypted', 'TWILIO', 'password', 'token', 'SMS_TEST_RECIPIENT'):
            self.assertNotIn(private, page)
        self.assertNotRegex(page, r'\+27\d|0[6-8]\d{8}')


class ConnectionWatch(unittest.TestCase):
    def test_connection_banner_and_saved_dashboard_need_no_server(self):
        import dashboard_theme
        watch = dashboard_theme.CONNECTION_WATCH
        for text in ('Connection lost — live updates paused', 'Open saved offline dashboard', "addEventListener('offline'",
                     "addEventListener('online'", 'frame.srcdoc = page', 'Back to live dashboard'):
            self.assertIn(text, watch)
        self.assertNotIn('Connection restored', watch)               # only a successful retrieval may say so (the banner)
        html = dashboard_theme.connection_watch_html('<p>x</p><script>y</script>')
        self.assertNotIn('</script><', html[:-len('</script>')])      # the saved page cannot end the script early
        self.assertIn('Connection restored · latest data retrieved', dashboard_theme.banner_html(
            __import__('datetime').datetime(2026, 11, 1, 9), True, 'x', update_state='restored'))


class PhoneNavigationAndSnapshot(DashboardHarness):
    def test_bottom_navigation_reaches_every_section(self):
        import dashboard_theme
        self.write_prediction(.05)
        at = self.app().run()
        labels = {b.key: b.label for b in at.button}
        self.assertEqual([labels[k] for k in ('bnav_Home', 'bnav_Risk', 'bnav_Map', 'bnav_Safety')], ['Home', 'Risk', 'Map', 'Safety'])
        for key in ('more_Alerts', 'more_Forecast', 'more_Historical Data', 'more_About', 'more_sms'):
            self.assertIn(key, labels)                                 # inside the More sheet
        self.assertEqual(sum(b.proto.label == 'Save for offline use' for b in at.get('download_button')), 2)  # Home and More
        next(b for b in at.button if b.key == 'bnav_Risk').click().run()
        self.assertEqual(at.session_state['dashboard_page'], '📈 Risk Analysis')
        self.assertEqual(next(b for b in at.button if b.key == 'bnav_Risk').proto.type, 'primary')   # active state
        next(b for b in at.button if b.key == 'more_About').click().run()
        self.assertEqual(at.session_state['dashboard_page'], 'ℹ️ About')
        self.assertFalse(any('warning in effect' in b.label for b in at.button))  # no warning: no badge, no invented count
        css = dashboard_theme.CHROME_CSS
        for rule in ('.st-key-bottom_nav {display:none!important}', '.st-key-top_nav_bar,[data-testid=stLayoutWrapper]:has(> .st-key-top_nav_bar)',
                     '[data-testid=stPopoverButton] div[aria-hidden="true"] {display:none!important}', 'button[kind=primary] {background:#1d4ed8!important;color:#fff!important}',
                     'padding-bottom:calc(104px + env(safe-area-inset-bottom))', 'position:fixed!important;left:0;right:0;bottom:0'):
            self.assertIn(rule, css)

    def test_a_failed_refresh_never_replaces_the_saved_snapshot(self):
        status = self.tmp / 'static' / 'status.json'
        status.unlink(missing_ok=True)
        self.write_prediction(.27)
        self.app().run()
        good = _json.loads(status.read_text(encoding='utf-8'))
        self.assertEqual((good['risk_score'], good['threshold']), ('27%', '35%'))
        self.write_prediction(.60, fresh=False)                      # the next retrieval fails: out-of-date data
        at = self.app(inference_ok=False).run()
        self.assertEqual(_json.loads(status.read_text(encoding='utf-8'))['risk_score'], '27%')   # the good snapshot is kept
        self.assertIn('Saved forecast / outdated prediction', ' '.join(w.value for w in at.warning))
        saved = next(b for b in at.get('download_button') if b.proto.label == 'Save for offline use')
        self.assertFalse(saved.proto.disabled)                       # residents can still save the last good snapshot
