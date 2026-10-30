"""Visual redesign: icons from genuine forecast values only, no external assets, themes, map and navigation."""
import json
import re
import unittest

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
        self.assertIn("initial_sidebar_state='collapsed' if text_view else 'auto'", source)

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
        group = next(g for g in at.button_group if g.key == 'map_basemap')
        self.assertEqual(list(group.options), ['Satellite', 'Streets', 'Low data'])
        self.assertTrue([t for t in at.toggle if t.key == 'map_overlay'])
        chart = at.get('deck_gl_json_chart')[0].proto
        spec = json.loads(chart.json)
        self.assertEqual(json.loads(chart.tooltip)['html'], '<b>{name}</b><br/>{detail}')
        layers = {layer['@@type'] for layer in spec['layers']}
        self.assertNotIn('HeatmapLayer', layers)  # no invented radar-style layers
        group.set_value('Low data').run()
        spec = json.loads(at.get('deck_gl_json_chart')[0].proto.json)
        style = json.loads(__import__('base64').b64decode(spec['mapStyle'].split(',', 1)[1]))
        self.assertEqual(style['sources'], {})  # no map tiles are requested

    def test_mobile_navigation_reaches_every_section(self):
        self.write_prediction(.05)
        at = self.app().run()
        nav = next(g for g in at.button_group if g.key == 'mobile_nav_choice')
        self.assertEqual(len(nav.options), 10)  # 8 sections plus SMS Alerts and Warning History
        nav.set_value('🛟 Safety Advice').run()
        self.assertEqual(at.session_state['dashboard_page'], '🛟 Safety Advice')
        self.assertIn('Full advice for when a storm is close', '\n'.join(c.value for c in at.caption))
        self.button(at, 'Historical Data').click().run()  # sidebar navigation still works and stays in sync
        self.assertEqual(at.session_state['mobile_nav_choice'], '🕒 Historical Data')

    def test_text_view_loads_no_theme_or_animation(self):
        self.write_prediction(.05)
        at = self.app(view='text').run()
        page = self.html(at)
        self.assertNotIn('<style>', page)
        self.assertNotIn('@keyframes', page)
        self.assertEqual([g for g in at.button_group if g.key == 'mobile_nav_choice'], [])


if __name__ == '__main__':
    unittest.main()
