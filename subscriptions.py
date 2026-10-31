"""Resident SMS subscriptions: validation, consent, phone verification, status and unsubscribe.

SMS delivery mode (SMS_DELIVERY_MODE):
  disabled  default: registration is closed and the dashboard says so
  outbox    LOCAL DEVELOPMENT ONLY: messages are appended to a local outbox file and
            shown on screen, clearly labelled; nothing is sent
  twilio    real SMS through the configured Twilio account

Phone numbers are never logged or shown in full; see subscriber_store for storage.
"""
import json
import re
import secrets
import uuid
from datetime import timedelta
from pathlib import Path

from subscriber_store import BASE, StoreError, iso, mask_phone, setting, utc_now

AREA = 'matatiele'
AREAS = {AREA: 'Matatiele (town and immediate surroundings)'}
CONSENT_VERSION = '2026-10-30'
RELAY_TEXT = ('I am a community relay (for example a ward councillor, community leader or volunteer) and agree to pass '
              'storm warnings on to people nearby, for example in person or by loudhailer.')
CONSENT_TEXT = ('I agree to receive SMS storm warnings for Matatiele from this academic research prototype '
                '(at most a few messages per storm hour, plus verification codes). It is not an official SAWS '
                'warning service. I can unsubscribe at any time on this page or by replying STOP.')
CODE_TTL = timedelta(minutes=10)
MAX_CODE_ATTEMPTS = 5
RESEND_AFTER = timedelta(seconds=60)
MAX_SENDS_PER_HOUR, MAX_SENDS_PER_DAY, GLOBAL_SENDS_PER_HOUR, GLOBAL_SENDS_PER_DAY = 3, 6, 60, 300  # global caps bound SMS cost abuse
OUTBOX_PATH = BASE / 'outputs' / 'subscribers' / 'dev_outbox.jsonl'
# South African mobile ranges (national format 0XX): 060-069, 071-074, 076, 078-079, 081-084.
MOBILE_PREFIXES = {'60', '61', '62', '63', '64', '65', '66', '67', '68', '69', '71', '72', '73', '74', '76', '78', '79', '81', '82', '83', '84'}


class SubscriptionError(ValueError):
    """User-facing problem (message is safe to display; never contains a phone number)."""


# ------------------------------------------------------------------ validation
def normalise_sa_mobile(text):
    digits = re.sub(r'[\s\-().]', '', str(text or ''))
    if digits.startswith('+'):
        digits = digits[1:]
    if not digits.isdigit():
        raise SubscriptionError('Enter a South African mobile number using digits only, e.g. 082 123 4567.')
    if digits.startswith('27') and len(digits) == 11:
        national = digits[2:]
    elif digits.startswith('0') and len(digits) == 10:
        national = digits[1:]
    else:
        raise SubscriptionError('Enter a 10-digit South African mobile number (e.g. 082 123 4567) or +27 format.')
    if national[:2] not in MOBILE_PREFIXES:
        raise SubscriptionError('That is not a South African mobile number. Landline, toll-free and shared-cost numbers cannot receive warnings.')
    return '+27' + national


# ------------------------------------------------------------------ SMS gateways
class OutboxGateway:
    """Development only: records the message locally instead of sending it."""
    mode, real = 'outbox', False

    def __init__(self, path=None):
        self.path = Path(path or OUTBOX_PATH)

    def send(self, to, body, kind):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        sid = 'OUTBOX-' + uuid.uuid4().hex[:12]
        with self.path.open('a', encoding='utf-8') as handle:
            handle.write(json.dumps({'at': iso(utc_now()), 'to': mask_phone(to), 'kind': kind, 'body': body, 'sid': sid}) + '\n')
        return {'status': 'outbox', 'sid': sid}

    def fetch_status(self, sid):
        return 'outbox'

    def recent(self, limit=20):
        if not self.path.exists():
            return []
        lines = self.path.read_text(encoding='utf-8').splitlines()[-limit:]
        return [json.loads(line) for line in reversed(lines)]


class TwilioGateway:
    mode, real = 'twilio', True

    def __init__(self, account_sid, auth_token, from_number, client=None):
        if not (account_sid and auth_token and from_number):
            raise StoreError('Twilio credentials are not configured.')
        if client is None:
            from twilio.rest import Client
            client = Client(account_sid, auth_token)
        self.client, self.from_number = client, from_number

    def send(self, to, body, kind):
        message = self.client.messages.create(to=to, from_=self.from_number, body=body)
        return {'status': str(getattr(message, 'status', 'queued')).lower(), 'sid': getattr(message, 'sid', '')}

    def fetch_status(self, sid):
        return str(getattr(self.client.messages(sid).fetch(), 'status', 'unknown')).lower()


