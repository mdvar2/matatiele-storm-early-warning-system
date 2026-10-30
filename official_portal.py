"""Decision-support portal for authorised disaster-management officials (rendering only).

Officials review genuine warning events, the available forecast geography and aggregate
acknowledgements, and record their review status and notes. Everything shown comes from the
warning ledger, the operations store and the genuine ECMWF forecast. The portal records
decisions taken through officials' own channels: it never contacts or dispatches anyone.
"""
import html
import time

import pandas as pd
import pydeck as pdk
import streamlit as st
from pydeck.types import String

import dashboard_theme
import emergency_contacts
import icons
import officials
import resident_view
import warning_events as we
from subscriber_store import StoreError, utc_now

MATATIELE = (-30.3436, 28.8116)  # same point as the dashboard and the model
VIEWS = ('Active warnings', 'Warning details', 'Geographic risk', 'History & actions')
VIEW_LABELS = dict(zip(VIEWS, (':material/notifications_active: Active warnings', ':material/description: Warning details',
                               ':material/map: Geographic risk', ':material/history: History & actions')))
DISCLAIMER = ('Decision support only. This portal records reviews and notes; it does not dispatch or contact emergency '
              'services, and acknowledgements are anonymous device counts, not people confirmed safe or affected.')


def sign_in(getter, failures, window, limit):
    """Sign-in form. Returns the username once signed in."""
    if st.session_state.get('official_user'):
        return st.session_state.official_user
    st.html('<div class="section-title">Disaster-management decision support <small>Authorised officials only</small></div>')
    accounts = officials.parse_accounts(getter('OFFICIAL_ACCOUNTS'))
    if not accounts:
        st.info('No official accounts are configured for this deployment.')
        return None
    with st.form('official_sign_in'):
        username = st.text_input('Official username')
        password = st.text_input('Official password', type='password')
        submitted = st.form_submit_button('Sign in', type='primary')
    if submitted:
        failures[:] = [t for t in failures if time.monotonic() - t < window]
        if len(failures) >= limit:
            st.error('Too many failed sign-in attempts. Try again in 15 minutes.')
        elif officials.verify(accounts, username, password):
            st.session_state.official_user = username.strip().lower()
            st.rerun()
        else:
            failures.append(time.monotonic())
            st.error('Incorrect username or password.')
    return None


def render(official, events, ops_store, ops_error, regional, regional_valid, current):
    head, out = st.columns([5, 1], vertical_alignment='center')
    head.html(f'<div class="section-title">Disaster-management decision support <small>Signed in as {html.escape(official)}</small></div>')
    if out.button('Sign out', key='official_sign_out', width='stretch'):
        st.session_state.pop('official_user', None)
        st.rerun()
    st.html(f'<div class="portal-note">{html.escape(DISCLAIMER)}</div>')
    if any(e['source'] == we.DEV_TEST for e in events):
        st.html('<div class="alert-banner amber"><div class="ab-kicker">DEVELOPMENT DATA</div><div class="ab-title">Warnings marked '
                '"development test" were created on a development computer and are not real warnings.</div></div>')
    if ops_store is None:
        st.error(f'Operations records are unavailable: {ops_error}')
        return
    try:
        doc = ops_store.snapshot()
    except StoreError as exc:
        st.error(f'Operations records are unavailable: {exc}')
        return
    st.session_state.setdefault('portal_view', VIEWS[0])
    view = st.segmented_control('Portal section', VIEWS, key='portal_view', format_func=VIEW_LABELS.get, label_visibility='collapsed') or VIEWS[0]
    if view == VIEWS[0]:
        _active(events, doc, current)
    elif view == VIEWS[1]:
        _details(official, events, doc, ops_store)
    elif view == VIEWS[2]:
        _geography(regional, regional_valid, current)
    else:
        _history(events, doc)


def _open(key):
    st.session_state.portal_selected = key
    st.session_state.portal_view = VIEWS[1]


def _summary(events, doc):
    rows = []
    for e in events:
        review = we.review_status(doc, e['key'])
        rows.append({'Warning period': we.period_text(e), 'Issued': f'{e["issued_at"]:%d %b %H:%M} SAST' if e['issued_at'] else 'Unknown',
                     'Model estimate': we.probability_text(e), 'Source': e['source'], 'Acknowledgements': we.acknowledgement_count(doc, e['key']),
                     'Review status': review['status'], 'Reviewed by': review['updated_by'] or '-'})
    return pd.DataFrame(rows)


