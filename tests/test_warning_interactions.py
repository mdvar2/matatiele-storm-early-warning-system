"""Resident warning interactions and the officials' decision-support portal (no network, no SMS)."""
import json
import os
import shutil
import sys
import tempfile
import threading
import unittest
from datetime import timedelta
from pathlib import Path
from unittest.mock import patch

from cryptography.fernet import Fernet

sys.path.insert(0, str(Path(__file__).resolve().parent))
import test_resident_dashboard as rd  # noqa: E402

import emergency_contacts  # noqa: E402
import officials  # noqa: E402
import resident_alerts  # noqa: E402
import subscriber_alerts as alerts  # noqa: E402
import subscriber_store as store_mod  # noqa: E402
import warning_events as we  # noqa: E402

NOW = store_mod.utc_now().replace(minute=20, second=0, microsecond=0)
ACTIVE_HOUR = (NOW + timedelta(hours=1)).replace(minute=0).isoformat()      # period in progress / upcoming
PAST_HOUR = (NOW - timedelta(days=2)).replace(minute=0).isoformat()
LEDGER = [{'forecast_hour_utc': ACTIVE_HOUR, 'issued_at_utc': (NOW - timedelta(minutes=8)).isoformat(), 'record': 'https://github.com/x/issues/2'},
          {'forecast_hour_utc': PAST_HOUR, 'issued_at_utc': (NOW - timedelta(days=2, hours=1)).isoformat(), 'record': 'https://github.com/x/issues/1'}]
DEVICE = '6f1c2d4e-1111-4abc-9def-0123456789ab'
PASSWORD = 'correct-horse-battery-staple'


def ops_store(tmp):
    crypto = store_mod.Crypto(Fernet.generate_key().decode(), 'h' * 40)
    return store_mod.SubscriberStore(store_mod.LocalFileBlob(Path(tmp) / 'operations.json'), crypto,
                                     store_mod.empty_operations, store_mod.prune_operations)


class Events(unittest.TestCase):
    def test_genuine_ledger_warnings_with_recorded_probability(self):
        doc = {'alerts': {we.KEY_PREFIX + PAST_HOUR: {'probability': .4123, 'created_at': PAST_HOUR}}}
        events = we.collect(LEDGER, doc)
        self.assertEqual([e['source'] for e in events], [we.GENUINE, we.GENUINE])
        self.assertGreater(events[0]['end'], events[1]['end'])  # newest first
        self.assertEqual(we.probability_text(events[1]), '41%')
        self.assertIn('35% or higher', we.probability_text(events[0]))  # never invented
        self.assertEqual(events[0]['end'] - events[0]['start'], timedelta(hours=1))  # hour ending, as in the SMS
        with patch.object(we, 'utc_now', lambda: NOW):
            self.assertEqual([we.is_active(e) for e in events], [True, False])

    def test_development_tests_only_when_requested_and_labelled(self):
        doc = {'alerts': {we.KEY_PREFIX + '2026-10-01T10:00:00+00:00': {'probability': .62, 'created_at': '2026-10-01T09:12:00+00:00'}}}
        self.assertEqual(we.collect([], doc), [])
        events = we.collect([], doc, include_tests=True)
        self.assertEqual([e['source'] for e in events], [we.DEV_TEST])
        self.assertEqual(we.period_text(events[0]), '01 Oct 2026 11:00 - 12:00 SAST')


class Banner(unittest.TestCase):
    STATUS = {'estimate': 'Model estimate: 5% chance of a storm', 'period': '30 Oct 11:00 - 12:00 (SAST)'}

    def test_development_tests_never_look_like_real_warnings(self):
        test_event = we.make_event(ACTIVE_HOUR, NOW.isoformat(), we.DEV_TEST)
        banner = resident_alerts.status_banner_html([test_event], self.STATUS)
        self.assertIn('NOT A REAL WARNING', banner); self.assertNotIn('STORM WARNING IN EFFECT', banner)
        genuine = we.make_event(ACTIVE_HOUR, NOW.isoformat(), we.GENUINE)
        self.assertIn('STORM WARNING IN EFFECT', resident_alerts.status_banner_html([test_event, genuine], self.STATUS))
        self.assertEqual(resident_alerts.status_banner_html([], self.STATUS), '')  # no separate "no warning" card


