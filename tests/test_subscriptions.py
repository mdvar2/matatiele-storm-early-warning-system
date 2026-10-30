"""Resident subscriptions, encrypted store, verification, warning delivery and worker hook (no network, no SMS)."""
import base64
import json
import re
import shutil
import tempfile
import threading
import unittest
from datetime import timedelta
from pathlib import Path
from unittest.mock import Mock, patch

from cryptography.fernet import Fernet

import subscriber_alerts as alerts
import subscriber_store as store_mod
import subscriptions as subs

PHONE, OTHER = '082 123 4567', '+27 73 987 6543'


class FakeGateway:
    """Records messages; can fail like Twilio."""
    real = False

    def __init__(self):
        self.sent, self.fail_with, self.statuses = [], {}, {}

    def send(self, to, body, kind):
        if to in self.fail_with:
            raise self.fail_with[to]
        self.sent.append((to, body, kind))
        sid = f'SM{len(self.sent):032d}'
        return {'status': 'queued', 'sid': sid}

    def fetch_status(self, sid):
        return self.statuses.get(sid, 'sent')

    def code_for(self, phone):
        body = next(b for to, b, k in reversed(self.sent) if to == phone and k == 'verification')
        return re.search(r'code is (\d{6})', body).group(1)


class TwilioError(Exception):
    def __init__(self, code):
        super().__init__(f'Twilio error {code}')
        self.code = code


def make_store(tmp):
    crypto = store_mod.Crypto(Fernet.generate_key().decode(), 'h' * 40)
    return store_mod.SubscriberStore(store_mod.LocalFileBlob(Path(tmp) / 'subscribers.json'), crypto)


class Base(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix='subs-')
        self.addCleanup(shutil.rmtree, self.tmp, True)
        self.store, self.gw = make_store(self.tmp), FakeGateway()

    def subscribe(self, phone=PHONE):
        subs.request_code(self.store, self.gw, phone, 'subscribe', consent=True)
        return subs.verify_code(self.store, phone, self.gw.code_for(subs.normalise_sa_mobile(phone)), 'subscribe')

    def raw(self):
        return (Path(self.tmp) / 'subscribers.json').read_text(encoding='utf-8')


class Validation(unittest.TestCase):
    def test_south_african_mobile_numbers(self):
        ok = {'082 123 4567': '+27821234567', '0821234567': '+27821234567', '+27 82 123 4567': '+27821234567',
              '27821234567': '+27821234567', '(071) 555-0101': '+27715550101', '060 000 0000': '+27600000000', '084-999-9999': '+27849999999'}
        for raw, e164 in ok.items():
            with self.subTest(raw=raw):
                self.assertEqual(subs.normalise_sa_mobile(raw), e164)
        for bad in ('', 'abc', '082 123 456', '0821234567890', '+44 7700 900123', '011 123 4567', '080 012 3456',
                    '086 123 4567', '087 123 4567', '+2782123456', '1234567890', '082-ABC-4567', None):
            with self.subTest(bad=bad), self.assertRaises(subs.SubscriptionError) as caught:
                subs.normalise_sa_mobile(bad)
            self.assertNotRegex(str(caught.exception), r'\d{9}')

    def test_masking(self):
        self.assertEqual(store_mod.mask_phone('+27821234567'), '+27 82 *** **67')