def _active(events, doc, current):
    now = utc_now()
    active = [e for e in events if we.is_active(e, now)]
    recent = [e for e in events if (now - e['end']).days < 30]
    a, b, c, d = st.columns(4)
    a.metric('Warnings in effect', len(active))
    b.metric('Warnings, last 30 days', len(recent))
    c.metric('Acknowledgements (in effect)', sum(we.acknowledgement_count(doc, e['key']) for e in active))
    d.metric('Not yet reviewed', sum(we.review_status(doc, e['key'])['status'] == 'Not reviewed' for e in events))
    st.caption(f'Current next-hour model estimate for Matatiele: {current["estimate"]} ({current["period"]}). '
               'A warning is issued automatically when the estimate reaches 35%.')
    if not active:
        st.info('No storm warning is in effect. Recent and past warnings are under "History & actions".')
    for e in active:
        review = we.review_status(doc, e['key'])
        left, right = st.columns([4, 1], vertical_alignment='center')
        left.html(f'<div class="warn-card active"><div class="warn-top"><b>{icons.icon("siren")} {html.escape(we.period_text(e))}</b>'
                  f'<span class="warn-badge {"test" if e["source"] == we.DEV_TEST else "live"}">{html.escape(e["source"].upper())}</span></div>'
                  f'<div class="warn-meta"><span>Issued {e["issued_at"]:%H:%M} SAST</span><span>{icons.icon("trend")} {html.escape(we.probability_text(e))}</span>'
                  f'<span>{icons.icon("eye")} {we.acknowledgement_count(doc, e["key"])} acknowledgements</span><span>{icons.icon("clipboard")} {html.escape(review["status"])}</span></div></div>')
        right.button('Review', key='review_' + e['key'], on_click=_open, args=(e['key'],), type='primary', width='stretch')


def _details(official, events, doc, ops_store):
    if not events:
        st.info('No warnings have been issued yet, so there is nothing to review.')
        return
    keys = [e['key'] for e in events]
    if st.session_state.get('portal_selected') not in keys:
        st.session_state.portal_selected = keys[0]
    labels = {e['key']: f'{we.period_text(e)} · {e["source"]}' for e in events}
    key = st.selectbox('Warning', keys, key='portal_selected', format_func=labels.get)
    event = next(e for e in events if e['key'] == key)
    review = we.review_status(doc, key)
    a, b, c = st.columns(3)
    a.metric('Model estimate', we.probability_text(event).split(' (')[0])
    b.metric('Acknowledgements', we.acknowledgement_count(doc, key), help='Devices that opened the warning and pressed "I have read this warning". Anonymous; not a count of people safe or affected.')
    c.metric('Review status', review['status'])
    st.html(f'<div class="resident-guidance"><ul><li><b>Prediction period:</b> {html.escape(we.period_text(event))}</li>'
            f'<li><b>Issued:</b> {event["issued_at"]:%d %b %Y %H:%M:%S} SAST</li><li><b>Location:</b> {html.escape(event["location"])}</li>'
            f'<li><b>Severity:</b> {html.escape(event["severity"])}</li><li><b>Source:</b> {html.escape(event["source"])}'
            + (f' · <a href="{html.escape(event["record"])}" target="_blank">public ledger record</a>' if event.get('record') else '') + '</li>'
            + (f'<li><b>Last review:</b> {html.escape(review["status"])} by {html.escape(review["updated_by"])} at {html.escape(_when(review["updated_at"]))}</li>' if review['updated_by'] else '')
            + f'</ul><div class="resident-note">{html.escape(resident_view.MODEL_NOTE)}</div></div>')
    with st.form('review_form', clear_on_submit=True):
        status = st.selectbox('Review or response status', we.REVIEW_STATUSES, index=we.REVIEW_STATUSES.index(review['status']))
        note = st.text_area('Operational note (optional)', max_chars=we.MAX_NOTE,
                            placeholder='e.g. Ward councillors informed by phone; monitoring river levels.')
        submitted = st.form_submit_button('Record review', type='primary')
    if submitted:
        try:
            we.record_review(ops_store, key, official, status, note)
            st.session_state.portal_flash = 'Review recorded.'
            st.rerun()
        except (we.OperationsError, StoreError) as exc:
            st.error(str(exc))
    if st.session_state.get('portal_flash'):
        st.success(st.session_state.pop('portal_flash'))
    st.markdown('**Actions on this warning**')
    _actions_table(we.actions(doc, key), events)


