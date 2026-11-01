"""The status file behind the offline page (static/offline.html, served at /app/static/offline.html).

The dashboard writes static/status.json from the genuine model output (never the administrator's on-screen
simulation): risk score and level, prediction period, warning decision, warnings in effect, any early alert, safety
advice and emergency numbers. The page's service worker keeps the last copy so it opens with no connection.
No personal data. The file is rewritten only when its content changes.
"""
import json
import os
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

import emergency_contacts
import resident_view
import warning_events as we

SAST = ZoneInfo('Africa/Johannesburg')


def build(status, probability, record, active_genuine, early_alert=None, now=None):
    """status: genuine resident_status(); record: as for resident_view.warning_state; active_genuine: genuine events in effect."""
    now = now or datetime.now(timezone.utc)
    decision, decision_tone, _, decision_detail = resident_view.warning_state(status, record)
    in_effect = bool(active_genuine)
    advice = resident_view.guidance('WARNING' if in_effect else status['guidance_level'])
    usable = status['level'] != 'UNAVAILABLE'
    return {
        'generated_utc': now.astimezone(timezone.utc).isoformat(timespec='seconds'),
        'generated_sast': f'{now.astimezone(SAST):%d %b %Y %H:%M} SAST',
        'risk_score': resident_view.score_text(probability) if usable else 'n/a',
        'risk_level': 'OUT OF DATE' if status['stale'] else resident_view.RISK_BADGES[status['level']],
        'risk_tone': status['tone'] if status['tone'] in ('green', 'amber', 'red') else 'gray',
        'period': status['period'],
        'decision': decision, 'decision_tone': decision_tone, 'decision_detail': decision_detail,
        'warnings': [{'title': 'Storm warning', 'period': we.period_text(event)} for event in active_genuine],
        'early_alert': early_alert,
        'advice_title': f'What to do: {advice["action"]}',
        'advice': [[topic, text] for topic, text in advice['items']],
        'emergency': [[number, f'{label}: {detail}'] for number, label, detail in emergency_contacts.CONTACTS],
        'emergency_note': emergency_contacts.NOTE,
    }


def write(path, data):
    """Atomically write `data` if it differs from the saved file (ignoring the generation time). Returns True if written."""
    path = Path(path)
    content = {k: v for k, v in data.items() if not k.startswith('generated_')}
    try:
        saved = json.loads(path.read_text(encoding='utf-8'))
        if {k: v for k, v in saved.items() if not k.startswith('generated_')} == content:
            return False
    except (OSError, ValueError):
        pass
    path.parent.mkdir(parents=True, exist_ok=True)
    handle, temporary = tempfile.mkstemp(dir=path.parent, suffix='.tmp')
    with os.fdopen(handle, 'w', encoding='utf-8') as out:
        json.dump(data, out, indent=1)
    os.replace(temporary, path)
    return True


TEMPLATE = Path(__file__).resolve().parent / 'static' / 'offline.html'
EMBED_SLOT = '<script type="application/json" id="embedded-status">null</script>'


def download_html(data, template=TEMPLATE):
    """A self-contained copy of the offline page with `data` embedded, for residents to save on their phone.

    It needs no server, service worker or browser storage, so it opens from the phone's files with no connection on
    any hosting. '<' is escaped so saved text can never close the data block.
    """
    page = Path(template).read_text(encoding='utf-8')
    if EMBED_SLOT not in page:
        raise ValueError('offline page template has no data slot')
    payload = json.dumps(data, ensure_ascii=False).replace('<', '\\u003c')  # JSON escape for '<'
    return page.replace(EMBED_SLOT, EMBED_SLOT.replace('>null<', '>' + payload + '<'), 1)