def delivery_mode(getter=None):
    mode = setting('SMS_DELIVERY_MODE', getter) or 'disabled'
    if mode == 'outbox' and setting('SUBSCRIBER_STORE', getter) == 'github':
        return 'disabled'  # the outbox shows codes on screen: never allowed against the real subscriber store
    return mode if mode in ('disabled', 'outbox', 'twilio') else 'disabled'


def gateway_from_config(getter=None):
    mode = delivery_mode(getter)
    if mode == 'outbox':
        return OutboxGateway(setting('SMS_OUTBOX_PATH', getter) or None)
    if mode == 'twilio':
        return TwilioGateway(setting('TWILIO_ACCOUNT_SID', getter), setting('TWILIO_AUTH_TOKEN', getter), setting('TWILIO_FROM_NUMBER', getter))
    return None


# ------------------------------------------------------------------ helpers on the document
def find(doc, phone_hash):
    return next((s for s in doc['subscribers'].values() if s['phone_hash'] == phone_hash), None)


def event(doc, kind, subscriber_id=None, detail=''):
    doc['events'].append({'at': iso(utc_now()), 'type': kind, 'subscriber': subscriber_id, 'detail': detail})


def public_view(sub):
    if not sub:
        return None
    return {'status': sub['status'], 'area': AREAS.get(sub['area'], sub['area']), 'number': sub['phone_masked'],
            'since': sub.get('verified_at') or sub.get('created_at'), 'unsubscribed_at': sub.get('unsubscribed_at')}


def _rate_limit(doc, phone_hash, now):
    recent = [t for t in doc['otp_sends'].get(phone_hash, []) if now - _parse(t) < timedelta(days=1)]
    if recent and now - _parse(recent[-1]) < RESEND_AFTER:
        raise SubscriptionError('Please wait a minute before requesting another code.')
    if sum(now - _parse(t) < timedelta(hours=1) for t in recent) >= MAX_SENDS_PER_HOUR or len(recent) >= MAX_SENDS_PER_DAY:
        raise SubscriptionError('Too many codes were requested for this number. Please try again later.')
    every = [now - _parse(t) for times in doc['otp_sends'].values() for t in times]
    if sum(age < timedelta(hours=1) for age in every) >= GLOBAL_SENDS_PER_HOUR or sum(age < timedelta(days=1) for age in every) >= GLOBAL_SENDS_PER_DAY:
        raise SubscriptionError('The service is receiving too many requests. Please try again later.')
    doc['otp_sends'][phone_hash] = recent + [iso(now)]


def _parse(text):
    from datetime import datetime
    return datetime.fromisoformat(text)


# ------------------------------------------------------------------ resident actions
def request_code(store, gateway, raw_phone, purpose, consent=False, area=AREA, now=None, relay=None):
    """Create/refresh a one-time code and send it. purpose: 'subscribe' or 'manage'. Returns a safe message.

    relay: True or False sets the community-relay role on subscription; None keeps the current role (resident by default).
    """
    if gateway is None:
        raise SubscriptionError('SMS alerts registration is not available yet: the SMS service has not been configured.')
    phone = normalise_sa_mobile(raw_phone)
    if purpose == 'subscribe':
        if area not in AREAS:
            raise SubscriptionError('Warnings are currently available for Matatiele only.')
        if consent is not True:
            raise SubscriptionError('Please confirm that you agree to receive SMS warnings.')
    now = now or utc_now()
    phone_hash = store.crypto.phone_hash(phone)
    code = f'{secrets.randbelow(10**6):06d}'

    def change(doc):
        sub = find(doc, phone_hash)
        if purpose == 'manage' and (sub is None or sub['status'] == 'unsubscribed'):
            return False  # same reply as success: does not reveal whether a number is registered
        _rate_limit(doc, phone_hash, now)
        if purpose == 'subscribe' and sub is not None and sub['status'] == 'active':
            # Same reply and next step as a new number (an unsent decoy code), so the form does not reveal
            # whether a number is registered; only the phone's owner learns it, from the SMS below.
            sub['code'] = {'hash': store.crypto.secret_hash(purpose + sub['id'], secrets.token_hex(16)), 'purpose': purpose,
                           'expires_at': iso(now + CODE_TTL), 'attempts': 0}
            event(doc, 'code_requested', sub['id'], 'subscribe_existing')
            return 'existing'
        if sub is None or sub['status'] == 'unsubscribed':
            sub_id = sub['id'] if sub else uuid.uuid4().hex
            sub = doc['subscribers'][sub_id] = {'id': sub_id, 'phone_hash': phone_hash, 'created_at': iso(now)}
        if purpose == 'subscribe':
            sub.update(status='pending', area=area, phone_encrypted=store.crypto.encrypt_phone(phone), phone_masked=mask_phone(phone),
                       consent={'version': CONSENT_VERSION, 'at': iso(now)}, unsubscribed_at=None, unsubscribe_reason=None)
            sub['role'] = ('relay' if relay else 'resident') if relay is not None else sub.get('role', 'resident')
        sub['code'] = {'hash': store.crypto.secret_hash(purpose + sub['id'], code), 'purpose': purpose,
                       'expires_at': iso(now + CODE_TTL), 'attempts': 0}
        sub['updated_at'] = iso(now)
        event(doc, 'code_requested', sub['id'], purpose)
        return True

    outcome = store.mutate(change)
    if outcome:
        body = (f'Matatiele storm alerts: your verification code is {code}. It expires in 10 minutes. '
                'If you did not request it, ignore this SMS.')
        if outcome == 'existing':
            body = ('Matatiele storm alerts: this number is already subscribed. To view or cancel, use '
                    '"Manage my subscription" on the dashboard. If you did not request this, ignore this SMS.')
        try:
            gateway.send(phone, body, 'verification')
        except Exception as exc:
            raise SubscriptionError('The verification SMS could not be sent. Please try again later.') from exc
    return 'If the number can receive SMS, a 6-digit code has been sent. It expires in 10 minutes.'