class Storage(Base):
    def test_numbers_are_encrypted_and_never_stored_in_clear(self):
        self.subscribe()
        raw = self.raw()
        for fragment in ('821234567', '0821234567', '+27821234567', '123 4567'):
            self.assertNotIn(fragment, raw)
        doc = self.store.snapshot()
        sub = next(iter(doc['subscribers'].values()))
        self.assertEqual(self.store.crypto.decrypt_phone(sub['phone_encrypted']), '+27821234567')
        self.assertEqual(sub['phone_masked'], '+27 82 *** **67')
        self.assertNotIn('code', sub)

    def test_wrong_key_cannot_read_numbers(self):
        self.subscribe()
        other = store_mod.Crypto(Fernet.generate_key().decode(), 'x' * 40)
        token = next(iter(self.store.snapshot()['subscribers'].values()))['phone_encrypted']
        with self.assertRaises(store_mod.StoreError):
            other.decrypt_phone(token)

    def test_concurrent_writers_never_lose_updates(self):
        errors = []

        def add(i):
            try:
                self.store.mutate(lambda doc: doc['events'].append({'at': 'x', 'type': f'e{i}', 'subscriber': None, 'detail': ''}))
            except Exception as exc:  # surfaced below instead of dying silently in a thread
                errors.append(exc)
        threads = [threading.Thread(target=add, args=(i,)) for i in range(12)]
        [t.start() for t in threads]; [t.join() for t in threads]
        self.assertEqual(errors, [])
        doc = self.store.snapshot()
        self.assertEqual(len(doc['events']), 12)
        self.assertEqual(doc['version'], 12)

    def test_configuration_errors(self):
        with self.assertRaises(store_mod.StoreError):
            store_mod.Crypto('', 'h' * 40)
        with self.assertRaises(store_mod.StoreError):
            store_mod.Crypto(Fernet.generate_key().decode(), 'short')
        with self.assertRaises(store_mod.StoreError):
            store_mod.open_store({'SUBSCRIBER_ENCRYPTION_KEY': '', 'SUBSCRIBER_HASH_KEY': ''}.get)
        with self.assertRaises(store_mod.StoreError):
            store_mod.open_store({'SUBSCRIBER_ENCRYPTION_KEY': Fernet.generate_key().decode(), 'SUBSCRIBER_HASH_KEY': 'h' * 40,
                                  'SUBSCRIBER_STORE': 'github'}.get)  # repo and token missing


class GitHubBlob(unittest.TestCase):
    def test_contents_api_compare_and_swap(self):
        server = {'sha': None, 'content': None, 'puts': 0, 'conflict_once': True}

        class Session:
            def get(self, url, headers, params, timeout):
                assert headers['Authorization'] == 'Bearer test-token'
                if server['content'] is None:
                    return Mock(status_code=404)
                return Mock(status_code=200, json=lambda: {'sha': server['sha'], 'content': server['content']})

            def put(self, url, headers, json, timeout):
                server['puts'] += 1
                if server['conflict_once'] and server['content'] is not None:
                    server['conflict_once'] = False
                    server['sha'] = 'changed-by-someone-else'
                    return Mock(status_code=409)
                if server['content'] is not None and json.get('sha') != server['sha']:
                    return Mock(status_code=409)
                server['content'], server['sha'] = json['content'], f'sha{server["puts"]}'
                return Mock(status_code=201)

        blob = store_mod.GitHubContentsBlob('owner/private-store', 'test-token', session=Session())
        store = store_mod.SubscriberStore(blob, store_mod.Crypto(Fernet.generate_key().decode(), 'h' * 40))
        store.mutate(lambda doc: doc['events'].append({'type': 'first'}))
        store.mutate(lambda doc: doc['events'].append({'type': 'second'}))  # first PUT conflicts, retried
        doc = json.loads(base64.b64decode(server['content']))
        self.assertEqual([e['type'] for e in doc['events']], ['first', 'second'])
        self.assertEqual(server['puts'], 3)


