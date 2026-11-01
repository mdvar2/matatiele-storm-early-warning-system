"""Resident-facing wording, safety guidance and on-screen warning simulation.

Pure functions only: no Streamlit, no network, no file writes and no SMS sending.
The dashboard renders what these functions return. The risk bands mirror the
dashboard's existing `risk()` function, and the 0.35 warning threshold is unchanged.

The simulation is display-only. `sms_preview` formats the text the scheduled
worker would send (via the same message builder), but nothing here can submit it.
"""
import base64
import html
import math

import emergency_contacts
import icons

from sms_alert import _build_warning_message

THRESHOLD = 0.35
SIMULATED_PROBABILITY = 0.60
COVERAGE = ('Matatiele town and its immediate surroundings (one model location). '
            'Nearby towns and villages do not receive separate storm-risk estimates.')
MODEL_NOTE = ('This is an estimate from a research computer model (machine learning) that uses '
              'weather forecasts. It has not been independently validated as a storm probability '
              'and it is not an official weather warning.')
OFFICIAL_NOTE = ('General precautionary advice, not an official weather warning. Official warnings '
                 'for South Africa are issued by the South African Weather Service (SAWS, '
                 'www.weathersa.co.za). In an emergency, contact your local emergency services.')
SIMULATION_LABEL = 'SIMULATION - NOT A REAL FORECAST OR WARNING'

HEADLINES = {
    'LOW': 'Low storm risk (model estimate)',
    'ELEVATED': 'Slightly raised storm risk (model estimate)',
    'MODERATE': 'Raised storm risk: stay alert (model estimate)',
    'WARNING': 'Storm warning (model): take precautions now',
    'UNAVAILABLE': 'Storm risk is not available right now',
}
EXPLANATIONS = {
    'LOW': ('The model does not expect a storm in Matatiele during this hour. This is not a '
            'guarantee: storms can still develop. Watch the sky and follow official SAWS warnings.'),
    'ELEVATED': ('The model sees a slightly higher chance of a storm than usual. A storm is still '
                 'unlikely, but conditions can change quickly. Know where you would take shelter.'),
    'MODERATE': ('The model sees a raised chance of a storm in this hour. Get ready: finish outdoor '
                 'work early, and plan safe shelter for people and animals.'),
    'WARNING': ('The model estimates a high chance of a storm in this hour. Take precautions now '
                'and follow the safety advice below. Check SAWS for official warnings.'),
    'UNAVAILABLE': ('There is no current model estimate. Do not assume it is safe. Watch the sky and '
                    'follow official SAWS warnings.'),
}
STALE_HEADLINE = 'Storm risk information is out of date'
STALE_EXPLANATION = ('The latest update could not be completed, so this is not a current estimate. '
                     'Do not rely on it. Watch the sky and follow official SAWS warnings.')
TONES = {'LOW': 'green', 'ELEVATED': 'amber', 'MODERATE': 'amber', 'WARNING': 'red', 'UNAVAILABLE': 'gray'}

# Topic -> advice. Practical, general precautions; not location- or event-specific instructions.
TOPICS = ('Lightning', 'Flooding', 'Roads', 'Rivers', 'Livestock')
ACT_NOW = {
    'Lightning': ('If you hear thunder, lightning is close enough to strike. Go inside a solid building '
                  'or a closed car. Stay away from open fields, hilltops, lone trees, wire fences and '
                  'water. Wait 30 minutes after the last thunder before going back outside.'),
    'Flooding': ('Never walk, drive or let children play in flood water. Fast water only ankle-deep '
                 'can knock a person over. Move to higher ground if water is rising.'),
    'Roads': ('Do not cross flooded roads, low bridges or causeways: turn around. If you must travel, '
              'drive slowly with headlights on, or wait until the storm has passed.'),
    'Rivers': ('Stay away from rivers, streams and dongas: they can rise suddenly, even if it is not '
               'raining where you are. Do not cross rivers on foot.'),
    'Livestock': ('Before the storm, move animals away from rivers, low-lying land, lone trees and wire '
                  'fences if it is safe. Once lightning starts, do not go out to move animals.'),
}
PREPARE = {
    'Lightning': 'Know which solid building you would go to if you hear thunder.',
    'Flooding': 'Know the higher ground near your home, and keep children away from streams.',
    'Roads': 'Plan travel early. Avoid roads that flood or cross low bridges.',
    'Rivers': 'Avoid crossing rivers later in the day; water can rise quickly after storms upstream.',
    'Livestock': 'Plan where animals can shelter away from rivers, lone trees and wire fences.',
}
ACTIONS = {
    'WARNING': 'Act now',
    'MODERATE': 'Get ready',
    'ELEVATED': 'Be prepared',
    'LOW': 'Be prepared',
    'UNAVAILABLE': 'If you see signs of a storm',
}


