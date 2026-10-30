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
        estimate = f'{"Last" if stale else "Model"} estimate: {float(probability):.0%} chance of a storm'
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
    """Minimal Markdown for low-data access: status, period, timestamp, guidance."""
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
    lines += ['', f"_{advice['note']}_"]
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


def gauge_svg(probability, tone):
    """Small semicircle gauge with a tick at the 35% threshold; the value is also given as alt text."""
    try:
        p = min(max(float(probability), 0.0), 1.0)
        usable = math.isfinite(p)
    except (TypeError, ValueError):
        p, usable = 0.0, False
    angle = math.pi * (1 - THRESHOLD)
    x1, y1 = 60 + 41 * math.cos(angle), 60 - 41 * math.sin(angle)
    x2, y2 = 60 + 59 * math.cos(angle), 60 - 59 * math.sin(angle)
    label = f'Model-estimated storm risk {p:.0%}, warning threshold 35%' if usable else 'No model estimate'
    colour = GAUGE_COLOURS.get(tone, GAUGE_COLOURS['gray'])
    svg = ('<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 120 68">'
           '<path d="M10 60 A50 50 0 0 1 110 60" fill="none" stroke="#c7d2e0" stroke-width="12" stroke-linecap="round"/>'
           f'<path d="M10 60 A50 50 0 0 1 110 60" fill="none" stroke="{colour}" stroke-width="12" stroke-linecap="round" pathLength="100" stroke-dasharray="{p * 100 if usable else 0:.1f} 100"/>'
           f'<line x1="{x1:.1f}" y1="{y1:.1f}" x2="{x2:.1f}" y2="{y2:.1f}" stroke="#64748b" stroke-width="3"/></svg>')
    # An image, because the page's HTML sanitiser removes inline SVG; the value is in the alt text.
    return f'<img class="mini-gauge" src="data:image/svg+xml;base64,{base64.b64encode(svg.encode()).decode()}" alt="{label}">'


def summary_html(status, probability, weather, record, communication):
    """The four homepage summary cards: forecast weather, model estimate, warning decision, communication status.

    weather: dict of display strings (temperature, rain, wind, status); record: text on the genuine warning record;
    communication: list of (label, value) strings. Nothing here is computed from anything but these inputs.
    """
    e = lambda value: html.escape(str(value))  # noqa: E731
    sim = f'<div class="resident-sim">{e(status["label"])}</div>' if status['simulated'] else ''
    estimate = f'{float(SIMULATED_PROBABILITY if status["simulated"] else probability):.0%}' if status['level'] != 'UNAVAILABLE' else 'n/a'
    weather_card = (f'<div class="summary-card wx-summary"><div class="sc-title">{icons.icon("cloud-rain")} Weather forecast (ECMWF)</div>'
                    f'<div class="sc-value">{e(weather["temperature"])}</div>'
                    f'<div class="sc-line">Rain {e(weather["rain"])} · Wind {e(weather["wind"])}</div>'
                    f'<div class="sc-line">Gusts {e(weather["gust"])}</div><div class="sc-foot">{e(weather["status"])}</div></div>')
    risk_card = (f'<div class="summary-card risk-summary tone-{e(status["tone"])}">{sim}<div class="sc-title">{icons.icon("gauge")} Model-estimated storm risk</div>'
                 f'<div class="sc-gauge">{gauge_svg(SIMULATED_PROBABILITY if status["simulated"] else probability, status["tone"])}<b>{e(estimate)}</b></div>'
                 f'<div class="sc-head">{e(status["headline"])}</div><div class="sc-line">{e(status["estimate"])}</div>'
                 f'<div class="sc-line">{icons.icon("clock")} Prediction period {e(status["period"])}</div>'
                 f'<div class="sc-foot">Model updated {e(status["updated"])} · {e(HERO_NOTE)}</div></div>')
    decision_card = (f'<div class="summary-card decision-summary"><div class="sc-title">{icons.icon("scale")} Warning decision</div>'
                     f'<div class="sc-line"><b>Warning threshold: {THRESHOLD:.0%}</b></div>'
                     f'<div class="sc-line">{e(status["decision"])}</div><div class="sc-line">{e(record)}</div>'
                     f'<details class="threshold-info"><summary>{icons.icon("info")} Why 35%?</summary><p>{e(THRESHOLD_TEXT)}</p>'
                     '<p>More detail: menu, then Risk Analysis.</p></details></div>')
    rows = ''.join(f'<div class="sc-line"><b>{e(label)}:</b> {e(value)}</div>' for label, value in communication)
    comms_card = f'<div class="summary-card comms-summary"><div class="sc-title">{icons.icon("message")} Warning communication</div>{rows}</div>'
    return f'<div class="summary-grid">{weather_card}{risk_card}{decision_card}{comms_card}</div>'


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


def advice_cards_html(advice, title):
    """Safety advice as icon cards (one per topic) under a short heading."""
    e = lambda value: html.escape(str(value))  # noqa: E731
    cards = ''.join(f'<div class="advice-card"><div class="advice-icon">{icons.icon(TOPIC_ICONS[topic])}</div><b>{e(topic)}</b><p>{e(text)}</p></div>'
                    for topic, text in advice['items'])
    return f'<div class="advice-block"><div class="resident-action">{e(title)}</div><div class="advice-grid">{cards}</div></div>'