class Lifecycle(Base):
    def test_subscribe_requires_consent_valid_number_and_area(self):
        with self.assertRaises(subs.SubscriptionError):
            subs.request_code(self.store, self.gw, PHONE, 'subscribe', consent=False)
        with self.assertRaises(subs.SubscriptionError):
            subs.request_code(self.store, self.gw, PHONE, 'subscribe', consent=True, area='durban')
        with self.assertRaises(subs.SubscriptionError):
            subs.request_code(self.store, None, PHONE, 'subscribe', consent=True)  # SMS not configured
        self.assertEqual(self.gw.sent, [])

    def test_verification_activates_and_records_consent(self):
        view = self.subscribe()
        self.assertEqual((view['status'], view['number'], view['area']), ('active', '+27 82 *** **67', subs.AREAS['matatiele']))
        sub = next(iter(self.store.snapshot()['subscribers'].values()))
        self.assertEqual(sub['consent']['version'], subs.CONSENT_VERSION)
        self.assertTrue(sub['verified_at'])
        self.assertIn('expires in 10 minutes', self.gw.sent[0][1])

    def test_wrong_expired_and_locked_codes(self):
        subs.request_code(self.store, self.gw, PHONE, 'subscribe', consent=True)
        code = self.gw.code_for('+27821234567')
        wrong = f'{(int(code) + 1) % 10**6:06d}'
        with self.assertRaisesRegex(subs.SubscriptionError, 'not correct'):
            subs.verify_code(self.store, PHONE, wrong, 'subscribe')
        with self.assertRaisesRegex(subs.SubscriptionError, '6-digit'):
            subs.verify_code(self.store, PHONE, '12ab', 'subscribe')
        for _ in range(3):
            with self.assertRaises(subs.SubscriptionError):
                subs.verify_code(self.store, PHONE, wrong, 'subscribe')
        with self.assertRaisesRegex(subs.SubscriptionError, 'Too many'):
            subs.verify_code(self.store, PHONE, wrong, 'subscribe')
        with self.assertRaises(subs.SubscriptionError):  # the right code no longer works once locked
            subs.verify_code(self.store, PHONE, code, 'subscribe')
        self.assertEqual(subs.subscription_status(self.store, PHONE)['status'], 'pending')
        later = store_mod.utc_now() + timedelta(minutes=2)
        subs.request_code(self.store, self.gw, PHONE, 'subscribe', consent=True, now=later)
        code = self.gw.code_for('+27821234567')
        with self.assertRaisesRegex(subs.SubscriptionError, 'expired'):
            subs.verify_code(self.store, PHONE, code, 'subscribe', now=later + timedelta(minutes=11))

    def test_rate_limits(self):
        now = store_mod.utc_now()
        subs.request_code(self.store, self.gw, PHONE, 'subscribe', consent=True, now=now)
        with self.assertRaisesRegex(subs.SubscriptionError, 'wait a minute'):
            subs.request_code(self.store, self.gw, PHONE, 'subscribe', consent=True, now=now + timedelta(seconds=20))
        subs.request_code(self.store, self.gw, PHONE, 'subscribe', consent=True, now=now + timedelta(minutes=2))
        subs.request_code(self.store, self.gw, PHONE, 'subscribe', consent=True, now=now + timedelta(minutes=4))
        with self.assertRaisesRegex(subs.SubscriptionError, 'Too many codes'):
            subs.request_code(self.store, self.gw, PHONE, 'subscribe', consent=True, now=now + timedelta(minutes=6))
        self.assertEqual(len(self.gw.sent), 3)

    def test_manage_does_not_reveal_unregistered_numbers(self):
        message = subs.request_code(self.store, self.gw, OTHER, 'manage')
        self.assertEqual(self.gw.sent, [])
        self.subscribe()
        later = store_mod.utc_now() + timedelta(minutes=2)
        self.assertEqual(subs.request_code(self.store, self.gw, PHONE, 'manage', now=later), message)

    def test_subscribe_does_not_reveal_registered_numbers(self):
        new_number_reply = subs.request_code(self.store, self.gw, OTHER, 'subscribe', consent=True)
        self.subscribe()
        later = store_mod.utc_now() + timedelta(minutes=2)
        self.assertEqual(subs.request_code(self.store, self.gw, PHONE, 'subscribe', consent=True, now=later), new_number_reply)
        self.assertIn('already subscribed', self.gw.sent[-1][1])  # only the phone's owner learns it
        self.assertNotIn('code is', self.gw.sent[-1][1])
        with self.assertRaisesRegex(subs.SubscriptionError, 'not correct'):  # same next step as a new number
            subs.verify_code(self.store, PHONE, '123456', 'subscribe', now=later)
        self.assertEqual(subs.subscription_status(self.store, PHONE)['status'], 'active')

    def test_manage_and_unsubscribe_erases_number(self):
        self.subscribe()
        subs.request_code(self.store, self.gw, PHONE, 'manage', now=store_mod.utc_now() + timedelta(minutes=2))
        view = subs.verify_code(self.store, PHONE, self.gw.code_for('+27821234567'), 'manage')
        self.assertEqual(view['status'], 'active')
        view = subs.unsubscribe(self.store, PHONE)
        self.assertEqual(view['status'], 'unsubscribed')
        sub = next(iter(self.store.snapshot()['subscribers'].values()))
        self.assertNotIn('phone_encrypted', sub)
        self.assertEqual(subs.statistics(self.store.snapshot()), {'active': 0, 'pending': 0, 'unsubscribed': 1})

    def test_resubscribe_after_unsubscribe(self):
        self.subscribe(); subs.unsubscribe(self.store, PHONE)
        later = store_mod.utc_now() + timedelta(minutes=5)
        subs.request_code(self.store, self.gw, PHONE, 'subscribe', consent=True, now=later)
        subs.verify_code(self.store, PHONE, self.gw.code_for('+27821234567'), 'subscribe', now=later)
        self.assertEqual(subs.subscription_status(self.store, PHONE)['status'], 'active')
        self.assertEqual(len(self.store.snapshot()['subscribers']), 1)