def classify(probability, threshold=THRESHOLD):
    """Same bands as the dashboard's risk(): <10% LOW, <20% ELEVATED, <threshold MODERATE."""
    try:
        p = float(probability)
    except (TypeError, ValueError):
        return 'UNAVAILABLE'
    if not math.isfinite(p) or not 0 <= p <= 1:
        return 'UNAVAILABLE'
    if p >= threshold:
        return 'WARNING'
    if p >= .20:
        return 'MODERATE'
    if p >= .10:
        return 'ELEVATED'
    return 'LOW'


def guidance(level):
    """Safety guidance: act-now advice for WARNING (and when no current estimate exists), else preparation."""
    level = level if level in ACTIONS else 'UNAVAILABLE'
    advice = ACT_NOW if level in ('WARNING', 'UNAVAILABLE') else PREPARE
    return {'level': level, 'action': ACTIONS[level],
            'items': [(topic, advice[topic]) for topic in TOPICS], 'note': OFFICIAL_NOTE}


def _clock(value):
    return value.strftime('%H:%M') if value is not None else None


def resident_status(probability, period_start, period_end, updated, stale, simulated=False):
    """Plain-language status for the resident card. Times are timezone-aware SAST values or None."""
    probability = SIMULATED_PROBABILITY if simulated else probability
    level = classify(probability)
    if simulated:
        stale = False
    if stale or level == 'UNAVAILABLE':
        headline = STALE_HEADLINE if stale else HEADLINES['UNAVAILABLE']
        explanation = STALE_EXPLANATION if stale else EXPLANATIONS['UNAVAILABLE']
        guidance_level = 'UNAVAILABLE'
        tone = 'gray'
    else:
        headline, explanation, guidance_level, tone = HEADLINES[level], EXPLANATIONS[level], level, TONES[level]
    if period_start is not None and period_end is not None:
        period = f'{period_start:%d %b} {_clock(period_start)} - {_clock(period_end)} (SAST)'
    else:
        period = 'Prediction period unavailable'
    usable = level != 'UNAVAILABLE'
    if simulated:
        estimate = f'Simulated model output: {SIMULATED_PROBABILITY:.0%}'
    elif usable:
        estimate = f'Last risk score: {score_text(probability)} (out of date)' if stale else f'Model risk score: {score_text(probability)}'
    else:
        estimate = 'No model estimate'
    if simulated:
        decision = 'Simulated: at or above 35%, warning condition shown on screen only. No warning record is created.'
    elif stale:
        decision = 'No warning decision: the information is out of date, and warnings are never issued from out-of-date data.'
    elif level == 'UNAVAILABLE':
        decision = 'No warning decision: there is no current model estimate.'
    elif level == 'WARNING':
        decision = 'At or above the 35% warning threshold: warning condition met.'
    else:
        decision = 'Below the 35% warning threshold: no warning.'
    if stale:
        freshness = f'OUT OF DATE: last known information from {updated:%d %b %Y %H:%M} SAST' if updated is not None else 'OUT OF DATE: update time unknown'
    else:
        freshness = 'Current' if updated is not None else 'Update time unknown'
    return {'level': level, 'guidance_level': guidance_level, 'headline': headline, 'decision': decision, 'freshness': freshness,
            'explanation': explanation, 'period': period,
            'updated': f'{updated:%d %b %Y %H:%M} SAST' if updated is not None else 'Unknown',
            'coverage': COVERAGE, 'estimate': estimate, 'model_note': MODEL_NOTE, 'tone': tone,
            'stale': bool(stale), 'simulated': bool(simulated),
            'label': SIMULATION_LABEL if simulated else ''}


