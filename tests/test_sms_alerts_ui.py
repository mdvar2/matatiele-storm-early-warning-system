"""Resident SMS journey through the real dashboard and the real worker (development outbox; nothing is sent).

Registration -> verification -> subscription -> warning decision -> SMS submission ->
delivery status -> unsubscription, with the network refused and Twilio unconfigured.
"""
import json
import os
import re
import shutil
import tempfile
from datetime import timedelta
from pathlib import Path
from unittest.mock import patch

from cryptography.fernet import Fernet

import subscriber_alerts as alerts
import subscriber_store as store_mod
import subscriptions as subs
import test_r3_trigger as r3
import test_resident_dashboard as rd

PHONE = '082 123 4567'


class SmsJourney(rd.DashboardHarness):
    def setUp(self):
        super().setUp()
        self.data = Path(tempfile.mkdtemp(prefix='sms-ui-'))
        self.addCleanup(shutil.rmtree, self.data, True)
        self.key = Fernet.generate_key().decode()
        self.sms_env = {'SMS_DELIVERY_MODE': 'outbox', 'SUBSCRIBER_STORE': 'file',
                        'SUBSCRIBER_STORE_PATH': str(self.data / 'subscribers.json'), 'SMS_OUTBOX_PATH': str(self.data / 'outbox.jsonl'),
                        'SUBSCRIBER_ENCRYPTION_KEY': self.key, 'SUBSCRIBER_HASH_KEY': 'k' * 40}
        env = patch.dict(os.environ, self.sms_env)
        env.start(); self.addCleanup(env.stop)
        self.clock = [store_mod.utc_now()]
        clock = patch.object(subs, 'utc_now', lambda: self.clock[0])
        clock.start(); self.addCleanup(clock.stop)

    # ---------------------------------------------------------------- helpers
    def outbox(self):
        path = self.data / 'outbox.jsonl'
        return [json.loads(line) for line in path.read_text(encoding='utf-8').splitlines()] if path.exists() else []

    def latest_code(self):
        return re.search(r'code is (\d{6})', [m for m in self.outbox() if m['kind'] == 'verification'][-1]['body']).group(1)

    def text(self, at):
        parts = [e.proto.body for e in at.get('html') if not e.proto.body.lstrip().startswith('<style')]
        for kind in ('markdown', 'caption', 'success', 'info', 'warning', 'error'):
            parts += [str(getattr(e, 'value', '')) for e in at.get(kind)]
        parts += [frame.value.to_csv() for frame in at.dataframe]
        return '\n'.join(parts)

    def field(self, at, label):
        return next(t for t in at.text_input if t.label == label)

    def open_alerts(self, **query):
        self.write_prediction(.05)
        at = self.app(**query).run()
        self.go(at, 'Alerts')
        next(g for g in at.button_group if g.key == 'alerts_view').set_value('📲 SMS alerts').run()
        return at

    def warnings_view(self, at):
        self.go(at, 'Alerts')
        next(g for g in at.button_group if g.key == 'alerts_view').set_value('⚠️ Warnings').run()
        return at

    def subscribe_via_ui(self, at, phone=PHONE):
        self.field(at, 'South African mobile number').input(phone)
        next(c for c in at.checkbox if c.label == subs.CONSENT_TEXT).check()
        self.button(at, 'Send verification code').click().run()
        self.assertIn('We sent a 6-digit code to +27 82 *** **67', self.text(at))
        self.field(at, 'Verification code').input(self.latest_code())
        self.button(at, 'Verify and activate').click().run()
        return at

    # ---------------------------------------------------------------- tests
    def test_registration_closed_when_sms_not_configured(self):
        os.environ['SMS_DELIVERY_MODE'] = 'disabled'
        at = self.open_alerts()
        self.assertIn('SMS registration is not open yet', self.text(at))
        self.assertFalse([b for b in at.button if b.label in ('Send verification code', 'Send code')])
        self.assertEqual(self.outbox(), [])

    def test_subscribe_verify_manage_unsubscribe_through_the_dashboard(self):
        at = self.open_alerts()
        page = self.text(at)
        self.assertIn('DEVELOPMENT MODE', page); self.assertIn('NOT sent', page)
        # Consent is required: nothing is sent without it.
        self.field(at, 'South African mobile number').input(PHONE)
        self.button(at, 'Send verification code').click().run()
        self.assertIn('Please confirm that you agree', self.text(at))
        self.assertEqual(self.outbox(), [])
        # Invalid numbers are refused.
        self.field(at, 'South African mobile number').input('011 123 4567')
        next(c for c in at.checkbox if c.label == subs.CONSENT_TEXT).check()
        self.button(at, 'Send verification code').click().run()
        self.assertIn('not a South African mobile number', self.text(at))
        # Subscribe and verify.
        self.subscribe_via_ui(at)
        page = self.text(at)
        self.assertIn('Your subscription is active', page)
        self.assertIn('+27 82 *** **67', page)
        store = store_mod.open_store(os.environ.get)
        self.assertEqual(subs.statistics(store.snapshot())['active'], 1)
        self.assertNotIn('821234567', (self.data / 'subscribers.json').read_text(encoding='utf-8'))
        # Manage: prove ownership, then unsubscribe (a minute later, past the resend limit).
        self.clock[0] += timedelta(minutes=2)
        self.field(at, 'Your registered mobile number').input(PHONE)
        self.button(at, 'Send code').click().run()
        manage_code = [t for t in at.text_input if t.label == 'Verification code'][-1]
        manage_code.input(self.latest_code())
        self.button(at, 'Confirm').click().run()
        self.assertIn('Active', self.text(at))
        next(c for c in at.checkbox if c.label == 'I want to stop receiving SMS storm warnings').check().run()  # enables the button
        self.button(at, 'Unsubscribe').click().run()
        self.assertIn('You have been unsubscribed', self.text(at))
        self.assertEqual(subs.statistics(store.snapshot())['unsubscribed'], 1)
        sub = next(iter(store.snapshot()['subscribers'].values()))
        self.assertNotIn('phone_encrypted', sub)

    def test_code_still_works_after_reload_or_restart(self):
        at = self.open_alerts()
        self.field(at, 'South African mobile number').input(PHONE)
        next(c for c in at.checkbox if c.label == subs.CONSENT_TEXT).check()
        self.button(at, 'Send verification code').click().run()
        code = self.latest_code()
        import streamlit as st
        st.cache_resource.clear()
        restarted = self.open_alerts()  # a new app session: nothing survives except the subscriber store
        self.assertNotIn('We sent a 6-digit code', self.text(restarted))
        self.field(restarted, 'Mobile number you registered').input(PHONE)
        self.field(restarted, 'Code from the SMS').input(f'{(int(code) + 1) % 10**6:06d}')
        self.button(restarted, 'Verify and activate').click().run()
        self.assertIn('That code is not correct', self.text(restarted))
        self.field(restarted, 'Code from the SMS').input(code)
        self.button(restarted, 'Verify and activate').click().run()
        self.assertIn('Your subscription is active', self.text(restarted))
        self.assertEqual(subs.statistics(store_mod.open_store(os.environ.get).snapshot())['active'], 1)

    def test_warning_reaches_only_active_verified_subscribers_then_stops_after_unsubscribe(self):
        at = self.subscribe_via_ui(self.open_alerts())
        store = store_mod.open_store(os.environ.get)
        subs.request_code(store, subs.OutboxGateway(self.data / 'outbox.jsonl'), '073 987 6543', 'subscribe', consent=True)  # never verified
        env = dict(self.sms_env, SUBSCRIBER_ALERTS_ENABLED='true')
        first = alerts.run_for_worker('2026-10-30T13:00:00+00:00', .62, .35, env)
        self.assertEqual((first['subscriber_alerts'], first['subscriber_recipients'], first['subscriber_submitted']), ('sent', 1, 1))
        warnings = [m for m in self.outbox() if m['kind'] == 'warning']
        self.assertEqual([m['to'] for m in warnings], ['+27 82 *** **67'])
        self.assertIn('Storm risk 62%', warnings[0]['body'])
        self.assertEqual(alerts.run_for_worker('2026-10-30T13:00:00+00:00', .62, .35, env)['subscriber_recipients'], 0)  # re-run: no duplicate
        subs.unsubscribe(store, PHONE)
        later = alerts.run_for_worker('2026-10-30T14:00:00+00:00', .70, .35, env)
        self.assertEqual(later['subscriber_recipients'], 0)
        self.assertEqual(len([m for m in self.outbox() if m['kind'] == 'warning']), 1)

    def test_administration_is_protected_and_shows_masked_data_only(self):
        at = self.subscribe_via_ui(self.open_alerts(admin='1'))
        alerts.run_for_worker('2026-10-30T13:00:00+00:00', .62, .35, dict(self.sms_env, SUBSCRIBER_ALERTS_ENABLED='true'))
        self.assertFalse([b for b in at.button if b.label == 'Administration'])  # not signed in
        at.session_state['dashboard_page'] = '🛠️ Administration'
        at.run()
        self.assertNotIn('Active subscribers', self.text(at))
        self.assertEqual(at.session_state['dashboard_page'], '🏠 Dashboard')
        self.login(at)
        self.button(at, 'Administration').click().run()
        page = self.text(at)
        metrics = {m.label: m.value for m in at.metric}
        self.assertEqual(metrics['Active subscribers'], '1')
        self.assertEqual(metrics['SMS delivery mode'], 'Dev outbox')
        self.assertIn('+27 82 *** **67', page)
        self.assertNotRegex(page, r'0?82\s?123\s?4567|\+?27821234567')
        self.assertIn('outbox', page)
        self.button(at, 'Refresh delivery statuses').click().run()
        self.assertIn('delivery status', self.text(at))

    def test_public_pages_never_show_phone_numbers(self):
        at = self.subscribe_via_ui(self.open_alerts())
        for label in ('Dashboard', 'Safety Advice', 'Alerts', 'About'):
            self.warnings_view(at) if label == 'Alerts' else self.go(at, label)
            self.assertNotRegex(self.text(at), r'0?82\s?123\s?4567|\+?27821234567|\*\*\*', label)

    def test_warning_history_lists_genuine_warnings(self):
        import streamlit as st
        st.cache_data.clear()
        sample = [{'forecast_hour_utc': '2026-11-02T15:00:00+00:00', 'issued_at_utc': '2026-11-02T14:05:40Z', 'record': 'https://github.com/x/issues/9'}]
        with patch.object(alerts, 'ledger_warnings', return_value=sample):
            at = self.warnings_view(self.open_alerts())
        self.assertIn('02 Nov 2026 16:00 - 17:00 SAST', self.text(at))
        self.assertIn('Past warnings', self.text(at))
        st.cache_data.clear()
        with patch.object(alerts, 'ledger_warnings', return_value=[]):
            at = self.warnings_view(self.open_alerts())
        self.assertIn('No storm warnings have been issued', self.text(at))
        st.cache_data.clear()  # network refused by the harness: the page says so instead of failing
        at = self.warnings_view(self.open_alerts())
        self.assertIn('could not be reached', self.text(at))

    def test_simulation_never_reaches_subscribers(self):
        at = self.subscribe_via_ui(self.open_alerts(admin='1'))
        self.login(at)
        at.toggle(key='presentation_test_mode').set_value(True).run()
        self.go(at, 'Dashboard')
        self.assertIn(rd.rv.SIMULATION_LABEL, self.text(at))
        self.assertEqual([m for m in self.outbox() if m['kind'] == 'warning'], [])
        store = store_mod.open_store(os.environ.get)
        self.assertEqual(store.snapshot()['deliveries'], {})


