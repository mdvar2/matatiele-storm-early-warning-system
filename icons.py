"""Outline icons (Lucide style: 24 x 24 grid, 2 px round strokes) for the dashboard's HTML.

Each icon is a CSS mask filled with the current text colour, so it follows the light or dark
theme and any state colour. Purely decorative icons are hidden from screen readers; icons that
carry meaning are given a label by the caller.
"""
import base64
import html

ICONS = {
    'home': '<path d="M3 10.5 12 3l9 7.5"/><path d="M5 9.5V21h14V9.5"/><path d="M10 21v-6h4v6"/>',
    'cloud': '<path d="M7 18h10.5a4 4 0 0 0 .4-7.98A6 6 0 0 0 6.2 9.3 4.4 4.4 0 0 0 7 18Z"/>',
    'cloud-rain': '<path d="M7 15h10.5a4 4 0 0 0 .4-7.98A6 6 0 0 0 6.2 6.3 4.4 4.4 0 0 0 7 15Z"/><path d="M8 18l-1 3M12 18l-1 3M16 18l-1 3"/>',
    'wind': '<path d="M3 8h11a3 3 0 1 0-3-3"/><path d="M3 12h15a3 3 0 1 1-3 3"/><path d="M3 16h7"/>',
    'droplets': '<path d="M12 3s-6 6.5-6 11a6 6 0 0 0 12 0c0-4.5-6-11-6-11Z"/>',
    'zap': '<path d="M13 2 4 14h7l-1 8 9-12h-7l1-8Z"/>',
    'thermometer': '<path d="M14 14.5V4a2 2 0 1 0-4 0v10.5a4 4 0 1 0 4 0Z"/>',
    'clock': '<circle cx="12" cy="12" r="9"/><path d="M12 7v5l3 2"/>',
    'refresh': '<path d="M20 11a8 8 0 0 0-14.6-4.5L4 8"/><path d="M4 3v5h5"/><path d="M4 13a8 8 0 0 0 14.6 4.5L20 16"/><path d="M20 21v-5h-5"/>',
    'map': '<path d="M9 4 3 6v14l6-2 6 2 6-2V4l-6 2-6-2Z"/><path d="M9 4v14M15 6v14"/>',
    'map-pin': '<path d="M12 21s-7-6.1-7-11a7 7 0 0 1 14 0c0 4.9-7 11-7 11Z"/><circle cx="12" cy="10" r="2.5"/>',
    'shield': '<path d="M12 3 5 6v6c0 4.4 3 7.8 7 9 4-1.2 7-4.6 7-9V6l-7-3Z"/><path d="M9 12l2 2 4-4"/>',
    'bell': '<path d="M6 16v-5a6 6 0 0 1 12 0v5l2 2H4l2-2Z"/><path d="M10 21a2 2 0 0 0 4 0"/>',
    'activity': '<path d="M3 12h4l3-8 4 16 3-8h4"/>',
    'chart': '<path d="M4 4v16h16"/><path d="M8 16v-4M12 16V8M16 16v-6"/>',
    'info': '<circle cx="12" cy="12" r="9"/><path d="M12 11v5M12 7.5h.01"/>',
    'sun': '<circle cx="12" cy="12" r="4"/><path d="M12 2v2M12 20v2M4.9 4.9l1.4 1.4M17.7 17.7l1.4 1.4M2 12h2M20 12h2M4.9 19.1l1.4-1.4M17.7 6.3l1.4-1.4"/>',
    'moon': '<path d="M20 14.5A8 8 0 1 1 9.5 4a6.5 6.5 0 0 0 10.5 10.5Z"/>',
    'phone': '<path d="M5 4h3l2 5-2.5 1.5a11 11 0 0 0 6 6L15 14l5 2v3a2 2 0 0 1-2 2A16 16 0 0 1 3 6a2 2 0 0 1 2-2Z"/>',
    'alert': '<path d="M12 3 2 20h20L12 3Z"/><path d="M12 10v4M12 17h.01"/>',
    'check-circle': '<circle cx="12" cy="12" r="9"/><path d="M8 12l3 3 5-6"/>',
    'help-circle': '<circle cx="12" cy="12" r="9"/><path d="M9.5 9a2.5 2.5 0 1 1 3.5 2.3c-.6.3-1 .9-1 1.7M12 17h.01"/>',
    'bell-off': '<path d="M8.7 4.4A6 6 0 0 1 18 9.5V14"/><path d="M6 11v5l-2 2h14"/><path d="M10 21a2 2 0 0 0 4 0"/><path d="M3 3l18 18"/>',
    'megaphone': '<path d="M3 10v4h3l8 4V6l-8 4H3Z"/><path d="M18 9a4 4 0 0 1 0 6"/>',
    'message': '<path d="M4 5h16v11H9l-5 4V5Z"/>',
    'radar': '<circle cx="12" cy="12" r="9"/><circle cx="12" cy="12" r="4.5"/><path d="M12 12l6-6"/>',
    'cpu': '<rect x="6" y="6" width="12" height="12" rx="2"/><path d="M9 2v4M15 2v4M9 18v4M15 18v4M2 9h4M2 15h4M18 9h4M18 15h4"/>',
    'scale': '<path d="M12 4v16M6 20h12M5 8h14"/><path d="M5 8l-3 6a3 3 0 0 0 6 0L5 8ZM19 8l-3 6a3 3 0 0 0 6 0l-3-6Z"/>',
    'siren': '<path d="M7 18v-5a5 5 0 0 1 10 0v5"/><path d="M5 18h14v3H5z"/><path d="M12 3v2M4 7l1.5 1M20 7l-1.5 1"/>',
    'smartphone': '<rect x="7" y="2" width="10" height="20" rx="2"/><path d="M11 18h2"/>',
    'clipboard': '<rect x="5" y="4" width="14" height="17" rx="2"/><path d="M9 4V3h6v1M9 10h6M9 14h6M9 18h4"/>',
    'car': '<path d="M5 16l1.5-5h11L19 16"/><path d="M3 16h18v3H3z"/><circle cx="7" cy="19" r="1.5"/><circle cx="17" cy="19" r="1.5"/>',
    'waves': '<path d="M3 8c2 0 2-2 4.5-2S10 8 12 8s2-2 4.5-2S19 8 21 8"/><path d="M3 13c2 0 2-2 4.5-2s2.5 2 4.5 2 2-2 4.5-2 2.5 2 4.5 2"/><path d="M3 18c2 0 2-2 4.5-2s2.5 2 4.5 2 2-2 4.5-2 2.5 2 4.5 2"/>',
    'fence': '<path d="M5 8l2-3 2 3v12H5zM15 8l2-3 2 3v12h-4z"/><path d="M9 10h6M9 15h6"/>',
    'eye': '<path d="M2 12s4-7 10-7 10 7 10 7-4 7-10 7S2 12 2 12Z"/><circle cx="12" cy="12" r="3"/>',
    'arrow-left': '<path d="M19 12H5M11 6l-6 6 6 6"/>',
    'arrow-right': '<path d="M5 12h14M13 6l6 6-6 6"/>',
    'gauge': '<path d="M4 18a8 8 0 1 1 16 0"/><path d="M12 18l4-5"/>',
    'calendar': '<rect x="4" y="5" width="16" height="16" rx="2"/><path d="M8 3v4M16 3v4M4 10h16"/>',
    'history': '<path d="M3 12a9 9 0 1 0 3-6.7L3 8"/><path d="M3 3v5h5"/><path d="M12 7v5l3 2"/>',
    'trend': '<path d="M3 17l6-6 4 4 8-8"/><path d="M15 7h6v6"/>',
}


def svg(name):
    return ('<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="#000" stroke-width="2" '
            'stroke-linecap="round" stroke-linejoin="round">' + ICONS[name] + '</svg>')


def _uri(name):
    return 'data:image/svg+xml;base64,' + base64.b64encode(svg(name).encode('utf-8')).decode('ascii')


CSS = ('.ico{display:inline-block;width:1.1em;height:1.1em;flex-shrink:0;vertical-align:-.18em;background-color:currentColor;'
       '-webkit-mask:var(--m) center/contain no-repeat;mask:var(--m) center/contain no-repeat}'
       + ''.join(f'.ico-{name}{{--m:url("{_uri(name)}")}}' for name in ICONS))


def icon(name, label=None, size=None):
    """An icon span; decorative unless a label is given."""
    if name not in ICONS:
        raise KeyError(name)
    style = f' style="width:{size};height:{size}"' if size else ''
    access = f' role="img" aria-label="{html.escape(label, quote=True)}"' if label else ' aria-hidden="true"'
    return f'<span class="ico ico-{name}"{style}{access}></span>'