class Acknowledgements(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix='ops-'); self.addCleanup(shutil.rmtree, self.tmp, True)
        self.store = ops_store(self.tmp)
        self.key = we.KEY_PREFIX + ACTIVE_HOUR

    def test_one_per_device_and_persistent_across_restarts(self):
        self.assertEqual(we.acknowledge(self.store, self.key, DEVICE)[0], 'recorded')
        restarted = store_mod.SubscriberStore(self.store.blob, self.store.crypto, store_mod.empty_operations, store_mod.prune_operations)
        outcome, at = we.acknowledge(restarted, self.key, DEVICE)
        self.assertEqual(outcome, 'already')
        doc = restarted.snapshot()
        self.assertEqual(we.acknowledgement_count(doc, self.key), 1)
        self.assertEqual(we.acknowledged_at(restarted, doc, self.key, DEVICE), at)
        self.assertNotIn(DEVICE, (Path(self.tmp) / 'operations.json').read_text(encoding='utf-8'))  # only a keyed hash is stored

    def test_concurrent_acknowledgements(self):
        def run(device):
            we.acknowledge(ops_store_same, self.key, device)
        ops_store_same = self.store
        same = [threading.Thread(target=run, args=(DEVICE,)) for _ in range(10)]
        many = [threading.Thread(target=run, args=(f'{i:032x}',)) for i in range(15)]
        [t.start() for t in same + many]; [t.join() for t in same + many]
        self.assertEqual(we.acknowledgement_count(self.store.snapshot(), self.key), 16)

    def test_unidentified_device_is_refused(self):
        for device in (None, '', 'short'):
            with self.assertRaises(we.OperationsError):
                we.acknowledge(self.store, self.key, device)

    def test_wording_never_implies_safety(self):
        self.assertIn('does not tell anyone that you are safe', we.ACK_NOTE)


class Reviews(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix='ops-'); self.addCleanup(shutil.rmtree, self.tmp, True)
        self.store = ops_store(self.tmp)
        self.key = we.KEY_PREFIX + ACTIVE_HOUR

    def test_status_and_notes_are_attributed_and_timestamped(self):
        self.assertEqual(we.review_status(self.store.snapshot(), self.key)['status'], 'Not reviewed')
        we.record_review(self.store, self.key, 'n.dlamini', 'Under review', 'Checking river levels.')
        we.record_review(self.store, self.key, 'n.dlamini', 'Under review', 'Councillors informed.')  # note only
        we.record_review(self.store, self.key, 'k.mokoena', 'Monitoring')
        doc = self.store.snapshot()
        review = we.review_status(doc, self.key)
        self.assertEqual((review['status'], review['updated_by']), ('Monitoring', 'k.mokoena'))
        rows = we.actions(doc, self.key)
        self.assertEqual([(r['official'], r['status'], r['note']) for r in rows],
                         [('k.mokoena', 'Monitoring', ''), ('n.dlamini', None, 'Councillors informed.'),
                          ('n.dlamini', 'Under review', 'Checking river levels.')])
        self.assertTrue(all(r['at'] for r in rows))

    def test_invalid_requests_are_refused(self):
        for status, note in (('Dispatch ambulances', ''), (None, ''), ('Not reviewed', ''), (None, 'x' * (we.MAX_NOTE + 1))):
            with self.subTest(status=status), self.assertRaises(we.OperationsError):
                we.record_review(self.store, self.key, 'n.dlamini', status, note)
        with self.assertRaises(we.OperationsError):
            we.record_review(self.store, self.key, '', 'Monitoring')
        self.assertEqual(self.store.snapshot()['actions'], [])

    def test_no_dispatch_status_exists(self):
        for status in we.REVIEW_STATUSES:
            self.assertNotRegex(status.lower(), r'dispatch|deploy|evacuat')


