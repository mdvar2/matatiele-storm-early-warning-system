"""Visual redesign: icons from genuine forecast values only, no external assets, themes, map and navigation."""
import json
import re
import unittest
from types import SimpleNamespace
import ast

import dashboard_theme as theme
import test_resident_dashboard as rd


class WeatherCondition(unittest.TestCase):
    def test_rules_use_only_forecast_values(self):
        cases = [((0.0, 5, 12), ('clear-day', 'Clear (forecast)')), ((0.0, 5, 22), ('clear-night', 'Clear (forecast)')),
                 ((0.0, 45, 10), ('partly-day', 'Partly cloudy (forecast)')), ((0.0, 45, 3), ('partly-night', 'Partly cloudy (forecast)')),
                 ((0.0, 85, 12), ('cloud', 'Mostly cloudy (forecast)')), ((0.1, 10, 12), ('rain', 'Rain forecast')),
                 ((4.2, 100, 2), ('rain', 'Rain forecast')), ((0.09, 69.9, 6), ('partly-day', 'Partly cloudy (forecast)')),
                 ((None, None, 12), ('unknown', 'Forecast conditions unavailable')),
                 ((float('nan'), 'x', 12), ('unknown', 'Forecast conditions unavailable')),
                 ((0.0, None, 12), ('unknown', 'No rain forecast')), ((0.0, 10, None), ('clear-day', 'Clear (forecast)'))]
        for args, expected in cases:
            with self.subTest(args=args):
                self.assertEqual(theme.weather_condition(*args), expected)

    def test_labels_never_claim_observations(self):
        labels = {theme.weather_condition(r, c, h)[1] for r in (None, 0, .05, .2, 9) for c in (None, 0, 40, 90) for h in (None, 3, 12)}
        for label in labels:
            self.assertNotRegex(label.lower(), r'observ|measured|radar|current|now')
            self.assertRegex(label.lower(), r'forecast|unavailable')


