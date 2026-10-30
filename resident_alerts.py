"""Resident Alerts page: current and past storm warnings, warning details, acknowledgement,
emergency contacts and SMS alerts. Rendering only; records live in warning_events.py.
"""
import html
import uuid
from pathlib import Path

import streamlit as st
import streamlit.components.v1 as components

import emergency_contacts
import icons
import resident_pages
import resident_view
import subscriber_alerts as alerts
import subscriptions as subs
import warning_events as we
from subscriber_store import StoreError, open_store, utc_now

LEDGER_REPO = resident_pages.LEDGER_REPO
SAWS_URL = 'https://www.weathersa.co.za/'
VIEWS = ('Warnings', 'SMS alerts')
VIEW_LABELS = {'Warnings': ':material/warning: Warnings', 'SMS alerts': ':material/sms: SMS alerts'}
_device = components.declare_component('device_id', path=str(Path(__file__).resolve().parent / 'components' / 'device_id'))


def device_id():
    """(identifier or None, state): 'ready' (kept in this browser), 'pending' (browser has not answered yet)
    or 'session' (local storage unavailable: this visit only)."""
    try:
        value = _device(key='device_id', default=None)
    except Exception:  # components unavailable
        value = 'unavailable'
    if isinstance(value, str) and len(value) >= 16:
        return value, 'ready'
    if value == 'unavailable':
        return st.session_state.setdefault('ack_session_id', uuid.uuid4().hex), 'session'
    return None, 'pending'  # never fall back early: a click now could create a second record for this device


@st.cache_data(ttl=300, show_spinner=False)
def _ledger(repo):
    return alerts.ledger_warnings(repo)


def load_events(getter):
    """Genuine warnings from the public ledger (+ labelled development tests in outbox mode). Returns (events, error)."""
    error = None
    try:
        rows = _ledger(LEDGER_REPO)
    except Exception:
        rows, error = [], 'The public warning record could not be reached. Please try again later.'
    try:
        doc = open_store(getter).snapshot()
    except Exception:  # store not configured or unreachable: genuine ledger warnings still list
        doc = None
    return we.collect(rows, doc, include_tests=subs.delivery_mode(getter) == 'outbox'), error


def operations_store(getter):
    try:
        return open_store(getter, kind='operations'), None
    except StoreError as exc:
        return None, str(exc)


def _sast(moment):
    return f'{moment:%d %b %Y %H:%M} SAST' if moment is not None else 'Unknown'


def warning_card_html(event, active):
    test = event['source'] == we.DEV_TEST
    badge = '<span class="warn-badge test">DEVELOPMENT TEST · not a real warning</span>' if test else \
        ('<span class="warn-badge live">IN EFFECT</span>' if active else '<span class="warn-badge past">ENDED</span>')
    return (f'<div class="warn-card {"active" if active else "past"}"><div class="warn-top"><b>{icons.icon("siren")} {html.escape(event["severity"])}</b>{badge}</div>'
            f'<div class="warn-meta"><span>{icons.icon("clock")} {html.escape(we.period_text(event))}</span><span>{icons.icon("map-pin")} Matatiele</span>'
            f'<span>{icons.icon("trend")} {html.escape(we.probability_text(event))}</span></div></div>')


def status_banner_html(active_events, status):
    genuine = [e for e in active_events if e['source'] == we.GENUINE]
    if active_events and not genuine:
        return (f'<div class="alert-banner amber"><div class="ab-kicker">DEVELOPMENT TEST · NOT A REAL WARNING</div>'
                f'<div class="ab-title">Test warning for {html.escape(we.period_text(active_events[0]))}</div>'
                '<div class="ab-text">Created on a development computer to demonstrate the warning pages. '
                f'{html.escape(status["estimate"])} is the genuine current model estimate.</div></div>')
    if genuine:
        latest = genuine[0]
        return (f'<div class="alert-banner red"><div class="ab-kicker">STORM WARNING IN EFFECT</div>'
                f'<div class="ab-title">Storm warning for Matatiele, {html.escape(we.period_text(latest))}</div>'
                '<div class="ab-text">Take precautions now. Open the warning for what to do.</div></div>')
    return ''  # no warning in effect: the risk card already shows the current estimate


