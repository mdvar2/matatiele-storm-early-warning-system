"""Dashboard pages for SMS subscriptions, public warning history and administration.

Rendering only: all decisions live in subscriptions.py, subscriber_alerts.py and
subscriber_store.py. Phone numbers appear only in the form a resident is typing and,
for administrators, masked. Session state holds UI progress only; data is persisted
in the subscriber store.
"""
import html

import pandas as pd
import streamlit as st

import subscriber_alerts as alerts
import subscriptions as subs
from subscriber_store import StoreError, open_store

LEDGER_REPO = 'mdvar2/matatiele-storm-early-warning-system'
DEV_BANNER = ('background:#7a4b00;color:#ffffff;border:3px solid #ffd23f;border-radius:12px;padding:12px 16px;'
              'font-weight:700;font-size:14px;line-height:1.5')


def _store(getter):
    try:
        return open_store(getter), None
    except StoreError as exc:
        return None, str(exc)


def _gateway(getter):
    try:
        return subs.gateway_from_config(getter), None
    except StoreError as exc:
        return None, str(exc)


def dev_banner():
    st.html(f'<div style="{DEV_BANNER}">DEVELOPMENT MODE: SMS messages are written to a local outbox on this computer '
            'and are NOT sent to any phone.</div>')


def _outbox_list(rows):
    """Readable list of development-outbox messages (masked numbers; local development only)."""
    if not rows:
        st.caption('No messages yet.')
        return
    items = ''.join(f'<li><b>{html.escape(r["to"])}</b> &middot; {html.escape(r["kind"])} &middot; {html.escape(r["at"])}<br>'
                    f'{html.escape(r["body"])}</li>' for r in rows)
    st.html(f'<div class="resident-guidance"><ul>{items}</ul></div>')


def _status_card(view):
    labels = {'active': ('Active', 'tone-green', 'You will receive SMS storm warnings for this area.'),
              'pending': ('Waiting for verification', 'tone-amber', 'Enter the code from the SMS to activate warnings.'),
              'unsubscribed': ('Unsubscribed', 'tone-off', 'You will not receive storm warnings. Your number has been removed.')}
    title, tone, text = labels.get(view['status'], (view['status'], 'tone-gray', ''))
    stopped = view['status'] == 'unsubscribed' and view.get('unsubscribed_at')
    when = view['unsubscribed_at'] if stopped else view.get('since')
    since = pd.Timestamp(when).tz_convert('Africa/Johannesburg').strftime('%d %b %Y %H:%M SAST') if when else 'Unknown'
    st.html(f'<div class="resident-card {tone}"><div class="resident-head">{html.escape(title)}</div>'
            f'<div class="resident-text">{html.escape(text)}</div><div class="resident-facts">'
            f'<span><b>Number</b>{html.escape(view["number"])}</span><span><b>Area</b>{html.escape(view["area"])}</span>'
            f'<span><b>{"Unsubscribed on" if stopped else "Since"}</b>{html.escape(since)}</span></div></div>')


def _flow(prefix):
    state = st.session_state
    state.setdefault(prefix + 'stage', 'enter')
    state.setdefault(prefix + 'phone', '')
    return state


def render_sms_alerts(getter):
    st.html('<div class="section-title">SMS storm warnings <small>Free text messages when the model warns of a storm in Matatiele</small></div>')
    mode = subs.delivery_mode(getter)
    if mode == 'disabled':
        st.info('SMS registration is not open yet: the project team has not yet configured the SMS service for public sign-up. '
                'Storm warnings remain available on this dashboard, and official warnings are issued by the South African Weather Service.')
        return
    store, store_error = _store(getter)
    gateway, gateway_error = _gateway(getter)
    if store is None or gateway is None:
        st.error('SMS registration is temporarily unavailable (service configuration incomplete). Please try again later.')
        return
    if mode == 'outbox':
        dev_banner()
    subscribe_tab, manage_tab = st.tabs(['Subscribe', 'Manage my subscription'])
    with subscribe_tab:
        _subscribe(store, gateway)
    with manage_tab:
        _manage(store, gateway)
    if mode == 'outbox':
        with st.expander('Development outbox (messages NOT sent)', expanded=True):
            _outbox_list(gateway.recent(10))