class Delivery(Base):
    KEY = 'REAL-SHORT-V1-2026-10-30T12:00:00+00:00'

    def warn(self, key=KEY):
        return alerts.deliver_warning(self.store, self.gw, key, 'MATATIELE MODEL ALERT test body', '2026-10-30T12:00:00+00:00', .41)

    def test_only_active_verified_subscribers_receive_once(self):
        self.subscribe(PHONE)
        subs.request_code(self.store, self.gw, OTHER, 'subscribe', consent=True)  # pending, never verified
        counts = self.warn()
        warnings = [s for s in self.gw.sent if s[2] == 'warning']
        self.assertEqual([w[0] for w in warnings], ['+27821234567'])
        self.assertEqual(counts, {'recipients': 1, 'submitted': 1, 'failed': 0, 'uncertain': 0})
        self.assertEqual(self.warn(), {'recipients': 0, 'submitted': 0, 'failed': 0, 'uncertain': 0})  # duplicate prevention
        self.assertEqual(len([s for s in self.gw.sent if s[2] == 'warning']), 1)

    def test_unsubscribed_numbers_never_receive(self):
        self.subscribe(PHONE); self.subscribe(OTHER)
        subs.unsubscribe(self.store, OTHER)
        self.warn()
        self.assertEqual([s[0] for s in self.gw.sent if s[2] == 'warning'], ['+27821234567'])

    def test_failures_uncertainty_and_stop(self):
        self.subscribe(PHONE); self.subscribe(OTHER)
        self.gw.fail_with = {'+27821234567': TwilioError(21610), '+27739876543': TimeoutError('timed out')}
        counts = self.warn()
        self.assertEqual(counts, {'recipients': 2, 'submitted': 0, 'failed': 1, 'uncertain': 1})
        doc = self.store.snapshot()
        by_masked = {d['masked']: d for d in doc['deliveries'].values()}
        self.assertEqual(by_masked['+27 82 *** **67']['error'], 'recipient_opted_out')
        self.assertEqual(by_masked['+27 73 *** **43']['status'], 'uncertain')
        self.assertEqual(subs.subscription_status(self.store, PHONE)['status'], 'unsubscribed')  # STOP enforced
        self.gw.fail_with = {}
        self.assertEqual(self.warn()['recipients'], 0)  # uncertain is never resent automatically
        for key, d in doc['deliveries'].items():
            with self.assertRaises(subs.SubscriptionError):
                alerts.retry_failed(self.store, self.gw, key)

    def test_definitive_failure_can_be_retried_by_admin_with_limit(self):
        self.subscribe(PHONE)
        self.gw.fail_with = {'+27821234567': TwilioError(30006)}
        self.warn()
        key = next(iter(self.store.snapshot()['deliveries']))
        self.assertEqual(alerts.retry_failed(self.store, self.gw, key), 'failed')
        self.gw.fail_with = {}
        self.assertEqual(alerts.retry_failed(self.store, self.gw, key), 'submitted')
        with self.assertRaises(subs.SubscriptionError):
            alerts.retry_failed(self.store, self.gw, key)  # only failed deliveries can be retried

    def test_delivery_status_tracking(self):
        self.subscribe(PHONE); self.subscribe(OTHER)
        self.warn()
        sids = {d['masked']: d['sid'] for d in self.store.snapshot()['deliveries'].values()}
        self.gw.statuses = {sids['+27 82 *** **67']: 'delivered', sids['+27 73 *** **43']: 'undelivered'}
        self.assertEqual(alerts.refresh_delivery_statuses(self.store, self.gw), 2)
        statuses = {d['masked']: d['status'] for d in self.store.snapshot()['deliveries'].values()}
        self.assertEqual(statuses, {'+27 82 *** **67': 'delivered', '+27 73 *** **43': 'failed'})

    def test_admin_overview_contains_no_full_numbers(self):
        self.subscribe(PHONE); self.warn()
        text = json.dumps(alerts.admin_overview(self.store.snapshot()))
        self.assertNotIn('821234567', text)
        self.assertNotIn('phone_encrypted', text)
        self.assertIn('+27 82 *** **67', text)


