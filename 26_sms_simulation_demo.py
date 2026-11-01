"""Reproducible SMS simulation (Mode A): the warning-to-SMS pipeline end to end, with nothing sent.

Steps: a fictional test subscriber registers and verifies; a stated TEST probability is compared with the 35%
threshold; a warning event is recorded; the simulated SMS (labelled TEST ONLY) is written to a temporary outbox;
re-running the same warning sends nothing twice; a provider failure leaves the warning recorded; a below-threshold
value creates no warning.

Safety: everything happens in a new temporary folder with throw-away keys. Network access is blocked inside this
process, so no SMS provider, GitHub ledger or forecast service can be reached. The model, the threshold, the public
warning ledger and any real subscriber store are never touched. The test probability is an input, not a model output.

Run:  python 26_sms_simulation_demo.py [--out results.json]
"""
import argparse
import base64
import json
import os
import re
import socket
import sys
import tempfile
from pathlib import Path

import pandas as pd
from cryptography.fernet import Fernet

THRESHOLD = 0.35
TEST_PHONE = '082 000 0001'  # fictional; the outbox never sends


def block_network():
    def refuse(*args, **kwargs):
        raise OSError('network access is blocked in the SMS simulation')
    socket.socket.connect = refuse
    socket.create_connection = refuse
    socket.getaddrinfo = refuse


class FailingGateway:
    """Stands in for an SMS provider that is unreachable (timeout): the outcome is unknown."""
    mode, real = 'twilio', True

    def send(self, to, body, kind):
        raise TimeoutError('simulated provider timeout')


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument('--out', help='also write the step results to this JSON file')
    args = parser.parse_args()
    block_network()
    work = Path(tempfile.mkdtemp(prefix='sms_sim_'))
    os.environ.update({'SMS_DELIVERY_MODE': 'outbox', 'SUBSCRIBER_STORE': 'file', 'SUBSCRIBER_ALERTS_ENABLED': 'true',
                       'SUBSCRIBER_STORE_PATH': str(work / 'subscribers.json'), 'SMS_OUTBOX_PATH': str(work / 'outbox.jsonl'),
                       'SUBSCRIBER_ENCRYPTION_KEY': Fernet.generate_key().decode(),
                       'SUBSCRIBER_HASH_KEY': base64.urlsafe_b64encode(os.urandom(32)).decode()})
    import subscriber_alerts
    import subscriptions as subs
    import warning_events as we
    from subscriber_store import open_store

    store, gateway = open_store(), subs.gateway_from_config()
    assert gateway.mode == 'outbox' and not gateway.real
    steps = []

    def step(name, **result):
        steps.append({'step': name, **result})
        print(f'{len(steps)}. {name}: ' + json.dumps(result, default=str))

    # 1. A fictional test subscriber registers with consent and verifies the one-time code (code read from the outbox).
    subs.request_code(store, gateway, TEST_PHONE, 'subscribe', consent=True)
    code = re.search(r'code is (\d{6})', gateway.recent(1)[0]['body']).group(1)
    subs.verify_code(store, TEST_PHONE, code, 'subscribe')
    step('Test subscriber registered and verified', subscribers=subs.statistics(store.snapshot()))

    # 2-4. Threshold evaluation, warning event, simulated SMS.
    hour = (pd.Timestamp.now(tz='UTC').floor('h') + pd.Timedelta(hours=1)).isoformat()
    probability = 0.62
    step('Threshold evaluated', test_probability=probability, threshold=THRESHOLD, warning=probability >= THRESHOLD,
         note='stated TEST input, not a model output')
    result = subscriber_alerts.run_for_worker(hour, probability, THRESHOLD)
    doc = store.snapshot()
    key = 'REAL-SHORT-V1-' + pd.Timestamp(hour).isoformat()
    event = we.collect([], doc, include_tests=True)[0]
    step('Warning event recorded', event_id=key, label=event['source'], period=we.period_text(event))
    message = gateway.recent(1)[0]
    step('Simulated SMS written to the local outbox (not sent)', to=message['to'], body=message['body'],
         delivery_status=[d['status'] for d in doc['deliveries'].values()], worker_result=result)

    # 5. Idempotency: the same warning again sends nothing new.
    again = subscriber_alerts.run_for_worker(hour, probability, THRESHOLD)
    step('Same warning run again', worker_result=again, outbox_messages=len(gateway.recent(100)))

    # 6. Provider failure: the warning stays recorded; the delivery is marked unknown and never retried automatically.
    later = (pd.Timestamp(hour) + pd.Timedelta(hours=1)).isoformat()
    later_key = 'REAL-SHORT-V1-' + later
    counts = subscriber_alerts.deliver_warning(store, FailingGateway(), later_key, 'TEST ONLY - provider failure check', later, probability)
    doc = store.snapshot()
    step('Provider failure', counts=counts, warning_still_recorded=later_key in doc['alerts'],
         delivery_status=doc['deliveries'][f'{later_key}|{next(iter(doc["subscribers"]))}']['status'])

    # 7. Below the threshold: no warning, no SMS.
    low = 0.20
    step('Below-threshold value', test_probability=low, warning=low >= THRESHOLD,
         note='the worker stops before the subscriber hook when the estimate is below 35%, so nothing is created')

    summary = {'all_messages_labelled_test': all(m['body'].startswith('TEST ONLY') for m in gateway.recent(100) if m['kind'] == 'warning'),
               'messages_sent_to_a_phone': 0, 'temporary_folder': str(work), 'real_ledger_or_store_touched': False}
    step('Summary', **summary)
    if args.out:
        Path(args.out).write_text(json.dumps(steps, indent=1, default=str), encoding='utf-8')
    return 0


if __name__ == '__main__':
    sys.exit(main())
