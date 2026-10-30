"""Accounts for authorised disaster-management officials (decision-support portal).

OFFICIAL_ACCOUNTS (a secret) lists one account per line or separated by ';', as
`username:pbkdf2_sha256$iterations$salt$hash`. Create a line with 23_create_official_account.py;
plain passwords are never stored. Each official signs in individually, so every review and note
is attributed to a named person.
"""
import base64
import hashlib
import hmac
import re
import secrets

ITERATIONS = 310_000
USERNAME = re.compile(r'^[a-z0-9._-]{3,40}$')
# Compared against when the username is unknown, so both cases take the same time.
_DUMMY = 'pbkdf2_sha256$310000$c2FsdHNhbHRzYWx0c2FsdA==$' + base64.b64encode(b'\0' * 32).decode()


def hash_password(password, iterations=ITERATIONS, salt=None):
    if len(password) < 12:
        raise ValueError('Use at least 12 characters.')
    salt = salt or secrets.token_bytes(16)
    digest = hashlib.pbkdf2_hmac('sha256', password.encode('utf-8'), salt, iterations)
    return f'pbkdf2_sha256${iterations}${base64.b64encode(salt).decode()}${base64.b64encode(digest).decode()}'


def parse_accounts(text):
    accounts = {}
    for entry in re.split(r'[;\n]', text or ''):
        name, _, hashed = entry.strip().partition(':')
        if USERNAME.match(name) and hashed.startswith('pbkdf2_sha256$'):
            accounts[name] = hashed
    return accounts


def _check(hashed, password):
    try:
        _, iterations, salt, digest = hashed.split('$')
        candidate = hashlib.pbkdf2_hmac('sha256', password.encode('utf-8'), base64.b64decode(salt), int(iterations))
        return hmac.compare_digest(candidate, base64.b64decode(digest))
    except (ValueError, TypeError):
        return False


def verify(accounts, username, password):
    username = (username or '').strip().lower()
    hashed = accounts.get(username)
    valid = _check(hashed or _DUMMY, password or '')
    return bool(hashed) and valid