def sms_preview(prediction_for, probability=SIMULATED_PROBABILITY):
    """Text the worker's message builder would produce. Display only: never submitted."""
    try:
        return _build_warning_message('Matatiele', prediction_for, probability, THRESHOLD, 0.0, 0.0, 0.0, 0.0)
    except (ValueError, TypeError):
        return 'Preview unavailable: no valid forecast period.'


def text_only_page(status, advice):
    """Minimal Markdown for low-data access: status, period, timestamp, guidance and emergency numbers."""
    lines = []
    if status['simulated']:
        lines += [f"**{status['label']}**", '']
    lines += [f"## {status['headline']}", '', status['explanation'], '',
              f"- **Prediction period:** {status['period']}",
              f"- **{status['estimate']}** (warning threshold: {THRESHOLD:.0%})",
              f"- **Warning decision:** {status['decision']}",
              f"- **Last update:** {status['updated']}",
              f"- **Information status:** {status['freshness']}",
              f"- **Area:** {status['coverage']}", '',
              f"_{status['model_note']}_", '',
              f"### Safety advice: {advice['action']}"]
    lines += [f"- **{topic}:** {text}" for topic, text in advice['items']]
    lines += ['', '### Emergency numbers']
    lines += [f'- {line}' for line in emergency_contacts.text_lines()]
    lines += ['', f'_{emergency_contacts.NOTE} Calls need mobile network coverage._', '', f"_{advice['note']}_"]
    return '\n'.join(lines)


def card_html(status):
    """Escaped HTML for the resident status card (styling classes live in the dashboard CSS)."""
    e = lambda value: html.escape(str(value))  # noqa: E731
    banner = f'<div class="resident-sim">{e(status["label"])}</div>' if status['simulated'] else ''
    return (f'<div class="resident-card tone-{e(status["tone"])}">{banner}'
            f'<div class="resident-head">{e(status["headline"])}</div>'
            f'<div class="resident-text">{e(status["explanation"])}</div>'
            f'<div class="resident-facts"><span><b>Prediction period</b>{e(status["period"])}</span>'
            f'<span><b>Estimate</b>{e(status["estimate"])}</span>'
            f'<span><b>Last update</b>{e(status["updated"])}</span>'
            f'<span><b>Area</b>{e(status["coverage"])}</span></div>'
            f'<div class="resident-note">{e(status["model_note"])}</div></div>')


def guidance_html(advice):
    e = lambda value: html.escape(str(value))  # noqa: E731
    items = ''.join(f'<li><b>{e(topic)}:</b> {e(text)}</li>' for topic, text in advice['items'])
    return (f'<div class="resident-guidance"><div class="resident-action">{e(advice["action"])}</div>'
            f'<ul>{items}</ul><div class="resident-note">{e(advice["note"])}</div></div>')


# Short labels for the homepage action strip; the full advice above stays one tap away.
TOPIC_ICONS = {'Lightning': 'zap', 'Flooding': 'droplets', 'Roads': 'car', 'Rivers': 'waves', 'Livestock': 'fence'}
SHORT_ACT_NOW = {'Lightning': 'Go indoors', 'Flooding': 'Keep out of flood water', 'Roads': 'Turn around at flooded roads',
                 'Rivers': 'Stay away from rivers', 'Livestock': 'Do not go out for animals'}
