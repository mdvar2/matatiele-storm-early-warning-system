"""Create one DEVELOPMENT TEST warning on this computer, for demonstrating the Alerts page and the officials' portal.

It runs the worker's subscriber hook with a stated test probability, exactly as a warning hour would,
but only in development outbox mode with the local file store: messages go to the local outbox and are
never sent, and the dashboard labels the result "development test - not a real warning". It never
touches the public warning ledger, the model or any real subscriber store.

Run:  SMS_DELIVERY_MODE=outbox python 24_create_dev_test_warning.py [--hours-ahead 1] [--probability 0.62]
"""
import argparse
import os

import pandas as pd

import subscriber_alerts
import subscriptions

parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
parser.add_argument('--hours-ahead', type=int, default=1, help='forecast hour ending this many hours from now (default 1)')
parser.add_argument('--probability', type=float, default=0.62, help='stated test probability (default 0.62)')
args = parser.parse_args()

if subscriptions.delivery_mode() != 'outbox' or (os.getenv('SUBSCRIBER_STORE') or 'file') != 'file':
    raise SystemExit('Refused: development test warnings need SMS_DELIVERY_MODE=outbox and the local file store.')
if not 0.35 <= args.probability <= 1:
    raise SystemExit('The test probability must be between 0.35 and 1 (a warning needs the 35% threshold).')
hour = (pd.Timestamp.now(tz='UTC').floor('h') + pd.Timedelta(hours=args.hours_ahead)).isoformat()
result = subscriber_alerts.run_for_worker(hour, args.probability, 0.35, dict(os.environ, SUBSCRIBER_ALERTS_ENABLED='true'))
print(f'Development test warning for the hour ending {hour} (UTC): {result}')