class OfficialAccounts(unittest.TestCase):
    def test_hashing_and_verification(self):
        line = 'n.dlamini:' + officials.hash_password(PASSWORD, iterations=1000)
        self.assertNotIn(PASSWORD, line)
        accounts = officials.parse_accounts(line + ';bad entry;Upper:case$x')
        self.assertEqual(list(accounts), ['n.dlamini'])
        self.assertTrue(officials.verify(accounts, 'N.Dlamini ', PASSWORD))
        for user, password in (('n.dlamini', 'wrong-password-123'), ('nobody', PASSWORD), ('n.dlamini', '')):
            self.assertFalse(officials.verify(accounts, user, password))
        with self.assertRaises(ValueError):
            officials.hash_password('short')


class EmergencyContacts(unittest.TestCase):
    def test_verified_national_numbers_with_tap_to_call(self):
        page = emergency_contacts.contacts_html()
        for number in ('10111', '10177', '112'):
            self.assertIn(f'href="tel:{number}"', page)
        self.assertEqual([c[0] for c in emergency_contacts.CONTACTS], ['10111', '10177', '112'])
        self.assertIn('Calls connect to emergency services, not to the Matatiele Storm Early Warning System.', page)
        self.assertNotRegex(page, r'20\d\d|checked against')  # no dates or source notes in the resident-facing disclaimer