SHORT_PREPARE = {'Lightning': 'Know your shelter', 'Flooding': 'Know your high ground', 'Roads': 'Plan travel early',
                 'Rivers': 'Cross rivers early', 'Livestock': 'Plan animal shelter'}
HERO_NOTE = 'Model-estimated storm risk from a research prototype · not a guarantee · not an official SAWS warning'
THRESHOLD_TEXT = ("Warnings are triggered when the model's storm-risk estimate reaches or exceeds 35%. This threshold is intended to "
                  'support early identification of potentially hazardous conditions. Lower thresholds may detect more events but can '
                  'also increase false alarms.')
THRESHOLD_METHOD = ("How it was set: the project's threshold-evaluation step compared thresholds from 10% to 60% on the most recent part "
                    'of the historical ERA5 data, using the F1-score (a balance between missed storms and false alarms). Thresholds from '
                    '30% to 40% scored almost the same. 35% is the setting in use; because the comparison used that same period, it is a '
                    'practical working setting, not an independently validated optimum.')


GAUGE_COLOURS = {'green': '#36a46b', 'amber': '#d98b16', 'red': '#d93449', 'gray': '#8a9bb0'}
RISK_BADGES = {'LOW': 'LOW RISK', 'ELEVATED': 'ELEVATED RISK', 'MODERATE': 'MODERATE RISK', 'WARNING': 'HIGH RISK', 'UNAVAILABLE': 'NO SCORE'}
SCORE_NOTE = 'Model risk score \u2014 not a calibrated probability'


def score_text(probability):
    """The model score as shown to residents: whole percent, with '<1%' for small non-zero scores."""
    try:
        p = float(probability)
    except (TypeError, ValueError):
        return 'n/a'
    if not math.isfinite(p) or not 0 <= p <= 1:
        return 'n/a'
    return '<1%' if 0 < p < 0.005 else f'{p:.0%}'


def gauge_svg(probability, tone):
    """The 35% marker and its label over the gauge (the arc itself is CSS, see gauge_html); value in the alt text."""
    try:
        p = min(max(float(probability), 0.0), 1.0)
        usable = math.isfinite(p)
    except (TypeError, ValueError):
        p, usable = 0.0, False
    angle = math.pi * (1 - THRESHOLD)
    cx, cy, r = 110, 112, 88
    point = lambda radius: (cx + radius * math.cos(angle), cy - radius * math.sin(angle))  # noqa: E731
    (x1, y1), (x2, y2), (tx, ty) = point(r - 17), point(r + 17), point(r + 27)
    label = f'Model risk score {score_text(p)}, warning threshold 35%' if usable else 'No model risk score'
    svg = ('<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 220 124" font-family="Segoe UI, Arial, sans-serif">'
           f'<line x1="{x1:.1f}" y1="{y1:.1f}" x2="{x2:.1f}" y2="{y2:.1f}" stroke="#d93449" stroke-width="4" stroke-linecap="round"/>'
           f'<text x="{tx:.1f}" y="{ty:.1f}" font-size="13" font-weight="700" fill="#d93449" text-anchor="middle">35%</text></svg>')
    # An image, because the page's HTML sanitiser removes inline SVG; the value is in the alt text.
    return f'<img class="risk-gauge-img" src="data:image/svg+xml;base64,{base64.b64encode(svg.encode()).decode()}" alt="{label}">'


def gauge_html(probability, tone, previous=None):
    """Track, fill and marker. The fill equals the genuine score; it sweeps from `previous` only when the score changed."""
    try:
        p = min(max(float(probability), 0.0), 1.0)
        p = p if math.isfinite(p) else 0.0
    except (TypeError, ValueError):
        p = 0.0
    sweep = previous is not None and abs(float(previous) - p) >= 0.005
    start = min(max(float(previous), 0.0), 1.0) if sweep else p
    colour = GAUGE_COLOURS.get(tone, GAUGE_COLOURS['gray'])
    return (f'<div class="risk-track"></div><div class="risk-arc{" animate" if sweep else ""}" '
            f'style="--to:{p:.4f};--from:{start:.4f};--arc:{colour}"></div>{gauge_svg(probability, tone)}')


