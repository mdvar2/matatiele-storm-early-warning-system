"""Persistent, encrypted store for resident SMS subscriptions, warnings and deliveries.

One JSON document, changed only through compare-and-swap mutations so the dashboard
(registration) and the scheduled worker (warnings) never overwrite each other's work.

Backends (SUBSCRIBER_STORE):
  file    a local file with an exclusive lock and atomic replace (default; local use)
  github  one file in a PRIVATE GitHub repository via the contents API; the file SHA is
          the version, so a concurrent write is rejected and retried (production)

Personal data protection:
  * phone numbers are encrypted with Fernet (AES-128-CBC + HMAC-SHA256) using
    SUBSCRIBER_ENCRYPTION_KEY; lookups use HMAC-SHA256 with SUBSCRIBER_HASH_KEY;
  * administrators see only a masked number (+27 82 *** **67);
  * the encrypted number is erased when a resident unsubscribes.
No function here logs or returns a full phone number except `decrypt_phone`, which only
the SMS gateway uses at the moment of sending.
"""
import base64
import contextlib
import hashlib
import hmac
import json
import os
import secrets
import tempfile
import time
from datetime import datetime, timezone
from pathlib import Path

import requests
from cryptography.fernet import Fernet, InvalidToken

SCHEMA = 1
BASE = Path(__file__).resolve().parent
DEFAULT_PATH = BASE / 'outputs' / 'subscribers' / 'subscribers.json'
DEV_KEYS_PATH = BASE / 'outputs' / 'subscribers' / 'dev_keys.json'
MAX_EVENTS = 300


class StoreError(RuntimeError):
    """Store unavailable or misconfigured (message never contains personal data)."""


class ConflictError(StoreError):
    """The document changed since it was read; the mutation is retried."""


def utc_now():
    return datetime.now(timezone.utc)


def iso(moment):
    return moment.astimezone(timezone.utc).isoformat(timespec='seconds')


def empty_document():
    return {'schema': SCHEMA, 'subscribers': {}, 'alerts': {}, 'deliveries': {}, 'otp_sends': {}, 'events': []}


# ------------------------------------------------------------------ crypto
class Crypto:
    def __init__(self, encryption_key, hash_key):
        if not encryption_key or not hash_key or len(hash_key) < 32:
            raise StoreError('Subscriber encryption is not configured.')
        try:
            self._fernet = Fernet(encryption_key.encode() if isinstance(encryption_key, str) else encryption_key)
        except (ValueError, TypeError) as exc:
            raise StoreError('SUBSCRIBER_ENCRYPTION_KEY is not a valid Fernet key.') from exc
        self._hash_key = hash_key.encode()

    def phone_hash(self, e164):
        return hmac.new(self._hash_key, e164.encode(), hashlib.sha256).hexdigest()

    def secret_hash(self, purpose, value):
        """Keyed hash for one-time codes (never stored in clear)."""
        return hmac.new(self._hash_key, f'{purpose}:{value}'.encode(), hashlib.sha256).hexdigest()

    def encrypt_phone(self, e164):
        return self._fernet.encrypt(e164.encode()).decode()

    def decrypt_phone(self, token):
        try:
            return self._fernet.decrypt(token.encode()).decode()
        except (InvalidToken, AttributeError) as exc:
            raise StoreError('Stored number could not be decrypted (wrong or rotated key).') from exc


def mask_phone(e164):
    digits = e164[3:] if e164.startswith('+27') else e164
    return f'+27 {digits[:2]} *** **{digits[-2:]}' if len(digits) >= 4 else '+27 *** ****'


