"""Verified national emergency numbers for South Africa, with tap-to-call links.

Checked on 30 October 2026 against government sources: the South African Police Service (10111),
the national Department of Tourism safety page (10177 ambulance and fire) and municipal emergency
notices (112 from any cellphone). No local or invented numbers are listed.
"""
import html

import icons

CONTACTS = (('10111', 'Police (SAPS)', 'Crime and police emergencies'),
            ('10177', 'Ambulance and fire', 'Medical emergencies and fires'),
            ('112', 'Any emergency from a cellphone', 'Free from any mobile network'))
NOTE = 'Calls connect to emergency services, not to the Matatiele Storm Early Warning System.'
SOURCE = 'Numbers checked against SAPS and South African government sources (October 2026).'


def contacts_html(title='Emergency contacts', wide=False):
    """Tap-to-call cards. wide: the three numbers side by side (Safety page); they stack on narrow screens."""
    rows = ''.join(f'<a class="call-row" href="tel:{number}" aria-label="Call {html.escape(label)} on {number}">'
                   f'<span class="call-icon">{icons.icon("phone")}</span><span><b>{number}</b><small>{html.escape(label)} · {html.escape(detail)}</small></span></a>'
                   for number, label, detail in CONTACTS)
    return (f'<div class="contacts-card{" wide" if wide else ""}" id="emergency-contacts"><div class="contacts-head">{html.escape(title)}<small>Tap to call</small></div>'
            f'<div class="call-list">{rows}</div><div class="contacts-note">{html.escape(NOTE)}</div></div>')


def text_lines():
    """Plain-text numbers for the low-data view (no images or links needed)."""
    return [f'{number}: {label} ({detail.lower()})' for number, label, detail in CONTACTS]


def call_row_html():
    """Compact tap-to-call buttons shown inside an open warning."""
    buttons = ''.join(f'<a class="call-chip" href="tel:{number}" aria-label="Call {html.escape(label)} on {number}">{icons.icon("phone")} {number}</a>'
                      for number, label, _ in CONTACTS)
    return f'<div class="call-chips"><span>Need help?</span>{buttons}</div>'