def warning_state(status, record):
    """Warning-decision badge (title, tone, icon, detail). A threshold crossing is not reported as a warning until the
    public warning record holds one. record: {'state': 'genuine'|'dev'|'none'|'unknown', 'issued': 'HH:MM' or None}."""
    state = record.get('state')
    if status['simulated']:
        return 'SIMULATED WARNING', 'amber', 'alert', 'On screen only: no warning record is created.'
    if state == 'genuine':
        issued = f' at {record["issued"]} SAST' if record.get('issued') else ''
        return 'WARNING TRIGGERED', 'red', 'siren', f'Warning record created{issued} for this period.'
    if status['stale']:
        return 'NO DECISION', 'gray', 'help-circle', 'Data out of date: warnings are never issued from out-of-date data.'
    if status['level'] == 'UNAVAILABLE':
        return 'NO DECISION', 'gray', 'help-circle', 'No current model risk score.'
    if status['level'] == 'WARNING':
        detail = {'unknown': 'Threshold reached; the warning record could not be checked.',
                  'dev': 'Threshold reached; only a development test record exists.'}.get(
            state, 'Threshold reached; no warning record yet (the hourly checker creates warnings).')
        return 'THRESHOLD REACHED', 'amber', 'alert', detail
    detail = 'Score is below the warning threshold.'
    if state == 'unknown':
        detail += ' Warning record could not be checked.'
    return 'NO WARNING TRIGGERED', 'green', 'check-circle', detail


def summary_html(status, probability, weather, record, just_updated=False, previous_score=None):
    """Homepage row 1: forecast weather, model storm-risk gauge, prediction period and warning decision.

    weather: display strings (temperature, rain, wind, gust, source) plus an 'icon' <img>; record: see warning_state.
    Every value comes from these inputs.
    """
    e = lambda value: html.escape(str(value))  # noqa: E731
    score = SIMULATED_PROBABILITY if status['simulated'] else probability
    sim = f'<div class="resident-sim">{e(status["label"])}</div>' if status['simulated'] else ''
    tone = status['tone']
    badge = 'OUT OF DATE' if status['stale'] else RISK_BADGES[status['level']]
    value = score_text(score) if status['level'] != 'UNAVAILABLE' else 'n/a'
    risk_card = (f'<div class="summary-card risk-summary tone-{e(tone)}">{sim}<div class="sc-title">{icons.icon("gauge")} Model-estimated storm risk</div><span class="sc-sub">(Next hour, Random Forest)</span>'
                 f'<div class="risk-dial">{gauge_html(score, tone, None if status["simulated"] else previous_score)}<div class="risk-value">{e(value)}</div></div>'
                 f'<div class="risk-badge-row"><span class="risk-pill tone-{e(tone)}">{e(badge)}</span></div>'
                 f'<div class="risk-note"><b>{THRESHOLD:.0%} warning threshold</b></div>'
                 f'<div class="risk-meta"><span>{icons.icon("clock")} {e(status["period"])} · Updated {e(status["updated"].split()[-2] if status["updated"] != "Unknown" else "unknown")}</span></div>'
                 f'<div class="risk-caveat">{e(status["estimate"]) + " · " if status["stale"] or status["simulated"] else ""}{e(SCORE_NOTE)}; not a guarantee.</div></div>')
    title, decision_tone, icon, detail = warning_state(status, record)
    decision_card = (f'<div class="summary-card decision-summary"><div class="sc-title">{icons.icon("scale")} Warning decision</div><span class="sc-sub">(35% threshold)</span>'
                     f'<div class="decision-badge tone-{decision_tone}">{icons.icon(icon)}<b>{e(title)}</b></div>'
                     f'<div class="sc-line">{e(detail)}</div>'
                     f'<div class="decision-foot"><b>Warning threshold: {THRESHOLD:.0%}</b>'
                     f'<details class="threshold-info"><summary>{icons.icon("info")} Why 35%?</summary><p>{e(THRESHOLD_TEXT)}</p>'
                     '<p>More detail: menu, then Risk Analysis.</p></details></div>'
                     '<div class="sc-foot">Research system decision, not an official SAWS warning.</div></div>')
    weather_card = (f'<div class="summary-card wx-summary"><div class="sc-title">{icons.icon("cloud")} Weather forecast</div><span class="sc-sub">(Matatiele, ECMWF)</span>'
                    f'<div class="wx-now"><div class="sc-value">{e(weather["temperature"])}</div>{weather["icon"]}</div>'
                    '<div class="wx-stats">'
                    f'<span>{icons.icon("cloud-rain", "Rain")}<b>{e(weather["rain"])}</b><small>Rain</small></span>'
                    f'<span>{icons.icon("wind", "Wind")}<b>{e(weather["wind"])}</b><small>Wind</small></span>'
                    f'<span>{icons.icon("wind", "Gusts")}<b>{e(weather["gust"])}</b><small>Gusts</small></span></div>'
                    f'<div class="sc-foot">{e(weather["source"])}</div></div>')
    fresh = ('<span class="fresh-badge stale">Out of date</span>' if status['stale'] else '<span class="fresh-badge">Fresh data</span>')
    period_card = (f'<div class="summary-card period-summary"><div class="sc-title">{icons.icon("calendar")} Prediction period</div><span class="sc-sub">(Target hour)</span>'
                   f'<div class="period-row">{icons.icon("calendar")}<span><small>Target hour</small><b>{e(status["period"])}</b></span></div>'
                   f'<div class="period-row">{icons.icon("clock")}<span><small>Model updated</small><b>{e(status["updated"])}</b></span></div>'
                   f'{fresh}</div>')
    return f'<div class="summary-grid{" just-updated" if just_updated else ""}">{risk_card}{decision_card}{period_card}{weather_card}</div>'