class WorkerHook(Base):
    def env(self, **extra):
        env = {'SUBSCRIBER_ALERTS_ENABLED': 'true', 'SMS_DELIVERY_MODE': 'outbox', 'SUBSCRIBER_STORE': 'file',
               'SUBSCRIBER_STORE_PATH': str(Path(self.tmp) / 'subscribers.json'), 'SMS_OUTBOX_PATH': str(Path(self.tmp) / 'outbox.jsonl'),
               'SUBSCRIBER_ENCRYPTION_KEY': self.key, 'SUBSCRIBER_HASH_KEY': 'h' * 40}
        env.update(extra)
        return env

    def setUp(self):
        super().setUp()
        self.key = Fernet.generate_key().decode()
        self.store = store_mod.SubscriberStore(store_mod.LocalFileBlob(Path(self.tmp) / 'subscribers.json'), store_mod.Crypto(self.key, 'h' * 40))

    def test_disabled_by_default(self):
        self.assertEqual(alerts.run_for_worker('2026-10-30T12:00:00+00:00', .5, .35, {}), {'subscriber_alerts': 'disabled'})
        self.assertEqual(alerts.run_for_worker('2026-10-30T12:00:00+00:00', .5, .35, {'SUBSCRIBER_ALERTS_ENABLED': 'yes'}),
                         {'subscriber_alerts': 'disabled'})

    def test_enabled_sends_to_subscribers_and_never_raises(self):
        self.subscribe(PHONE)
        result = alerts.run_for_worker('2026-10-30T12:00:00+00:00', .5, .35, self.env())
        self.assertEqual(result['subscriber_alerts'], 'sent')
        self.assertEqual(result['subscriber_recipients'], 1)
        outbox = (Path(self.tmp) / 'outbox.jsonl').read_text(encoding='utf-8')
        self.assertIn('MATATIELE MODEL ALERT', outbox); self.assertIn('Storm risk 50%', outbox)
        self.assertNotIn('821234567', outbox)
        again = alerts.run_for_worker('2026-10-30T12:00:00+00:00', .5, .35, self.env())  # same hour: nobody is sent twice
        self.assertEqual((again['subscriber_alerts'], again['subscriber_recipients']), ('no_active_subscribers', 0))
        broken = alerts.run_for_worker('2026-10-30T12:00:00+00:00', .5, .35, self.env(SUBSCRIBER_ENCRYPTION_KEY='not-a-key'))
        self.assertEqual(broken['subscriber_alerts'], 'failed')
        self.assertEqual(alerts.run_for_worker('2026-10-30T12:00:00+00:00', .5, .35, self.env(SMS_DELIVERY_MODE='disabled'))['subscriber_alerts'],
                         'not_configured')


class LedgerHistory(unittest.TestCase):
    def test_only_genuine_warning_records_are_listed(self):
        issues = [{'title': '[SMS-LEDGER] REAL-SHORT-V1-2026-11-02T15:00:00+00:00', 'created_at': '2026-11-02T14:05:40Z', 'html_url': 'https://github.com/x/1'},
                  {'title': '[SMS-LEDGER] CONNECTIVITY-TEST-RUN-38142187487', 'created_at': 'x', 'html_url': 'u'},
                  {'title': '[RUN-LOG] 2026-10', 'created_at': 'x', 'html_url': 'u'},
                  {'title': '[SMS-LEDGER] REAL-SHORT-V1-<script>', 'created_at': 'x', 'html_url': 'u'},
                  {'title': '[SMS-LEDGER] REAL-SHORT-V1-2026-11-01T09:00:00+00:00', 'pull_request': {}, 'created_at': 'x', 'html_url': 'u'}]
        session = Mock(); session.get.return_value = Mock(json=lambda: issues, raise_for_status=lambda: None)
        result = alerts.ledger_warnings('owner/repo', session=session)
        self.assertEqual(result, [{'forecast_hour_utc': '2026-11-02T15:00:00+00:00', 'issued_at_utc': '2026-11-02T14:05:40Z', 'record': 'https://github.com/x/1'}])


if __name__ == '__main__':
    unittest.main()