class Assets(unittest.TestCase):
    def test_icons_are_self_contained_and_respect_reduced_motion(self):
        for kind in ('clear-day', 'clear-night', 'partly-day', 'partly-night', 'cloud', 'rain', 'unknown', 'bogus'):
            with self.subTest(kind=kind):
                svg = theme.weather_icon_svg(kind)
                self.assertTrue(svg.startswith('<svg xmlns="http://www.w3.org/2000/svg"'))
                self.assertNotRegex(svg, r'(?i)<script|href=|url\(|https?://(?!www\.w3\.org/2000/svg)')
                self.assertIn('prefers-reduced-motion', svg)

    def test_css_has_themes_motion_safety_and_no_downloads(self):
        css = theme.CSS
        self.assertIn('@media (prefers-color-scheme: dark)', css)
        self.assertIn('@media (prefers-reduced-motion: reduce)', css)
        self.assertNotRegex(css, r'https?://(?!www\.w3\.org/2000/svg)')  # no fonts, images or scripts fetched
        self.assertNotIn('@import', css)
        self.assertIn('data:image/svg+xml;base64,', css)  # the clouds are inline vector art
        self.assertLess(len(css.encode('utf-8')), 40_000)

    def test_mobile_layout_is_not_broken_by_the_theme(self):
        # Streamlit overlays the sidebar on phones; repositioning it squeezed the page (found in screenshots).
        self.assertNotRegex(theme.CSS, r'stSidebar"\][^{]*\{[^}]*position')
        # Same for the main area: phones position it absolutely under the sliding sidebar.
        self.assertNotRegex(theme.CSS, r'(stMain|stAppViewContainer)"\][^{]*\{[^}]*position')
        source = (rd.ROOT / '16_dashboard.py').read_text(encoding='utf-8')
        self.assertIn("initial_sidebar_state='collapsed')", source)  # the ☰ menu holds Alerts and the research sections

    def test_menu_button_is_a_hamburger(self):
        for control in ('stSidebarCollapseButton', 'stExpandSidebarButton'):
            self.assertIn(f'[data-testid="{control}"] [data-testid="stIconMaterial"]', theme.CSS)
        self.assertIn('font-size:0!important', theme.CSS)  # hides the double-arrow glyph; three bars are drawn instead

    def test_theme_stylesheet_switches_the_dark_layer_explicitly(self):
        dark, light = theme.theme_css('dark'), theme.theme_css('light')
        self.assertIn('@media all {', dark); self.assertNotIn('@media (prefers-color-scheme: dark)', dark)
        self.assertIn('@media not all {', light); self.assertNotIn('@media (prefers-color-scheme: dark)', light)
        for css in (dark, light):
            self.assertIn('.ico-home{--m:url("data:image/svg+xml;base64,', css)  # icon masks follow the text colour
            self.assertIn('.resident-card.tone-red{--m:url(', css)  # severity shown by icon shape, not colour alone
            self.assertIn(':focus-visible', css)

    def test_text_contrast_in_both_themes(self):
        def luminance(hex_colour):
            channels = [int(hex_colour[i:i + 2], 16) / 255 for i in (1, 3, 5)]
            channels = [c / 12.92 if c <= .03928 else ((c + .055) / 1.055) ** 2.4 for c in channels]
            return .2126 * channels[0] + .7152 * channels[1] + .0722 * channels[2]

        def ratio(a, b):
            high, low = sorted((luminance(a), luminance(b)), reverse=True)
            return (high + .05) / (low + .05)
        light_block, dark_block = theme.CSS.split('@media (prefers-color-scheme: dark)', 1)
        for block in (light_block, dark_block[:1500]):
            token = lambda name: re.search(rf'--{name}:(#[0-9a-fA-F]{{6}})', block).group(1)  # noqa: E731
            for name in ('text', 'muted', 'heading'):
                self.assertGreaterEqual(ratio(token(name), token('card-solid')), 4.5, name)
            self.assertGreaterEqual(ratio(token('primary-text'), token('primary')), 4.5)

    def test_workflow_diagram_structure(self):
        page = theme.flow_html('disabled')
        steps = re.findall(r'<b>([^<]+)</b>', page)
        self.assertEqual(steps, ['External forecast', 'Random Forest', '35% warning decision', 'Warning information', 'SMS communication'])
        self.assertNotIn('Official', page)  # the officials' portal is a separate interface, not a stage in this workflow
        self.assertEqual(page.count('class="arrow"'), 4)
        sms = page[page.index('SMS communication') - 200:]
        self.assertIn('Optional · not enabled', sms); self.assertIn('step optional', page)
        self.assertIn('Optional · configured', theme.flow_html('twilio'))
        self.assertIn('development outbox, nothing sent', theme.flow_html('outbox'))
        self.assertIn('flex-direction:column', theme.CSS)  # stacks vertically on phones

    def test_status_strip(self):
        live = theme.status_strip(False, '30 Oct 10:20 SAST', False)
        self.assertIn('Live forecast', live); self.assertNotIn('Outdated', live); self.assertNotIn('SIMULATION', live)
        stale = theme.status_strip(True, None, False)
        self.assertIn('Outdated data', stale); self.assertIn('last update unknown', stale); self.assertNotIn('Live forecast', stale)
        self.assertIn('SIMULATION ON', theme.status_strip(False, 'x', True))
        self.assertIn('&lt;b&gt;', theme.status_strip(False, '<b>', False))