def _subscribe(store, gateway):
    state = _flow('sub_')
    if state.sub_stage == 'enter':
        with st.form('subscribe_form'):
            phone = st.text_input('South African mobile number', placeholder='e.g. 082 123 4567', max_chars=20)
            st.selectbox('Warning area', list(subs.AREAS.values()), help='Warnings are currently produced for Matatiele only.')
            consent = st.checkbox(subs.CONSENT_TEXT)
            sent = st.form_submit_button('Send verification code', type='primary')
        if sent:
            try:
                st.success(subs.request_code(store, gateway, phone, 'subscribe', consent=consent))
                state.sub_phone, state.sub_stage = phone, 'code'
                st.rerun()
            except subs.SubscriptionError as exc:
                st.error(str(exc))
    elif state.sub_stage == 'code':
        masked = subs.mask_phone(subs.normalise_sa_mobile(state.sub_phone))
        st.info(f'We sent a 6-digit code to {masked}. Enter it below to activate warnings.')
        with st.form('subscribe_code_form'):
            code = st.text_input('Verification code', max_chars=6, placeholder='123456')
            verify = st.form_submit_button('Verify and activate', type='primary')
        if verify:
            try:
                view = subs.verify_code(store, state.sub_phone, code, 'subscribe')
                state.sub_stage, state.sub_view = 'done', view
                st.rerun()
            except subs.SubscriptionError as exc:
                st.error(str(exc))
        left, right = st.columns(2)
        if left.button('Send a new code', key='sub_resend'):
            try:
                st.success(subs.request_code(store, gateway, state.sub_phone, 'subscribe', consent=True))
            except subs.SubscriptionError as exc:
                st.error(str(exc))
        if right.button('Use a different number', key='sub_restart'):
            state.sub_stage, state.sub_phone = 'enter', ''
            st.rerun()
    else:
        st.success('Your subscription is active. You will receive an SMS if the model warns of a storm in Matatiele.')
        _status_card(state.sub_view)
        st.caption('You can unsubscribe at any time under "Manage my subscription" or by replying STOP to any warning.')
        if st.button('Register another number', key='sub_again'):
            state.sub_stage, state.sub_phone = 'enter', ''
            st.rerun()


def _manage(store, gateway):
    state = _flow('man_')
    if state.man_stage == 'enter':
        st.caption('To protect your privacy we first confirm that you own the number with a one-time code.')
        with st.form('manage_form'):
            phone = st.text_input('Your registered mobile number', placeholder='e.g. 082 123 4567', max_chars=20)
            sent = st.form_submit_button('Send code')
        if sent:
            try:
                st.success(subs.request_code(store, gateway, phone, 'manage'))
                state.man_phone, state.man_stage = phone, 'code'
                st.rerun()
            except subs.SubscriptionError as exc:
                st.error(str(exc))
    elif state.man_stage == 'code':
        st.info('If this number is registered, we sent it a 6-digit code.')
        with st.form('manage_code_form'):
            code = st.text_input('Verification code', max_chars=6, placeholder='123456')
            verify = st.form_submit_button('Confirm', type='primary')
        if verify:
            try:
                subs.verify_code(store, state.man_phone, code, 'manage')
                state.man_stage = 'verified'
                st.rerun()
            except subs.SubscriptionError as exc:
                st.error(str(exc))
        if st.button('Start again', key='man_restart'):
            state.man_stage, state.man_phone = 'enter', ''
            st.rerun()
    else:
        view = subs.subscription_status(store, state.man_phone)
        if view is None:
            st.warning('No subscription was found for this number.')
        else:
            _status_card(view)
            if view['status'] != 'unsubscribed':
                confirm = st.checkbox('I want to stop receiving SMS storm warnings', key='man_confirm')
                if st.button('Unsubscribe', key='man_unsubscribe', disabled=not confirm):
                    subs.unsubscribe(store, state.man_phone)
                    st.success('You have been unsubscribed. Your number has been removed from the warning list.')
                    st.rerun()
        if st.button('Finish', key='man_finish'):
            state.man_stage, state.man_phone = 'enter', ''
            st.rerun()


@st.cache_data(ttl=600, show_spinner=False)
def _ledger(repo):
    return alerts.ledger_warnings(repo)


def render_warning_history():
    st.html('<div class="section-title">Storm warnings issued <small>Genuine warnings from the automatic hourly checks</small></div>')
    try:
        warnings = _ledger(LEDGER_REPO)
    except Exception:
        st.info('The warning history is temporarily unavailable (the public record could not be reached). Please try again later.')
        return
    if not warnings:
        st.info('No storm warnings have been issued by this system yet. Hours below the 35% warning level do not create warnings.')
    else:
        frame = pd.DataFrame(warnings)
        end = pd.to_datetime(frame['forecast_hour_utc'], utc=True).dt.tz_convert('Africa/Johannesburg')
        table = pd.DataFrame({'Warning period (SAST)': (end - pd.Timedelta(hours=1)).dt.strftime('%d %b %Y %H:%M') + ' - ' + end.dt.strftime('%H:%M'),
                              'Issued (SAST)': pd.to_datetime(frame['issued_at_utc'], utc=True).dt.tz_convert('Africa/Johannesburg').dt.strftime('%d %b %Y %H:%M'),
                              'Public record': frame['record']})
        st.dataframe(table, hide_index=True, width='stretch', column_config={'Public record': st.column_config.LinkColumn(display_text='View')})
    st.caption('Each warning is recorded publicly when the model reaches the 35% warning level for the next hour. '
               'Who received an SMS is never published. Connectivity tests are not listed.')