class WorkerIntegration(r3.LedgerHarness):
    """The real scheduled worker with the subscriber hook switched on (outbox; Twilio and GitHub mocked)."""

    def setUp(self):
        super().setUp()
        self.data = Path(tempfile.mkdtemp(prefix='sms-worker-'))
        self.addCleanup(shutil.rmtree, self.data, True)
        key = Fernet.generate_key().decode()
        self.sms_env = {'SMS_DELIVERY_MODE': 'outbox', 'SUBSCRIBER_STORE': 'file', 'SUBSCRIBER_STORE_PATH': str(self.data / 's.json'),
                        'SMS_OUTBOX_PATH': str(self.data / 'outbox.jsonl'), 'SUBSCRIBER_ENCRYPTION_KEY': key, 'SUBSCRIBER_HASH_KEY': 'k' * 40}
        store = store_mod.open_store(self.sms_env.get)
        gateway = subs.OutboxGateway(self.data / 'outbox.jsonl')
        subs.request_code(store, gateway, PHONE, 'subscribe', consent=True)
        code = re.search(r'code is (\d{6})', gateway.recent(1)[0]['body']).group(1)
        subs.verify_code(store, PHONE, code, 'subscribe')

    def warnings(self):
        return [m for m in subs.OutboxGateway(self.data / 'outbox.jsonl').recent(50) if m['kind'] == 'warning']

    def test_flag_off_leaves_worker_behaviour_unchanged(self):
        with patch.dict(os.environ, self.sms_env):
            r = self.live(probability=.62)
        self.assertEqual((r['code'], self.send.call_count, r['record']['subscriber_alerts']), (0, 1, 'disabled'))
        self.assertEqual(self.warnings(), [])

    def test_flag_on_warns_subscribers_once_per_hour(self):
        with patch.dict(os.environ, dict(self.sms_env, SUBSCRIBER_ALERTS_ENABLED='true')):
            first, second = self.live(probability=.62), self.live(probability=.62)
            below = self.live(probability=.20)
        self.assertEqual((first['code'], first['record']['subscriber_alerts'], first['record']['subscriber_recipients']), (0, 'sent', 1))
        self.assertEqual(second['record']['duplicate_prevention'], 'already_reserved')  # ledger stops the second run first
        self.assertEqual(below['record']['subscriber_alerts'], 'not_attempted')
        self.assertEqual(len(self.warnings()), 1)
        self.assertEqual(self.send.call_count, 1)  # existing recipient path unchanged

    def test_subscriber_failure_never_breaks_the_existing_warning(self):
        with patch.dict(os.environ, dict(self.sms_env, SUBSCRIBER_ALERTS_ENABLED='true', SUBSCRIBER_HASH_KEY='short')):
            r = self.live(probability=.62)
        self.assertEqual((r['code'], self.send.call_count, r['record']['subscriber_alerts']), (0, 1, 'failed'))


if __name__ == '__main__':
    import unittest
    unittest.main()