def _when(value):
    return f'{we._time(value):%d %b %Y %H:%M} SAST' if value else '-'


def _actions_table(rows, events):
    periods = {e['key']: we.period_text(e) for e in events}
    if not rows:
        st.caption('No actions recorded yet.')
        return
    frame = pd.DataFrame([{'Recorded (SAST)': _when(r['at']), 'Official': r['official'], 'Warning': periods.get(r['warning'], r['warning']),
                           'Status set': r['status'] or '-', 'Note': r['note'] or '-'} for r in rows])
    st.html(dashboard_theme.table_html(frame, caption='Operational actions'))


def _geography(regional, regional_valid, current):
    st.caption(f'Current next-hour model estimate for Matatiele: {current["estimate"]}. The storm model covers one location '
               '(Matatiele); the map shows the ECMWF rainfall forecast at the surrounding grid points, not radar or observations.')
    if regional is None or regional.empty:
        st.info('The regional forecast is not available right now.')
        return
    frame = regional[['lat', 'lon', 'precipitation_mm']].copy()
    frame['detail'] = frame['precipitation_mm'].map(lambda v: f'{v:.1f} mm forecast rainfall')
    frame['name'] = 'ECMWF grid point'
    frame['radius'] = 1500 + frame['precipitation_mm'].clip(0, 40) * 400
    frame['color'] = frame['precipitation_mm'].map(lambda v: [237, 57, 75, 210] if v >= 10 else [250, 120, 43, 200] if v >= 3 else [10, 111, 214, 190] if v >= .1 else [120, 140, 160, 120])
    town = pd.DataFrame([{'lat': MATATIELE[0], 'lon': MATATIELE[1], 'name': 'Matatiele', 'detail': 'Location of the next-hour storm model'}])
    layers = [pdk.Layer('ScatterplotLayer', frame, get_position='[lon, lat]', get_radius='radius', get_fill_color='color', pickable=True),
              pdk.Layer('ScatterplotLayer', town, get_position='[lon, lat]', get_radius=2500, get_fill_color=[221, 45, 67, 240],
                        get_line_color=[255, 255, 255, 255], line_width_min_pixels=2, stroked=True, pickable=True),
              pdk.Layer('TextLayer', town, get_position='[lon, lat]', get_text='name', get_size=13, size_units=String('pixels'),
                        get_color=[255, 255, 255], background=True, get_background_color=[12, 32, 54, 235], get_pixel_offset=[0, -18])]
    st.pydeck_chart(pdk.Deck(map_style=None, initial_view_state=pdk.ViewState(latitude=MATATIELE[0], longitude=MATATIELE[1], zoom=7.6),
                             layers=layers, tooltip={'html': '<b>{name}</b><br/>{detail}'}), width='stretch', height=420)
    hour = f'hour ending {regional_valid:%d %b %H:%M} SAST' if regional_valid is not None else 'next hour'
    st.caption(f'Forecast rainfall for the {hour}. Grey: dry; blue: 0.1-3 mm; orange: 3-10 mm; red: 10 mm or more.')
    top = frame.sort_values('precipitation_mm', ascending=False).head(5)[['lat', 'lon', 'precipitation_mm']]
    st.html(dashboard_theme.table_html(top.rename(columns={'lat': 'Latitude', 'lon': 'Longitude', 'precipitation_mm': 'Forecast rainfall (mm)'}),
                                       caption='Grid points with the most forecast rain'))
    st.html(emergency_contacts.contacts_html('Emergency numbers residents see'))


def _history(events, doc):
    st.markdown('**All warnings**')
    if events:
        st.html(dashboard_theme.table_html(_summary(events, doc), caption='All warnings'))
    else:
        st.info('No warnings have been issued yet.')
    st.markdown('**All operational actions**')
    rows = we.actions(doc)
    _actions_table(rows, events)
    if rows:
        csv = pd.DataFrame(rows).to_csv(index=False).encode('utf-8')
        st.download_button('Download actions (CSV)', csv, 'operational_actions.csv', 'text/csv')
