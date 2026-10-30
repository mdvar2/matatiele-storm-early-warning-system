"""Verified national emergency numbers for South Africa, with tap-to-call links.

Checked on 30 October 2026 against government sources: the South African Police Service (10111),
the national Department of Tourism safety page (10177 ambulance and fire) and municipal emergency
notices (112 from any cellphone). No local or invented numbers are listed.
"""
import html

CONTACTS = (('10111', 'Police (SAPS)', 'Crime and police emergencies'),
            ('10177', 'Ambulance and fire', 'Medical emergencies and fires'),
            ('112', 'Any emergency from a cellphone', 'Free from any mobile network'))
NOTE = 'Calls go to national emergency services, not to this research system.'
SOURCE = 'Numbers checked against SAPS and South African government sources (October 2026).'


def contacts_html(title='Emergency contacts'):
    rows = ''.join(f'<a class="call-row" href="tel:{number}" aria-label="Call {html.escape(label)} on {number}">'
                   f'<span class="call-icon">📞</span><span><b>{number}</b><small>{html.escape(label)} · {html.escape(detail)}</small></span></a>'
                   for number, label, detail in CONTACTS)
    return (f'<div class="contacts-card"><div class="contacts-head">{html.escape(title)}<small>Tap to call</small></div>{rows}'
            f'<div class="contacts-note">{html.escape(NOTE)} {html.escape(SOURCE)}</div></div>')


def call_row_html():
    """Compact tap-to-call buttons shown inside an open warning."""
    buttons = ''.join(f'<a class="call-chip" href="tel:{number}" aria-label="Call {html.escape(label)} on {number}">📞 {number}</a>'
                      for number, label, _ in CONTACTS)
    return f'<div class="call-chips"><span>Need help?</span>{buttons}</div>'