OUTLOOK_NOTE = ('Hours 2 to 12 ahead: the same model applied to the ECMWF forecast for those hours. It was evaluated one hour '
                'ahead only, so these scores are unvalidated and less certain further ahead. Model risk scores, not calibrated '
                'probabilities. Hour 1 is the estimate above.')


def outlook_badge_html(state, first_hour=None, score=None):
    """state: 'alert' (an hour 2-12 ahead at or above 35%), 'clear', or 'unavailable'."""
    e = lambda value: html.escape(str(value))  # noqa: E731
    if state == 'alert':
        return (f'<div class="decision-badge tone-amber">{icons.icon("alert")}<b>EARLY ALERT: raised storm risk from about '
                f'{e(first_hour)} SAST ({e(score)})</b></div>')
    if state == 'clear':
        return f'<div class="decision-badge tone-green">{icons.icon("check-circle")}<b>No raised storm risk in the next 12 hours</b></div>'
    return (f'<div class="decision-badge tone-gray">{icons.icon("help-circle")}<b>Outlook unavailable: no current forecast</b></div>')


def communication_html(communication):
    """Warning-communication tiles: (label, state, tone) rows derived from configuration."""
    e = lambda value: html.escape(str(value))  # noqa: E731
    comm_icons = {'Dashboard alerts': 'bell', 'SMS simulation': 'message', 'Public SMS delivery': 'smartphone'}
    tiles = ''.join(f'<div class="comm-tile">{icons.icon(comm_icons.get(label, "info"))}<span>{e(label)}</span>'
                    f'<span class="sc-state {e(state_tone)}">{e(state)}</span></div>' for label, state, state_tone in communication)
    return (f'<div class="summary-card comms-summary"><div class="sc-title">{icons.icon("message")} Warning communication</div>'
            f'<div class="comm-tiles">{tiles}</div><div class="sc-foot">Details: Alerts, then SMS alerts.</div></div>')