def verify_code(store, raw_phone, code, purpose, now=None):
    """Check a code. 'subscribe' activates the subscription; 'manage' proves ownership. Returns public_view."""
    phone = normalise_sa_mobile(raw_phone)
    code = re.sub(r'\s', '', str(code or ''))
    if not re.fullmatch(r'\d{6}', code):
        raise SubscriptionError('Enter the 6-digit code from the SMS.')
    now = now or utc_now()
    phone_hash = store.crypto.phone_hash(phone)

    def change(doc):
        sub = find(doc, phone_hash)
        pending = (sub or {}).get('code')
        if not sub or not pending or pending['purpose'] != purpose:
            return 'missing', None
        if now > _parse(pending['expires_at']):
            sub.pop('code', None); event(doc, 'code_expired', sub['id'])
            return 'expired', None
        if pending['attempts'] >= MAX_CODE_ATTEMPTS:
            sub.pop('code', None); event(doc, 'code_locked', sub['id'])
            return 'locked', None
        if not secrets.compare_digest(pending['hash'], store.crypto.secret_hash(purpose + sub['id'], code)):
            pending['attempts'] += 1
            return ('locked' if pending['attempts'] >= MAX_CODE_ATTEMPTS else 'wrong'), None
        sub.pop('code', None)
        if purpose == 'subscribe':
            sub.update(status='active', verified_at=iso(now), updated_at=iso(now))
            event(doc, 'subscribed', sub['id'])
        else:
            event(doc, 'ownership_verified', sub['id'])
        return 'ok', public_view(sub)

    outcome, view = store.mutate(change)
    # 'missing' and 'wrong' read the same, so the form never reveals whether a number has a pending code.
    messages = {'missing': 'That code is not correct. Check the SMS and try again.',
                'expired': 'The code has expired. Request a new code.',
                'locked': 'Too many wrong attempts. Request a new code.',
                'wrong': 'That code is not correct. Check the SMS and try again.'}
    if outcome != 'ok':
        raise SubscriptionError(messages[outcome])
    return view


def subscription_status(store, raw_phone):
    """Public view for a number whose ownership the caller has already verified."""
    phone_hash = store.crypto.phone_hash(normalise_sa_mobile(raw_phone))
    return public_view(find(store.snapshot(), phone_hash))


def unsubscribe(store, raw_phone, reason='resident', now=None):
    """Stop all future warnings and erase the encrypted number (the keyed hash remains for audit)."""
    phone_hash = store.crypto.phone_hash(normalise_sa_mobile(raw_phone))
    now = now or utc_now()

    def change(doc):
        sub = find(doc, phone_hash)
        if not sub or sub['status'] == 'unsubscribed':
            return public_view(sub)
        mark_unsubscribed(doc, sub, reason, now)
        return public_view(sub)
    return store.mutate(change)


def mark_unsubscribed(doc, sub, reason, now=None):
    now = now or utc_now()
    sub.update(status='unsubscribed', unsubscribed_at=iso(now), unsubscribe_reason=reason, updated_at=iso(now))
    sub.pop('phone_encrypted', None)
    sub.pop('code', None)
    event(doc, 'unsubscribed', sub['id'], reason)


# ------------------------------------------------------------------ administrator summaries (no personal data)
def statistics(doc):
    counts = {'active': 0, 'pending': 0, 'unsubscribed': 0}
    for sub in doc['subscribers'].values():
        counts[sub['status']] = counts.get(sub['status'], 0) + 1
    return counts


def relay_count(doc):
    """Active community relays (a count only)."""
    return sum(1 for sub in doc['subscribers'].values() if sub['status'] == 'active' and sub.get('role') == 'relay')
