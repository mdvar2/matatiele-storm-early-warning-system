"""Deterministic timestamp regression fixtures; no forecast requests or SMS."""
import ast
from datetime import UTC
import html
import math
from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest.mock import MagicMock, Mock

import altair as alt
import numpy as np
import pandas as pd

from forecast_timing import (SAST, TARGET_LABEL, GENERATED_LABEL, local_time,
                             interval_label, timestamp_labels, six_hour_forecast,
                             forecast_axis_order, next_hour_endpoint, model_input_hour,
                             next_complete_hour_endpoint, is_next_complete_prediction)

ROOT = Path(__file__).resolve().parents[1]


class ForecastTimingTests(unittest.TestCase):
    def frame(self):
        # Timing fixtures deliberately unordered across midnight, not live data.
        times = pd.date_range('2026-10-10T18:00:00Z', periods=9, freq='h')
        return pd.DataFrame({'forecast_hour': times[::-1], 'sample_id': 25,
                             'precipitation_mm': 0.0, 'cloud_cover': 0.0})

    def test_utc_to_sast(self):
        time = local_time('2026-10-10T18:29:00Z')
        self.assertEqual(time.hour, 20)
        self.assertEqual(str(time.tzinfo), 'Africa/Johannesburg')

    def test_offset_and_legacy_utc(self):
        self.assertEqual(local_time('2026-10-10T20:29:00+02:00'),
                         local_time('2026-10-10T18:29:00'))

    def test_missing_time_remains_unknown(self):
        for value in [None, '', float('nan'), 'invalid']:
            self.assertIsNone(local_time(value))

    def test_midnight_conversion(self):
        time = local_time('2026-10-10T22:00:00Z')
        self.assertEqual(time.strftime('%Y-%m-%d %H:%M'), '2026-10-11 00:00')

    def test_six_intervals_chronological(self):
        result = six_hour_forecast(self.frame(), pd.Timestamp('2026-10-10T20:29:00+02:00'))
        self.assertEqual(forecast_axis_order(result['time']), ['21:00','22:00','23:00','00:00','01:00','02:00'])
        self.assertTrue(result['time'].is_monotonic_increasing)
        self.assertEqual(result['time'].iloc[3].day, 11)

    def test_exact_hour_selects_next_endpoint(self):
        result = six_hour_forecast(self.frame(), pd.Timestamp('2026-10-10T20:00:00+02:00'))
        self.assertEqual(result['time'].iloc[0].hour, 21)

    def test_dashboard_targets_wholly_future_interval(self):
        now = pd.Timestamp('2026-10-10T20:29:00+02:00')
        start = model_input_hour(now,next_complete=True)
        end = next_complete_hour_endpoint(now)
        self.assertEqual(start.tz_convert(SAST).hour, 21)
        self.assertEqual(end.tz_convert(SAST).hour, 22)
        self.assertEqual(end-start,pd.Timedelta(hours=1))
        self.assertGreater(start,now)
        self.assertTrue(is_next_complete_prediction(start,end,now.to_pydatetime()))
        self.assertFalse(is_next_complete_prediction(now.floor('h'),now.ceil('h'),now.to_pydatetime()))

    def test_worker_input_selection_is_unchanged(self):
        now = pd.Timestamp('2026-10-10T20:29:00+02:00')
        self.assertEqual(model_input_hour(now).tz_convert(SAST).hour,20)

    def test_complete_interval_selection_crosses_midnight(self):
        now = pd.Timestamp('2026-10-10T20:29:00+02:00')
        result = six_hour_forecast(self.frame(),now,complete_intervals=True)
        self.assertEqual(forecast_axis_order(result['time']),
                         ['22:00','23:00','00:00','01:00','02:00','03:00'])
        self.assertTrue(result['time'].is_monotonic_increasing)

    def test_complete_interval_at_exact_hour(self):
        now = pd.Timestamp('2026-10-10T20:00:00+02:00')
        self.assertEqual(model_input_hour(now,next_complete=True),now)
        self.assertEqual(next_complete_hour_endpoint(now).tz_convert(SAST).hour,21)

    def test_next_complete_input_at_midnight_rollover(self):
        now = pd.Timestamp('2026-10-10T23:29:00+02:00')
        start = model_input_hour(now,next_complete=True).tz_convert(SAST)
        end = next_complete_hour_endpoint(now).tz_convert(SAST)
        self.assertEqual(start.strftime('%d %H:%M'),'11 00:00')
        self.assertEqual(end.strftime('%d %H:%M'),'11 01:00')

    def test_existing_prediction_is_stale_once_interval_starts(self):
        start = pd.Timestamp('2026-10-10T21:00:00+02:00')
        end = start + pd.Timedelta(hours=1)
        self.assertFalse(is_next_complete_prediction(start,end,
                         pd.Timestamp('2026-10-10T21:01:00+02:00').to_pydatetime()))

    def test_missing_hour_does_not_substitute_later_data(self):
        frame = self.frame()
        frame = frame[frame['forecast_hour'] != pd.Timestamp('2026-10-10T20:00Z')]
        result = six_hour_forecast(frame, pd.Timestamp('2026-10-10T20:29:00+02:00'))
        self.assertEqual(len(result), 5)
        self.assertEqual(result['time'].iloc[-1].hour, 2)

    def test_naive_clock_rejected(self):
        with self.assertRaises(ValueError):
            six_hour_forecast(self.frame(), pd.Timestamp('2026-10-10T20:29'))

    def test_interval_label_at_midnight(self):
        self.assertEqual(interval_label('2026-10-10T22:00Z'),
                         '10 Oct 2026 23:00 – 11 Oct 2026 00:00 SAST')

    def test_generation_is_not_target_or_retrieval(self):
        labels = timestamp_labels({'prediction_for':'2026-10-10T19:00Z',
                                   'prediction_generated_at':'2026-10-10T18:29Z',
                                   'forecast_retrieved_at':'2026-10-10T18:28Z'})
        self.assertIn('21:00:00', labels[TARGET_LABEL])
        self.assertIn('20:29:00', labels[GENERATED_LABEL])
        self.assertEqual(timestamp_labels({'prediction_for':'2026-10-10T19:00Z'})[GENERATED_LABEL],
                         'Unknown (legacy record)')

    def test_history_table_labels_target_and_generation(self):
        tree = ast.parse((ROOT/'16_dashboard.py').read_text(encoding='utf-8'))
        names = {'numeric_series','risk','render_history'}
        functions = [node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name in names]
        st = Mock()
        captured = {}
        theme = SimpleNamespace(table_html=lambda frame, **kw: captured.setdefault('frame', frame) is None or '')
        namespace = dict(pd=pd, math=math, st=st, SAST=SAST, timestamp_labels=timestamp_labels, dashboard_theme=theme,
                         TARGET_LABEL=TARGET_LABEL, GENERATED_LABEL=GENERATED_LABEL, threshold=.35)
        exec(compile(ast.Module(body=functions,type_ignores=[]), '<history table>', 'exec'), namespace)
        namespace['render_history'](pd.DataFrame([{
            'prediction_for':'2026-10-10T19:00Z', 'prediction_generated_at':'2026-10-10T18:29Z',
            'storm_probability':.0533, 'precipitation_mm':0.1}]))
        frame = captured['frame']  # rendered as a themed HTML table
        self.assertEqual(frame[TARGET_LABEL].tolist(), ['10 Oct 21:00'])  # target (hour ending), SAST
        self.assertIn('20:29:00', frame[GENERATED_LABEL].iloc[0])        # generation time shown separately
        self.assertEqual(frame['Risk'].tolist(), ['LOW'])

    def test_regional_map_does_not_fall_forward_to_later_hour(self):
        tree = ast.parse((ROOT/'16_dashboard.py').read_text(encoding='utf-8'))
        function = next(node for node in tree.body if isinstance(node, ast.FunctionDef)
                        and node.name == 'upcoming_regional')
        namespace = dict(pd=pd, SAST=SAST, UTC=UTC, next_complete_hour_endpoint=next_complete_hour_endpoint,
                         datetime=SimpleNamespace(now=lambda tz: pd.Timestamp('2026-10-10T20:29+02:00')))
        exec(compile(ast.Module(body=[function],type_ignores=[]), '<regional>', 'exec'), namespace)
        frame = pd.DataFrame({'sample_id':range(25), 'forecast_hour':'2026-10-10T21:00Z',
                              'precipitation_mm':0.0})
        result, endpoint = namespace['upcoming_regional'](frame)
        self.assertTrue(result.empty)
        self.assertIsNone(endpoint)
        frame['forecast_hour'] = '2026-10-10T20:00Z'
        result, endpoint = namespace['upcoming_regional'](frame)
        self.assertEqual(len(result), 25)
        self.assertEqual(endpoint.hour, 22)

    def test_forecast_chart_keeps_time_order_across_midnight(self):
        # Run the real chart function without importing the dashboard's refresh/SMS code.
        tree = ast.parse((ROOT/'16_dashboard.py').read_text(encoding='utf-8'))
        function = next(node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name == 'forecast_chart')
        st = MagicMock()
        frame = self.frame().assign(temperature_2m=12.0)
        clock = SimpleNamespace(now=lambda tz: pd.Timestamp('2026-10-10T20:29:00+02:00'))
        import dashboard_theme
        namespace = dict(pd=pd, alt=alt, st=st, SAST=SAST, UTC=UTC, datetime=clock, dashboard_theme=dashboard_theme, theme_mode='dark',
                         state=SimpleNamespace(regional=frame, regional_error=''))
        exec(compile(ast.Module(body=[function], type_ignores=[]), '<forecast chart>', 'exec'), namespace)
        namespace['forecast_chart']()
        chart = st.altair_chart.call_args.args[0].to_dict()
        x = chart['layer'][0]['encoding']['x']
        self.assertEqual(x['type'], 'temporal')  # a time axis: midnight cannot be reordered alphabetically
        hours = [row['Hour (SAST)'] for row in next(iter(chart['datasets'].values()))]
        self.assertEqual(hours, sorted(hours))
        self.assertEqual(len(hours), 8)  # only future hours: 21:00 SAST onwards
        self.assertEqual(chart['config']['axis']['labelColor'], '#a3b3c7')  # chart colours follow the selected (dark) theme
        self.assertIsNone(st.altair_chart.call_args.kwargs['theme'])

if __name__ == '__main__':
    unittest.main()