def variables_html(tiles, caption):
    """Key weather variables the model uses: (icon, label, value) tiles from the ECMWF model input."""
    e = lambda value: html.escape(str(value))  # noqa: E731
    cells = ''.join(f'<div class="var-tile">{icons.icon(icon)}<span><small>{e(label)}</small><b>{e(value)}</b></span></div>'
                    for icon, label, value in tiles)
    return (f'<div class="summary-card vars-summary"><div class="sc-title">{icons.icon("thermometer")} Key weather variables</div>'
            f'<div class="var-grid">{cells}</div><div class="sc-foot">{e(caption)}</div></div>')


LOG_TONES = {'Warning': 'red', 'Threshold reached': 'amber', 'No warning': 'green'}


def prediction_log_html(rows, worker_log_reachable=True):
    """Recent outputs of the trained model: (target hour, input hour, score text, decision, source) rows, newest first.

    'Warning' is used only where the public record holds a genuine warning for that hour. Source: the hourly
    worker's public run log, or this dashboard's own saved runs.
    """
    e = lambda value: html.escape(str(value))  # noqa: E731
    if not rows:
        body = '<tr><td colspan="5">No saved predictions yet.</td></tr>'
    else:
        body = ''.join(f'<tr><td>{e(target)}</td><td>{e(source)}</td><td><b>{e(score)}</b></td>'
                       f'<td><span class="log-decision tone-{LOG_TONES.get(decision, "gray")}">{e(decision)}</span></td><td>{e(origin)}</td></tr>'
                       for target, source, score, decision, origin in rows)
    return (f'<div class="summary-card log-summary"><div class="sc-title">{icons.icon("history")} Recent predictions</div>'
            '<div class="log-wrap"><table class="pred-log"><thead><tr><th scope="col">Target hour</th><th scope="col">Forecast input</th>'
            f'<th scope="col">Risk score</th><th scope="col">Decision</th><th scope="col">Recorded by</th></tr></thead><tbody>{body}</tbody></table></div>'
            f'<div class="sc-foot">Hourly runs of the trained Random Forest, from saved records only: the hourly worker\'s public run log'
            f'{"" if worker_log_reachable else " (unreachable just now)"} and this dashboard\'s own runs. Hours without a saved run are '
            'not listed. Risk score: model score, not a calibrated probability.</div></div>')


def details_html(status):
    """The full explanation, coverage and model caveat shown under 'About this estimate'."""
    e = lambda value: html.escape(str(value))  # noqa: E731
    return (f'<div class="resident-guidance"><div class="resident-text">{e(status["explanation"])}</div>'
            f'<ul><li><b>Area:</b> {e(status["coverage"])}</li><li><b>Last update:</b> {e(status["updated"])}</li></ul>'
            f'<div class="resident-note">{e(status["model_note"])}</div></div>')


def quick_actions_html(advice):
    """Icon chips with a few words each, matching the level's advice (act now or prepare)."""
    e = lambda value: html.escape(str(value))  # noqa: E731
    short = SHORT_ACT_NOW if advice['level'] in ('WARNING', 'UNAVAILABLE') else SHORT_PREPARE
    chips = ''.join(f'<span class="action-chip">{icons.icon(TOPIC_ICONS[topic])}{e(short[topic])}</span>'
                    for topic, _ in advice['items'])
    return f'<div class="quick-actions"><div class="resident-action">{e(advice["action"])}</div><div class="action-chips">{chips}</div></div>'


def advice_cards_html(advice, title, compact=False):
    """Safety advice as icon cards (one per topic) under a short heading; compact: small tiles."""
    e = lambda value: html.escape(str(value))  # noqa: E731
    cards = ''.join(f'<div class="advice-card"><div class="advice-icon">{icons.icon(TOPIC_ICONS[topic])}</div><b>{e(topic)}</b><p>{e(text)}</p></div>'
                    for topic, text in advice['items'])
    grid = 'advice-grid compact' if compact else 'advice-grid'
    return f'<div class="advice-block"><div class="resident-action">{e(title)}</div><div class="{grid}">{cards}</div></div>'
