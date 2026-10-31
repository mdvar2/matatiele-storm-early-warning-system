"""Storm-warning delivery to verified resident subscribers, delivery tracking and warning history.

Called by the scheduled worker only after it has reserved the forecast hour in the
existing GitHub ledger, and only when SUBSCRIBER_ALERTS_ENABLED=true. The model,
threshold, ledger and existing recipient path are unchanged.

Safeguards:
  * eligibility is checked inside the reservation write: active, verified, Matatiele,
    number still stored (unsubscribed numbers are erased, so they cannot be sent to);
  * one delivery record per (warning, subscriber) is reserved BEFORE sending, so a
    re-run never sends twice; pending/uncertain records are never retried automatically;
  * Twilio error 21610 (recipient replied STOP) unsubscribes the resident;
  * only definitive failures can be retried, by an administrator, a limited number of times.
"""
import os
import re

import requests

import subscriptions as subs
from subscriber_store import StoreError, iso, utc_now

ACCEPTED = {'queued', 'accepted', 'sending', 'sent', 'scheduled'}
FINAL_OK, FINAL_FAIL = {'delivered', 'outbox'}, {'failed', 'undelivered', 'canceled'}
DEFINITIVE_ERRORS = {21211: 'invalid_number', 21614: 'not_a_mobile', 21608: 'trial_unverified_number',
                     21610: 'recipient_opted_out', 21612: 'unreachable_route', 30006: 'landline_or_unreachable'}
MAX_ATTEMPTS = 3
TEST_PREFIX = 'TEST ONLY - NOT A REAL WARNING. '


def _delivery_key(alert_key, subscriber_id):
    return f'{alert_key}|{subscriber_id}'


def deliver_warning(store, gateway, alert_key, body, forecast_period, probability, now=None, relay_body=None):
    """Send `body` once to every eligible subscriber (`relay_body` to community relays, if given). Returns counts only."""
    now = now or utc_now()

    def reserve(doc):
        doc['alerts'].setdefault(alert_key, {'key': alert_key, 'created_at': iso(now), 'forecast_period': forecast_period,
                                             'probability': round(float(probability), 4), 'body': body})
        targets = []
        for sub in doc['subscribers'].values():
            key = _delivery_key(alert_key, sub['id'])
            if key in doc['deliveries']:
                continue  # already reserved or sent for this warning
            if sub.get('status') != 'active' or sub.get('area') != subs.AREA or not sub.get('phone_encrypted') or not sub.get('verified_at'):
                continue
            doc['deliveries'][key] = {'alert': alert_key, 'subscriber': sub['id'], 'masked': sub['phone_masked'], 'status': 'pending',
                                      'attempts': 1, 'created_at': iso(now), 'updated_at': iso(now)}
            targets.append((key, sub['phone_encrypted'], relay_body if relay_body and sub.get('role') == 'relay' else body))
        return targets

    targets = store.mutate(reserve)
    outcomes = {key: _send(store, gateway, encrypted, text) for key, encrypted, text in targets}
    if outcomes:
        store.mutate(lambda doc: _record(doc, outcomes, now))
    counts = {'recipients': len(targets), 'submitted': 0, 'failed': 0, 'uncertain': 0}
    for outcome in outcomes.values():
        counts['failed' if outcome['status'] == 'failed' else 'uncertain' if outcome['status'] == 'uncertain' else 'submitted'] += 1
    return counts


def _send(store, gateway, encrypted, body):
    try:
        phone = store.crypto.decrypt_phone(encrypted)
    except StoreError:
        return {'status': 'failed', 'error': 'number_unreadable'}  # nothing was sent
    try:
        result = gateway.send(phone, body, 'warning')
        status = result.get('status', 'queued')
        return {'status': 'outbox' if status == 'outbox' else 'submitted', 'provider_status': status, 'sid': result.get('sid', '')}
    except Exception as exc:  # Twilio raises TwilioRestException with .code
        code = getattr(exc, 'code', None)
        if code in DEFINITIVE_ERRORS:
            return {'status': 'failed', 'error': DEFINITIVE_ERRORS[code], 'error_code': code}
        # Timeout, network error or unknown response: the SMS may have been accepted. Never retried automatically.
        return {'status': 'uncertain', 'error': type(exc).__name__}


