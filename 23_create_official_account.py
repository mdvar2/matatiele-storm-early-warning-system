"""Create one line for the OFFICIAL_ACCOUNTS secret (disaster-management decision-support portal).

Run: python 23_create_official_account.py
The password is typed without being shown and is never saved. Paste the printed line into the
OFFICIAL_ACCOUNTS secret in Streamlit (one line per official). Do not commit it.
"""
from getpass import getpass

import officials

username = input('Official username (3-40 characters: a-z, 0-9, . _ -): ').strip().lower()
if not officials.USERNAME.match(username):
    raise SystemExit('Invalid username.')
password = getpass('Password (at least 12 characters): ')
if password != getpass('Repeat password: '):
    raise SystemExit('Passwords do not match.')
print(f'{username}:{officials.hash_password(password)}')