class WarningJourneys(rd.DashboardHarness):
    """The real dashboard: a resident acknowledges a warning; an official reviews it."""

    def setUp(self):
        super().setUp()
        import streamlit as st
        st.cache_data.clear()
        self.data = Path(tempfile.mkdtemp(prefix='warn-ui-')); self.addCleanup(shutil.rmtree, self.data, True)
        self.env_values = {'SMS_DELIVERY_MODE': 'outbox', 'SUBSCRIBER_STORE': 'file', 'SUBSCRIBER_STORE_PATH': str(self.data / 'subscribers.json'),
                           'SMS_OUTBOX_PATH': str(self.data / 'outbox.jsonl'), 'SUBSCRIBER_ENCRYPTION_KEY': Fernet.generate_key().decode(),
                           'SUBSCRIBER_HASH_KEY': 'k' * 40,
                           'OFFICIAL_ACCOUNTS': 'n.dlamini:' + officials.hash_password(PASSWORD, iterations=1000)}
        for target in (patch.dict(os.environ, self.env_values), patch.object(alerts, 'ledger_warnings', return_value=LEDGER),
                       patch.object(we, 'utc_now', lambda: NOW), patch.object(resident_alerts, '_device', lambda **kw: DEVICE)):
            target.start(); self.addCleanup(target.stop)
        self.write_prediction(.05)

    def ops(self):
        return store_mod.open_store(os.environ.get, kind='operations')

    def open_warning(self, at, key):
        self.go(at, 'Alerts')
        next(g for g in at.button_group if g.key == 'alerts_view').set_value('Warnings').run()
        next(b for b in at.button if b.key == 'open_' + key).click().run()
        return at

    def test_homepage_banner_contacts_and_link_to_the_active_warning(self):
        at = self.app().run()
        page = self.html(at)
        self.assertIn('STORM WARNING IN EFFECT', page)
        self.assertIn('href="tel:10177"', page)
        next(b for b in at.button if b.key == 'home_open_warning').click().run()
        self.assertEqual(at.session_state['dashboard_page'], '🚨 Alerts')
        self.assertIn('I have read this warning', [b.label for b in at.button])

    def test_resident_views_details_and_acknowledges_once(self):
        key = we.KEY_PREFIX + ACTIVE_HOUR
        at = self.open_warning(self.app().run(), key)
        page = self.html(at)
        for part in (we.SEVERITY, 'Matatiele town', 'Act now', 'href="tel:112"', 'In effect'):
            self.assertIn(part, page)
        self.assertIn('does not tell anyone that you are safe', '\n'.join(c.value for c in at.caption))
        next(b for b in at.button if b.label == 'I have read this warning').click().run()
        self.assertIn('Your acknowledgement was recorded', '\n'.join(s.value for s in at.success))
        self.assertEqual(we.acknowledgement_count(self.ops().snapshot(), key), 1)
        # Same device, new visit (or after a restart): already acknowledged, and no second record is possible.
        again = self.open_warning(self.app().run(), key)
        self.assertIn('You acknowledged this warning on', '\n'.join(s.value for s in again.success))
        self.assertNotIn('I have read this warning', [b.label for b in again.button])
        self.assertEqual(we.acknowledgement_count(self.ops().snapshot(), key), 1)

    def test_no_acknowledgement_until_the_browser_identifies_the_device(self):
        key = we.KEY_PREFIX + ACTIVE_HOUR
        with patch.object(resident_alerts, '_device', lambda **kw: None):  # browser has not answered yet
            at = self.open_warning(self.app().run(), key)
        pending = [b for b in at.button if b.label == 'Checking this device…']
        self.assertTrue(pending and pending[0].disabled)
        self.assertNotIn('I have read this warning', [b.label for b in at.button])
        with patch.object(resident_alerts, '_device', lambda **kw: 'unavailable'):  # storage blocked: this visit only
            at = self.open_warning(self.app().run(), key)
            next(b for b in at.button if b.label == 'I have read this warning').click().run()
        self.assertIn('applies to this visit only', ' '.join(c.value for c in at.caption))
        self.assertEqual(we.acknowledgement_count(self.ops().snapshot(), key), 1)

    def test_past_warnings_are_listed_and_open(self):
        at = self.open_warning(self.app().run(), we.KEY_PREFIX + PAST_HOUR)
        self.assertIn('Ended', self.html(at))

    def portal(self):
        return self.app(portal='officials').run()

    def sign_in(self, at, password=PASSWORD):
        next(t for t in at.text_input if t.label == 'Official username').input('n.dlamini')
        next(t for t in at.text_input if t.label == 'Official password').input(password)
        next(b for b in at.button if b.label == 'Sign in').click().run()
        return at

    def test_portal_requires_an_official_account(self):
        at = self.portal()
        self.assertNotIn('Signed in as', self.html(at))
        self.sign_in(at, 'wrong-password-123')
        self.assertIn('Incorrect username or password.', [e.value for e in at.error])
        self.assertNotIn('official_user', at.session_state)
        resident = self.app().run()  # residents never see the portal or its navigation entry
        self.assertNotIn('Disaster-management decision support', self.html(resident))
        nav = next(g for g in resident.button_group if g.key == 'top_nav')
        self.assertFalse([o for o in nav.options if 'official' in o.lower() or 'portal' in o.lower()])

    def test_official_reviews_a_warning_with_aggregate_acknowledgements(self):
        key = we.KEY_PREFIX + ACTIVE_HOUR
        we.acknowledge(self.ops(), key, DEVICE)
        we.acknowledge(self.ops(), key, 'f' * 32)
        at = self.sign_in(self.portal())
        page = self.html(at)
        self.assertIn('Signed in as n.dlamini', page)
        self.assertIn('2 acknowledgements', page)
        self.assertNotIn(DEVICE, page)
        next(b for b in at.button if b.key == 'review_' + key).click().run()
        self.assertEqual(at.session_state['portal_view'], 'Warning details')
        next(s for s in at.selectbox if s.label == 'Review or response status').set_value('Monitoring')
        next(t for t in at.text_area if t.label == 'Operational note (optional)').input('Ward councillors informed by phone.')
        next(b for b in at.button if b.label == 'Record review').click().run()
        self.assertIn('Review recorded.', [s.value for s in at.success])
        doc = self.ops().snapshot()
        self.assertEqual(we.review_status(doc, key)['updated_by'], 'n.dlamini')
        self.assertEqual(we.actions(doc)[0]['note'], 'Ward councillors informed by phone.')
        next(g for g in at.button_group if g.key == 'portal_view').set_value('History & actions').run()
        self.assertIn('Ward councillors informed by phone.', self.html(at))  # themed HTML table of actions
        self.assertEqual(json.loads(json.dumps(doc))['acknowledgements'][key].__len__(), 2)

    def test_simulation_creates_no_warning_events(self):
        at = self.app(admin='1').run()
        self.login(at)
        at.toggle(key='presentation_test_mode').set_value(True).run()
        self.assertEqual(self.ops().snapshot()['actions'], [])
        self.assertEqual(self.ops().snapshot()['acknowledgements'], {})
        events, _ = resident_alerts.load_events(os.environ.get)
        self.assertEqual({e['source'] for e in events}, {we.GENUINE})


if __name__ == '__main__':
    unittest.main()