def _record(doc, outcomes, now):
    for key, outcome in outcomes.items():
        delivery = doc['deliveries'].get(key)
        if delivery is None:
            continue
        delivery.update(outcome, updated_at=iso(now))
        if outcome.get('error_code') == 21610:  # resident replied STOP to the provider
            sub = doc['subscribers'].get(delivery['subscriber'])
            if sub and sub['status'] != 'unsubscribed':
                subs.mark_unsubscribed(doc, sub, 'provider_stop', now)


def refresh_delivery_statuses(store, gateway, now=None):
    """Poll the provider for deliveries that were accepted but are not final. Returns the number updated."""
    now = now or utc_now()
    doc = store.snapshot()
    pending = {key: d['sid'] for key, d in doc['deliveries'].items() if d.get('status') == 'submitted' and d.get('sid')}
    updates = {}
    for key, sid in list(pending.items())[:100]:
        try:
            status = gateway.fetch_status(sid)
        except Exception:
            continue
        if status in FINAL_OK:
            updates[key] = {'status': 'delivered', 'provider_status': status}
        elif status in FINAL_FAIL:
            updates[key] = {'status': 'failed', 'provider_status': status, 'error': 'provider_reported_' + status}
        elif status:
            updates[key] = {'provider_status': status}
    if updates:
        def apply(d):
            for key, change in updates.items():
                if key in d['deliveries']:
                    d['deliveries'][key].update(change, updated_at=iso(now))
        store.mutate(apply)
    return len(updates)


def retry_failed(store, gateway, delivery_key, now=None):
    """Administrator action: resend one DEFINITIVELY failed delivery to a still-active subscriber."""
    now = now or utc_now()

    def reserve(doc):
        delivery = doc['deliveries'].get(delivery_key)
        if not delivery or delivery['status'] != 'failed':
            raise subs.SubscriptionError('Only deliveries that definitively failed can be retried.')
        if delivery.get('error') == 'recipient_opted_out':
            raise subs.SubscriptionError('The resident opted out; this warning must not be resent.')
        if delivery['attempts'] >= MAX_ATTEMPTS:
            raise subs.SubscriptionError('This delivery has reached the retry limit.')
        sub = doc['subscribers'].get(delivery['subscriber'])
        if not sub or sub['status'] != 'active' or not sub.get('phone_encrypted'):
            raise subs.SubscriptionError('The resident is no longer subscribed.')
        delivery.update(status='pending', attempts=delivery['attempts'] + 1, updated_at=iso(now))
        delivery.pop('error', None); delivery.pop('error_code', None)
        return sub['phone_encrypted'], doc['alerts'][delivery['alert']]['body']

    encrypted, body = store.mutate(reserve)
    outcome = _send(store, gateway, encrypted, body)
    store.mutate(lambda doc: _record(doc, {delivery_key: outcome}, now))
    return outcome['status']