def render_alerts(getter, status):
    """Warnings (list and details) and SMS alerts. The current status, contacts and SAWS link are on Home only."""
    st.html('<div class="section-title">Alerts <small>Storm warnings for Matatiele and SMS alerts</small></div>')
    st.session_state.setdefault('alerts_view', VIEWS[0])
    view = st.segmented_control('Alerts section', VIEWS, key='alerts_view', format_func=VIEW_LABELS.get, label_visibility='collapsed')
    if view == VIEWS[1]:
        resident_pages.render_sms_alerts(getter)
        return
    events, error = load_events(getter)
    selected = st.session_state.get('alert_selected')
    chosen = next((e for e in events if e['key'] == selected), None)
    if chosen:
        _detail(getter, chosen)
        return
    now = utc_now()
    active = [e for e in events if we.is_active(e, now)]
    if any(e['source'] == we.DEV_TEST for e in events):
        resident_pages.dev_banner()
    if error:
        st.info(error)
    st.markdown('**Current warnings**')
    if active:
        for event in active:
            _event_row(event, True)
    else:
        st.html(f'<div class="warn-card"><div class="warn-top"><b>{icons.icon("check-circle")} No severe weather warning issued by this research system</b></div></div>')
    past = [e for e in events if not we.is_active(e, now)]
    st.markdown('**Past warnings**')
    if past:
        for event in past:
            _event_row(event, False)
    elif not error:
        st.info('No storm warnings have been issued by this system yet.')


def _event_row(event, active):
    card, action = st.columns([4, 1], vertical_alignment='center')
    card.html(warning_card_html(event, active))
    if action.button('View', key='open_' + event['key'], width='stretch', type='primary' if active else 'secondary'):
        st.session_state.alert_selected = event['key']
        st.rerun()


def _detail(getter, event):
    if st.button('All warnings', key='alert_back', icon=':material/arrow_back:'):
        st.session_state.pop('alert_selected', None)
        st.rerun()
    test = event['source'] == we.DEV_TEST
    if test:
        st.html('<div class="alert-banner amber"><div class="ab-kicker">DEVELOPMENT TEST</div>'
                '<div class="ab-title">This is a test record created on a development computer, not a real warning.</div></div>')
    active = we.is_active(event)
    st.html(f'<div class="resident-card tone-{"red" if active else "gray"} warn-detail">'
            f'<div class="resident-head">{html.escape(event["severity"])}</div>'
            f'<div class="hero-estimate">{"In effect" if active else "Ended"} · {html.escape(we.period_text(event))}</div>'
            f'<div class="resident-facts"><span><b>Location</b>{html.escape(event["location"])}</span>'
            f'<span><b>Model estimate</b>{html.escape(we.probability_text(event))}</span>'
            f'<span><b>Issued</b>{html.escape(_sast(event["issued_at"]))}</span></div>'
            f'<div class="resident-note">{html.escape(resident_view.MODEL_NOTE)}</div></div>')
    st.html(resident_view.quick_actions_html(resident_view.guidance('WARNING')))
    st.html(emergency_contacts.call_row_html())  # kept with the warning on purpose: help must be one tap away
    if event.get('record'):
        st.link_button('Public record of this warning', event['record'], icon=':material/open_in_new:')
    _acknowledge(getter, event)
    st.button('Get warnings like this by SMS', key='alert_to_sms', on_click=show_sms_alerts, icon=':material/sms:')


def show_sms_alerts():
    """Callback (runs before the page renders, so it may change the section selector)."""
    st.session_state.alerts_view = VIEWS[1]
    st.session_state.pop('alert_selected', None)


def _acknowledge(getter, event):
    st.markdown('**Acknowledge this warning**')
    store, error = operations_store(getter)
    if store is None:
        st.info('Acknowledgements are not available at the moment.')
        return
    device, state = device_id()
    flash = st.session_state.pop('ack_flash', None)
    try:
        when = we.acknowledged_at(store, store.snapshot(), event['key'], device)
    except StoreError:
        st.info('Acknowledgements are not available at the moment.')
        return
    if flash:
        st.success(flash)
    elif when:
        st.success(f'You acknowledged this warning on {_sast(we._time(when))}.')
    elif state == 'pending':
        st.button('Checking this device…', key='ack_pending', disabled=True)
    else:
        if st.button('I have read this warning', key='ack_' + event['key'], type='primary', icon=':material/done:'):
            try:
                outcome, at = we.acknowledge(store, event['key'], device)
                st.session_state.ack_flash = ('Thank you. Your acknowledgement was recorded on ' if outcome == 'recorded'
                                              else 'You had already acknowledged this warning on ') + _sast(we._time(at)) + '.'
            except (we.OperationsError, StoreError) as exc:
                st.session_state.ack_flash = None
                st.error(str(exc))
            else:
                st.rerun()
    st.caption(we.ACK_NOTE + (' (This browser does not keep a device identifier, so the record applies to this visit only.)' if state == 'session' else ''))