# ------------------------------------------------------------------ blobs
class LocalFileBlob:
    """JSON file with an exclusive lock file; version = integer stored in the document."""

    def __init__(self, path):
        self.path = Path(path)
        self.lock_path = self.path.with_suffix(self.path.suffix + '.lock')

    @contextlib.contextmanager
    def _lock(self, timeout=10):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        deadline = time.monotonic() + timeout
        while True:
            try:
                fd = os.open(self.lock_path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
                break
            except FileExistsError:
                try:  # a crashed writer leaves a lock; locks older than 60 s are stale
                    if time.time() - self.lock_path.stat().st_mtime > 60:
                        self.lock_path.unlink(missing_ok=True)
                        continue
                except FileNotFoundError:
                    continue
                if time.monotonic() > deadline:
                    raise StoreError('Subscriber store is busy; try again.')
                time.sleep(0.05)
            except PermissionError:  # Windows: the previous holder's lock file is still being deleted
                if time.monotonic() > deadline:
                    raise StoreError('Subscriber store is busy; try again.')
                time.sleep(0.05)
        try:
            yield
        finally:
            os.close(fd)
            for _ in range(20):
                try:
                    self.lock_path.unlink(missing_ok=True)
                    break
                except PermissionError:
                    time.sleep(0.02)

    def read(self):
        for _ in range(20):  # Windows briefly refuses access while another writer replaces the file
            if not self.path.exists():
                return empty_document(), 0
            try:
                doc = json.loads(self.path.read_text(encoding='utf-8'))
                return doc, int(doc.get('version', 0))
            except PermissionError:
                time.sleep(0.02)
            except (OSError, ValueError) as exc:
                raise StoreError('Subscriber store file is unreadable.') from exc
        raise StoreError('Subscriber store file is busy.')

    def transaction(self):
        """Exclusive lock for a whole read-modify-write (a local file needs no optimistic retry)."""
        return self._lock()

    def write(self, doc, expected_version, locked=False):
        with (contextlib.nullcontext() if locked else self._lock()):
            _, current = self.read()
            if current != expected_version:
                raise ConflictError('changed')
            doc['version'] = expected_version + 1
            with tempfile.NamedTemporaryFile('w', encoding='utf-8', dir=self.path.parent, suffix='.tmp', delete=False) as handle:
                json.dump(doc, handle, indent=1, sort_keys=True)
                temporary = Path(handle.name)
            for _ in range(20):
                try:
                    os.replace(temporary, self.path)
                    return
                except PermissionError:
                    time.sleep(0.02)
            temporary.unlink(missing_ok=True)
            raise StoreError('Subscriber store file is busy.')

    def describe(self):
        return 'local file'


class GitHubContentsBlob:
    """One JSON file in a private repository; the blob SHA is the version (optimistic concurrency)."""

    def __init__(self, repo, token, path='subscribers.json', branch='main', session=None):
        if not repo or not token:
            raise StoreError('GitHub subscriber store needs SUBSCRIBER_STORE_REPO and SUBSCRIBER_STORE_TOKEN.')
        self.url = f'https://api.github.com/repos/{repo}/contents/{path}'
        self.branch = branch
        self.http = session or requests
        self.headers = {'Authorization': f'Bearer {token}', 'Accept': 'application/vnd.github+json',
                        'X-GitHub-Api-Version': '2022-11-28'}

    def read(self):
        try:
            response = self.http.get(self.url, headers=self.headers, params={'ref': self.branch}, timeout=20)
        except requests.RequestException as exc:
            raise StoreError('GitHub subscriber store is unreachable.') from exc
        if response.status_code == 404:
            return empty_document(), None
        if response.status_code != 200:
            raise StoreError(f'GitHub subscriber store returned HTTP {response.status_code}.')
        body = response.json()
        try:
            doc = json.loads(base64.b64decode(body['content']).decode('utf-8'))
        except (KeyError, ValueError) as exc:
            raise StoreError('GitHub subscriber store content is unreadable.') from exc
        return doc, body['sha']

    def write(self, doc, expected_version):
        doc['version'] = int(doc.get('version', 0)) + 1
        payload = {'message': 'Update subscriber store', 'branch': self.branch,
                   'content': base64.b64encode(json.dumps(doc, indent=1, sort_keys=True).encode()).decode()}
        if expected_version:
            payload['sha'] = expected_version
        try:
            response = self.http.put(self.url, headers=self.headers, json=payload, timeout=20)
        except requests.RequestException as exc:
            raise StoreError('GitHub subscriber store is unreachable.') from exc
        if response.status_code in (409, 422):
            raise ConflictError('changed')
        if response.status_code not in (200, 201):
            raise StoreError(f'GitHub subscriber store returned HTTP {response.status_code}.')

    def describe(self):
        return 'private GitHub repository'


# ------------------------------------------------------------------ store
class SubscriberStore:
    def __init__(self, blob, crypto):
        self.blob, self.crypto = blob, crypto

    def snapshot(self):
        doc, _ = self.blob.read()
        for key, value in empty_document().items():
            doc.setdefault(key, value)
        return doc

    def mutate(self, change, attempts=8):
        """Apply change(doc) -> result and persist; retries on concurrent writes. Raises what change raises."""
        if hasattr(self.blob, 'transaction'):
            with self.blob.transaction():
                doc, version = self.blob.read()
                for key, value in empty_document().items():
                    doc.setdefault(key, value)
                result = change(doc)
                doc['events'] = doc['events'][-MAX_EVENTS:]
                self.blob.write(doc, version, locked=True)
                return result
        for attempt in range(attempts):
            doc, version = self.blob.read()
            for key, value in empty_document().items():
                doc.setdefault(key, value)
            result = change(doc)
            doc['events'] = doc['events'][-MAX_EVENTS:]
            try:
                self.blob.write(doc, version)
                return result
            except ConflictError:
                time.sleep(0.05 * (attempt + 1) + secrets.randbelow(50) / 1000)
        raise StoreError('Subscriber store kept changing; please try again.')


def setting(name, getter=None):
    value = (getter or os.getenv)(name)
    return (value or '').strip()


def dev_keys(path=DEV_KEYS_PATH):
    """Local development only (outbox mode): stable keys kept beside the local store, never committed."""
    path = Path(path)
    if path.exists():
        data = json.loads(path.read_text(encoding='utf-8'))
    else:
        path.parent.mkdir(parents=True, exist_ok=True)
        data = {'encryption_key': Fernet.generate_key().decode(), 'hash_key': base64.urlsafe_b64encode(os.urandom(32)).decode()}
        path.write_text(json.dumps(data), encoding='utf-8')
    return data['encryption_key'], data['hash_key']


def open_store(getter=None):
    """Store from configuration, or raise StoreError explaining what is missing (no secrets in messages)."""
    get = lambda name: setting(name, getter)  # noqa: E731
    encryption_key, hash_key = get('SUBSCRIBER_ENCRYPTION_KEY'), get('SUBSCRIBER_HASH_KEY')
    if not (encryption_key and hash_key) and get('SMS_DELIVERY_MODE') == 'outbox':
        encryption_key, hash_key = dev_keys()
    crypto = Crypto(encryption_key, hash_key)
    backend = get('SUBSCRIBER_STORE') or 'file'
    if backend == 'github':
        blob = GitHubContentsBlob(get('SUBSCRIBER_STORE_REPO'), get('SUBSCRIBER_STORE_TOKEN'),
                                  get('SUBSCRIBER_STORE_FILE') or 'subscribers.json', get('SUBSCRIBER_STORE_BRANCH') or 'main')
    elif backend == 'file':
        blob = LocalFileBlob(get('SUBSCRIBER_STORE_PATH') or DEFAULT_PATH)
    else:
        raise StoreError('SUBSCRIBER_STORE must be "file" or "github".')
    return SubscriberStore(blob, crypto)