def run_for_worker(prediction_for, probability, threshold, environ=None):
    """Hook for the scheduled worker. Never raises; returns run-record fields (counts only)."""
    env = os.environ if environ is None else environ
    if (env.get('SUBSCRIBER_ALERTS_ENABLED') or '').strip().lower() != 'true':
        return {'subscriber_alerts': 'disabled'}
    try:
        from sms_alert import _build_warning_message
        from subscriber_store import open_store
        getter = env.get
        gateway = subs.gateway_from_config(getter)
        if gateway is None:
            return {'subscriber_alerts': 'not_configured'}
        store = open_store(getter)
        hour = _hour_key(prediction_for)
        body = _build_warning_message('Matatiele', prediction_for, probability, threshold, 0.0, 0.0, 0.0, 0.0)
        if not gateway.real:
            body = TEST_PREFIX + body  # simulation (outbox) messages are labelled; live wording is unchanged
        counts = deliver_warning(store, gateway, 'REAL-SHORT-V1-' + hour, body, str(prediction_for), probability,
                                 relay_body=relay_message(body))
        state = 'no_active_subscribers' if not counts['recipients'] else 'sent' if counts['submitted'] == counts['recipients'] else 'partial'
        return {'subscriber_alerts': state, 'subscriber_recipients': counts['recipients'], 'subscriber_submitted': counts['submitted'],
                'subscriber_failed': counts['failed'], 'subscriber_uncertain': counts['uncertain']}
    except Exception as exc:
        return {'subscriber_alerts': 'failed', 'subscriber_error': type(exc).__name__}


RELAY_SUFFIX = ' COMMUNITY RELAY: please warn people near you (in person, loudhailer, bell).'


def relay_message(body):
    """The warning text for community relays: the same warning, plus the request to pass it on."""
    return body + RELAY_SUFFIX


def announcement_script(kind, period, score_text):
    """A short announcement relays and community radio can read out. kind: 'warning' or 'early'."""
    opening = ('Storm warning for Matatiele' if kind == 'warning' else 'Early storm alert for Matatiele')
    return (f'{opening} from the Matatiele Storm Early Warning research system. A storm is possible {period} '
            f'(model risk score {score_text}; this is not certain). Go indoors when you hear thunder. Keep away from rivers, '
            'streams and flooded roads, and do not cross them. Move animals to safety early, before lightning starts. '
            'This is not an official South African Weather Service warning: follow official warnings. '
            'In an emergency call 10111, 10177, or 112 from a cellphone.')


def _hour_key(prediction_for):
    import pandas as pd
    return pd.Timestamp(prediction_for).tz_convert('UTC').floor('h').isoformat()


# ------------------------------------------------------------------ public warning history
LEDGER_PREFIX = '[SMS-LEDGER] REAL-SHORT-V1-'


def ledger_warnings(repo, session=None, token=None):
    """Genuine storm warnings reserved by the worker, from the public GitHub ledger (no personal data)."""
    http = session or requests
    headers = {'Accept': 'application/vnd.github+json', 'X-GitHub-Api-Version': '2022-11-28'}
    if token:
        headers['Authorization'] = f'Bearer {token}'
    response = http.get(f'https://api.github.com/repos/{repo}/issues', headers=headers,
                        params={'state': 'all', 'per_page': 100, 'sort': 'created', 'direction': 'desc'}, timeout=15)
    response.raise_for_status()
    warnings = []
    for issue in response.json():
        title = issue.get('title', '')
        if 'pull_request' in issue or not title.startswith(LEDGER_PREFIX):
            continue  # connectivity tests and other issues are not storm warnings
        hour = title[len(LEDGER_PREFIX):]
        if re.fullmatch(r'\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\+00:00', hour):
            warnings.append({'forecast_hour_utc': hour, 'issued_at_utc': issue.get('created_at'), 'record': issue.get('html_url')})
    return warnings


# ------------------------------------------------------------------ administrator views (masked)
def admin_overview(doc):
    deliveries = sorted(doc['deliveries'].items(), key=lambda kv: kv[1].get('updated_at', ''), reverse=True)
    by_status = {}
    for _, d in deliveries:
        by_status[d['status']] = by_status.get(d['status'], 0) + 1
    alerts = sorted(doc['alerts'].values(), key=lambda a: a['created_at'], reverse=True)
    return {'subscribers': subs.statistics(doc), 'deliveries_by_status': by_status, 'alerts': alerts,
            'deliveries': [dict(d, key=key) for key, d in deliveries]}
