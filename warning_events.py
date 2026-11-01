"""Storm warning events, resident acknowledgements and authorised officials' review records.

Events are never created here. A genuine warning is a forecast hour that the hourly worker
reserved in the public warning ledger after the model reached the 35% threshold. In development
outbox mode only, warnings that the worker's subscriber hook wrote to the local test store are
added and labelled as development tests (that mode is refused against the real store).

Acknowledgements record only that a warning was viewed on a device: one per device and warning,
stored as a keyed hash of a random device identifier. They say nothing about anyone's safety.
Officials' review status and notes are records of decisions taken outside this system; nothing
here dispatches or contacts emergency services.
"""
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from subscriber_store import iso, utc_now

SAST = ZoneInfo('Africa/Johannesburg')
KEY_PREFIX = 'REAL-SHORT-V1-'
SEVERITY = 'Storm warning (model estimate of 35% or more)'
LOCATION = 'Matatiele town and its immediate surroundings (one model location)'
GENUINE, DEV_TEST = 'genuine', 'development test'
REVIEW_STATUSES = ('Not reviewed', 'Under review', 'Monitoring', 'Response coordinated outside this system',
                   'Closed - no further action')
MAX_NOTE = 1000
ACK_NOTE = ('This only records that the warning was viewed on this device. It does not tell anyone that you are '
            'safe or that you need help. If you need help, call an emergency number.')


class OperationsError(ValueError):
    """A request that cannot be recorded; the message is safe to show."""


def _time(value):
    moment = datetime.fromisoformat(str(value).replace('Z', '+00:00'))
    return (moment if moment.tzinfo else moment.replace(tzinfo=timezone.utc)).astimezone(SAST)


def make_event(hour_utc, issued_at, source, record=None, probability=None):
    """One warning: the forecast period is the hour ending at `hour_utc`, as in the warning SMS."""
    end = _time(hour_utc)
    return {'key': KEY_PREFIX + end.astimezone(timezone.utc).isoformat(), 'start': end - timedelta(hours=1), 'end': end,
            'issued_at': _time(issued_at) if issued_at else None, 'probability': probability, 'source': source,
            'record': record, 'severity': SEVERITY, 'location': LOCATION}


def collect(ledger_rows, store_doc=None, include_tests=False):
    """Genuine ledger warnings (newest first), with the exact probability where the system recorded it."""
    recorded = (store_doc or {}).get('alerts', {})
    events = {}
    for row in ledger_rows or []:
        event = make_event(row['forecast_hour_utc'], row.get('issued_at_utc'), GENUINE, row.get('record'))
        event['probability'] = recorded.get(event['key'], {}).get('probability')
        events[event['key']] = event
    if include_tests:
        for key, alert in recorded.items():
            if key not in events and key.startswith(KEY_PREFIX):
                events[key] = make_event(key[len(KEY_PREFIX):], alert.get('created_at'), DEV_TEST, None, alert.get('probability'))
    return sorted(events.values(), key=lambda e: e['end'], reverse=True)


def is_active(event, now=None):
    """Active until its forecast period has ended (warnings are issued shortly before the period)."""
    return (now or utc_now()) < event['end']


def probability_text(event):
    p = event.get('probability')
    return f'{float(p):.0%}' if p is not None else '35% or higher (exact value not in the public record)'


def period_text(event):
    start, end = event['start'], event['end']
    return f'{start:%d %b %Y %H:%M} - {end:%H:%M} SAST' if start.date() == end.date() else f'{start:%d %b %H:%M} - {end:%d %b %H:%M} SAST'


# ---------------------------------------------------------------- resident acknowledgements
def _device(store, device_id):
    if not device_id or len(str(device_id)) < 16:
        raise OperationsError('This device could not be identified, so the acknowledgement was not recorded.')
    return store.crypto.secret_hash('device', str(device_id))


def acknowledge(store, event_key, device_id, now=None):
    """Record one acknowledgement per device and warning. Returns ('recorded'|'already', iso time)."""
    device = _device(store, device_id)
    now = now or utc_now()

    def change(doc):
        acks = doc['acknowledgements'].setdefault(event_key, {})
        if device in acks:
            return 'already', acks[device]
        acks[device] = iso(now)
        return 'recorded', acks[device]
    return store.mutate(change)


def acknowledged_at(store, doc, event_key, device_id):
    if not device_id:
        return None
    return doc['acknowledgements'].get(event_key, {}).get(store.crypto.secret_hash('device', str(device_id)))


def acknowledgement_count(doc, event_key):
    return len(doc['acknowledgements'].get(event_key, {}))


# ---------------------------------------------------------------- officials' review records
def review_status(doc, event_key):
    return doc['reviews'].get(event_key, {'status': 'Not reviewed', 'updated_at': None, 'updated_by': None})


def record_review(store, event_key, official, status=None, note='', now=None):
    """Record a status change and/or a note with the official's name and the time."""
    note = (note or '').strip()
    if status is not None and status not in REVIEW_STATUSES:
        raise OperationsError('Choose a review status from the list.')
    if len(note) > MAX_NOTE:
        raise OperationsError(f'Notes are limited to {MAX_NOTE} characters.')
    if not official:
        raise OperationsError('Sign in again to record a review.')
    now = now or utc_now()

    def change(doc):
        current = review_status(doc, event_key)['status']
        changed = status is not None and status != current
        if not changed and not note:
            raise OperationsError('Nothing to record: change the status or add a note.')
        if changed:
            doc['reviews'][event_key] = {'status': status, 'updated_at': iso(now), 'updated_by': official}
        action = {'at': iso(now), 'warning': event_key, 'official': official, 'status': status if changed else None, 'note': note}
        doc['actions'].append(action)
        return action
    return store.mutate(change)


def actions(doc, event_key=None):
    rows = [(i, a) for i, a in enumerate(doc['actions']) if event_key is None or a['warning'] == event_key]
    return [a for _, a in sorted(rows, key=lambda row: (row[1]['at'], row[0]), reverse=True)]  # newest first, ties by record order