def render_admin(getter, health):
    st.html('<div class="section-title">Administration <small>Subscriptions, warning delivery and system health</small></div>')
    mode = subs.delivery_mode(getter)
    store, store_error = _store(getter)
    gateway, gateway_error = _gateway(getter)
    if mode == 'outbox':
        dev_banner()
    a, b, c, d = st.columns(4)
    a.metric('SMS delivery mode', {'disabled': 'Disabled', 'outbox': 'Dev outbox', 'twilio': 'Twilio (live)'}[mode])
    b.metric('Subscriber store', store.blob.describe() if store else 'Not configured')
    c.metric('Encryption', 'Configured' if store else 'Not configured')
    d.metric('Prediction data', health.get('Prediction data', 'Unknown'))
    if store is None:
        st.warning(f'Subscriber store unavailable: {store_error}')
        _health(health)
        return
    overview = alerts.admin_overview(store.snapshot())
    counts = overview['subscribers']
    a, b, c, d = st.columns(4)
    a.metric('Active subscribers', counts.get('active', 0))
    b.metric('Awaiting verification', counts.get('pending', 0))
    c.metric('Unsubscribed', counts.get('unsubscribed', 0))
    d.metric('Warnings sent to subscribers', len(overview['alerts']))
    st.markdown('**Warning activity**')
    if overview['alerts']:
        st.dataframe(pd.DataFrame(overview['alerts'])[['key', 'created_at', 'forecast_period', 'probability']], hide_index=True, width='stretch')
    else:
        st.caption('No warnings have been delivered to subscribers yet.')
    st.markdown('**SMS deliveries** (numbers masked)')
    if overview['deliveries']:
        frame = pd.DataFrame(overview['deliveries'])
        cols = [c for c in ['alert', 'masked', 'status', 'provider_status', 'attempts', 'error', 'updated_at'] if c in frame]
        st.dataframe(frame[cols], hide_index=True, width='stretch')
        st.caption('Status: submitted = accepted by the provider; delivered = confirmed by the provider; failed = definitive failure; '
                   'uncertain/pending = outcome unknown, never resent automatically (check the provider console).')
    else:
        st.caption('No SMS deliveries recorded.')
    left, right = st.columns(2)
    with left:
        if st.button('Refresh delivery statuses', key='admin_refresh_status', disabled=gateway is None):
            st.success(f'{alerts.refresh_delivery_statuses(store, gateway)} delivery status(es) updated.')
    with right:
        failed = [d for d in overview['deliveries'] if d['status'] == 'failed' and d.get('error') != 'recipient_opted_out']
        if failed:
            choice = st.selectbox('Definitively failed deliveries', [d['key'] for d in failed],
                                  format_func=lambda k: next(f"{d['masked']} · {d['alert'][-25:]} · {d.get('error', '')}" for d in failed if d['key'] == k))
            if st.button('Retry selected delivery', key='admin_retry', disabled=gateway is None):
                try:
                    st.success(f'Retry outcome: {alerts.retry_failed(store, gateway, choice)}')
                except subs.SubscriptionError as exc:
                    st.error(str(exc))
        else:
            st.caption('No definitively failed deliveries to retry.')
    _health(health)
    if mode == 'outbox':
        with st.expander('Development outbox (messages NOT sent)'):
            _outbox_list(gateway.recent(20) if gateway else [])


@st.cache_data(ttl=300, show_spinner=False)
def _recent_runs(repo):
    import requests
    response = requests.get(f'https://api.github.com/repos/{repo}/actions/runs', params={'per_page': 8},
                            headers={'Accept': 'application/vnd.github+json'}, timeout=15)
    response.raise_for_status()
    return [{'run': r['run_number'], 'trigger': r['event'], 'result': r['conclusion'] or r['status'], 'started (UTC)': r['run_started_at'],
             'workflow': r['path'].rsplit('/', 1)[-1]} for r in response.json().get('workflow_runs', [])]


def _health(health):
    st.markdown('**System health**')
    st.dataframe(pd.DataFrame([{'Check': k, 'Status': v} for k, v in health.items()]), hide_index=True, width='stretch')
    try:
        st.dataframe(pd.DataFrame(_recent_runs(LEDGER_REPO)), hide_index=True, width='stretch')
        st.caption('Recent scheduled checks (public GitHub Actions record).')
    except Exception:
        st.caption('Recent GitHub Actions runs could not be retrieved.')
