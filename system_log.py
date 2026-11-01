"""System log: storm-warning and system events, stored in SQLite for demonstration and evaluation.

Only events the dashboard actually observes are recorded: model risk-level changes, warning records (genuine or
labelled development tests), SMS records with their honest status, forecast-service outages and recoveries, and
administrator demonstrations. Nothing is estimated or invented, and no phone numbers or personal data are stored.

Each event can carry a key; an event with a key is recorded once (INSERT OR IGNORE), so reruns never duplicate it.
The database is a local file (SYSTEM_LOG_PATH, default outputs/system_log.sqlite). On a hosted app that file is
reset when the app restarts; the durable records are the public warning record and the [RUN-LOG] issue.
"""
import sqlite3
from contextlib import closing
from datetime import datetime, timezone
from pathlib import Path

SEVERITIES = ('NORMAL', 'LOW', 'ELEVATED', 'MODERATE', 'HIGH', 'WARNING', 'INFO')
SCHEMA = ('CREATE TABLE IF NOT EXISTS events (id INTEGER PRIMARY KEY AUTOINCREMENT, at_utc TEXT NOT NULL, severity TEXT NOT NULL, '
          'delivery TEXT NOT NULL, status TEXT NOT NULL, key TEXT UNIQUE)',
          'CREATE TABLE IF NOT EXISTS state (name TEXT PRIMARY KEY, value TEXT NOT NULL)')


class SystemLog:
    def __init__(self, path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with closing(self._connect()) as db, db:
            for statement in SCHEMA:
                db.execute(statement)

    def _connect(self):
        return sqlite3.connect(self.path, timeout=10)

    def record(self, severity, delivery, status, key=None, at=None):
        """Add one event; returns True if it was new. An event with a key already recorded is ignored."""
        if severity not in SEVERITIES:
            raise ValueError(f'unknown severity {severity!r}')
        at = (at or datetime.now(timezone.utc)).astimezone(timezone.utc).isoformat(timespec='seconds')
        with closing(self._connect()) as db, db:
            cursor = db.execute('INSERT OR IGNORE INTO events (at_utc, severity, delivery, status, key) VALUES (?, ?, ?, ?, ?)',
                                (at, severity, delivery, status, key))
            return cursor.rowcount == 1

    def swap(self, name, value):
        """Store `value` under `name` and return the previous value (None the first time)."""
        with closing(self._connect()) as db, db:
            row = db.execute('SELECT value FROM state WHERE name = ?', (name,)).fetchone()
            db.execute('INSERT INTO state (name, value) VALUES (?, ?) ON CONFLICT(name) DO UPDATE SET value = excluded.value',
                       (name, str(value)))
            return row[0] if row else None

    def recent(self, limit=100):
        """Newest first: (at_utc, severity, delivery, status) rows."""
        with closing(self._connect()) as db:
            return db.execute('SELECT at_utc, severity, delivery, status FROM events ORDER BY at_utc DESC, id DESC LIMIT ?',
                              (int(limit),)).fetchall()