class RedesignedDashboard(rd.DashboardHarness):
    """The real dashboard (hermetic AppTest harness from test_resident_dashboard)."""

    def test_status_strip_reflects_freshness(self):
        self.write_prediction(.05)
        self.assertIn('Live forecast', self.html(self.app().run()))
        self.write_prediction(.05, fresh=False)
        page = self.html(self.app(inference_ok=False).run())
        self.assertIn('Outdated data', page); self.assertNotIn('<b>Live forecast</b>', page)

    def test_weather_card_icon_is_from_forecast_values(self):
        self.write_prediction(.05)  # fixture: 0.0 mm rain, 10 % cloud at 11:00 SAST
        page = self.html(self.app().run())
        self.assertIn('alt="Clear (forecast)"', page)
        self.assertIn('ECMWF forecast for 11:00 SAST - not an observation', page)

    def test_map_controls_tooltips_and_low_data_basemap(self):
        self.write_prediction(.05)
        at = self.app().run()
        self.assertEqual(at.get('deck_gl_json_chart'), [])  # the map is only on the Map page, not repeated on Home
        self.go(at, 'Weather Map')
        group = next(g for g in at.button_group if g.key == 'map_basemap')
        self.assertEqual(list(group.options), ['Satellite', 'Streets', 'Low data'])
        self.assertTrue([t for t in at.toggle if t.key == 'map_overlay'])
        chart = at.get('deck_gl_json_chart')[0].proto
        spec = json.loads(chart.json)
        self.assertEqual(json.loads(chart.tooltip)['html'], '<b>{name}</b><br/>{detail}')
        layers = {layer['@@type'] for layer in spec['layers']}
        self.assertNotIn('HeatmapLayer', layers)  # no invented radar-style layers
        self.assertIn('Storm model: LOW', chart.json)  # ring at Matatiele coloured by the genuine model level
        group.set_value('Low data').run()
        spec = json.loads(at.get('deck_gl_json_chart')[0].proto.json)
        style = json.loads(__import__('base64').b64decode(spec['mapStyle'].split(',', 1)[1]))
        self.assertEqual(style['sources'], {})  # no map tiles are requested

    def test_top_navigation_reaches_every_section(self):
        self.write_prediction(.05)
        at = self.app().run()
        nav = next(g for g in at.button_group if g.key == 'top_nav')
        self.assertEqual(len(nav.options), 4)  # Home, Forecast, Map, Safety
        self.assertEqual(sorted(b.key for b in at.button if (b.key or '').startswith('menu_')),
                         ['menu_About', 'menu_Alerts', 'menu_Historical Data', 'menu_Risk Analysis'])  # in the ☰ menu
        nav.set_value('🛟 Safety Advice').run()
        self.assertEqual(at.session_state['dashboard_page'], '🛟 Safety Advice')
        self.assertIn('Full advice for when a storm is close', '\n'.join(c.value for c in at.caption))
        self.go(at, 'Historical Data')  # from the ☰ menu
        self.assertEqual(at.session_state['dashboard_page'], '🕒 Historical Data')
        self.assertIsNone(at.session_state['top_nav'])  # no top-bar section is highlighted

    def test_each_component_appears_on_exactly_one_page(self):
        self.write_prediction(.05)
        at = self.app().run()
        markers = {'class="wx-card"': 'Dashboard', 'class="contacts-card"': 'Dashboard', 'class="threshold-info"': 'Dashboard',
                   'class="risk-gauge"': 'Risk Analysis', 'class="risk-scale"': 'Risk Analysis',
                   'class="advice-grid"': 'Safety Advice', 'class="flow"': 'About', 'class="kpi': 'About'}
        found = {marker: [] for marker in markers}
        maps = []
        for section in ('Dashboard', 'Live Forecast', 'Weather Map', 'Safety Advice', 'Alerts', 'Risk Analysis', 'Historical Data', 'About'):
            page = self.html(self.go(at, section))
            for marker in markers:
                if marker in page:
                    found[marker].append(section)
            if at.get('deck_gl_json_chart'):
                maps.append(section)
        self.assertEqual(found, {marker: [section] for marker, section in markers.items()})
        self.go(at, 'Dashboard')
        self.assertNotIn('NO WARNING IN EFFECT', self.html(at))  # the redundant status card is gone; the risk card remains
        self.assertIn('resident-card tone-green hero-risk', self.html(at))
        self.assertIn('Warning threshold: 35%', self.html(at))
        self.assertEqual(maps, ['Weather Map'])

    def style(self, at):
        return next(e.proto.body for e in at.get('html') if e.proto.body.startswith('<style>'))

    def test_theme_switch_applies_everywhere_and_persists(self):
        self.write_prediction(.05)
        at = self.app().run()
        self.assertIn('@media not all {', self.style(at))  # light by default
        switch = next(t for t in at.toggle if t.key == 'theme_switch')
        self.assertEqual((switch.label, switch.value), ('Dark theme', False))  # accessible name and state
        switch.set_value(True).run()
        self.assertEqual(at.query_params['theme'], ['dark'])  # kept in the link: survives a refresh
        for section in ('Dashboard', 'Live Forecast', 'Weather Map', 'Safety Advice', 'Alerts', 'Risk Analysis', 'Historical Data', 'About'):
            self.assertIn('@media all {', self.style(self.go(at, section)), section)
        refreshed = self.app(theme='dark').run()  # a refresh keeps ?theme=dark
        self.assertIn('@media all {', self.style(refreshed))
        self.assertTrue(next(t for t in refreshed.toggle if t.key == 'theme_switch').value)
        portal = self.app(portal='officials', theme='dark').run()  # the officials' portal uses the same theme system
        self.assertIn('@media all {', self.style(portal))
        self.assertTrue([t for t in portal.toggle if t.key == 'theme_switch'])
        next(t for t in refreshed.toggle if t.key == 'theme_switch').set_value(False).run()
        self.assertEqual(refreshed.query_params['theme'], ['light'])
        self.assertIn('@media not all {', self.style(refreshed))

    def test_theme_choice_order(self):
        tree = ast.parse((rd.ROOT / '16_dashboard.py').read_text(encoding='utf-8'))
        function = next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == 'resolve_theme')
        for session, query, prefs, expected in ((None, {}, None, 'light'), (None, {}, {'dark': True}, 'dark'),
                                               (None, {}, {'theme': 'light', 'dark': True}, 'light'),  # remembered choice beats the device
                                               (None, {'theme': 'dark'}, {'theme': 'light'}, 'dark'),    # the link beats the browser
                                               ('light', {'theme': 'dark'}, None, 'light'),             # this session's switch beats all
                                               (None, {'theme': 'purple'}, None, 'light')):
            state = {} if session is None else {'theme': session}
            namespace = dict(st=SimpleNamespace(session_state=SimpleNamespace(get=state.get, theme=session), query_params=query),
                             THEMES=('light', 'dark'), Any=object)
            exec(compile(ast.Module(body=[function], type_ignores=[]), '<theme>', 'exec'), namespace)
            self.assertEqual(namespace['resolve_theme'](prefs), expected, (session, query, prefs))

    def test_no_emoji_on_any_page(self):
        emoji = re.compile('[🀀-🫿☀-➿⬀-⯿️]')
        self.write_prediction(.05)
        at = self.app().run()
        for section in ('Dashboard', 'Live Forecast', 'Weather Map', 'Safety Advice', 'Alerts', 'Risk Analysis', 'Historical Data', 'About'):
            self.go(at, section)
            visible = [self.html(at)] + [b.label for b in at.button] + [t.label for t in at.toggle]
            visible += [str(o) for g in at.button_group for o in g.options]
            self.assertFalse(emoji.findall(' '.join(visible)), section)
        portal = self.app(portal='officials').run()
        self.assertFalse(emoji.findall(self.html(portal)))

    def test_threshold_model_and_low_connectivity_explanations(self):
        self.write_prediction(.05)
        at = self.app().run()
        home = self.html(at)
        self.assertIn('Why 35%?', home); self.assertIn('Warning threshold: 35%', home)
        self.assertIn('href="?view=text"', home)  # low-data view reachable from Home
        self.assertTrue([b for b in at.button if b.key == 'home_alerts'])
        next(b for b in at.button if b.key == 'home_threshold').click().run()
        self.assertEqual(at.session_state['dashboard_page'], '📈 Risk Analysis')
        text = ' '.join(m.value for m in at.markdown) + ' '.join(c.value for c in at.caption)
        self.assertIn(rd.rv.THRESHOLD_TEXT, text)
        self.assertIn('not an independently validated optimum', text)  # no claim that 35% is optimal
        self.assertEqual((rd.ROOT / 'outputs' / 'model_live' / 'live_selected_threshold.txt').read_text().strip(), '0.35')
        about = self.html(self.go(at, 'About'))
        self.assertEqual(about.count('<li><b>'), 9 + 4)  # nine model steps and four low-connectivity points
        for phrase in ('ERA5', '300 decision trees', 'does not produce weather forecasts', 'does not run offline', 'not implemented'):
            self.assertIn(phrase, about)
        self.assertEqual([e.label for e in at.expander if e.label in ('How the model and system work', 'Designed for low connectivity')],
                         ['How the model and system work', 'Designed for low connectivity'])

    def test_text_view_loads_no_theme_or_animation(self):
        self.write_prediction(.05)
        at = self.app(view='text').run()
        page = self.html(at)
        self.assertNotIn('<style>', page)
        self.assertNotIn('@keyframes', page)
        self.assertEqual([g for g in at.button_group if g.key == 'top_nav'], [])


if __name__ == '__main__':
    unittest.main()
