"""Isolated Twilio integration tests: dummy credentials, temporary logs, no network."""
import ast
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock, patch

import sms_alert as sms

ROOT = Path(__file__).resolve().parents[1]


class _State(dict):
    __getattr__ = dict.get

    def __setattr__(self, key, value):
        self[key] = value


def run_sms_panel(state, simulation, clicks, session=None):
    """Run the dashboard's sms_provider_panel with a mocked Streamlit; returns (send mock, st mock, session)."""
    import pandas as pd
    tree = ast.parse((ROOT / '16_dashboard.py').read_text(encoding='utf-8'))
    panel = next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == 'sms_provider_panel')
    st = Mock(); st.session_state = session if session is not None else _State()
    st.button.side_effect = lambda label, key=None, **kw: key in clicks and not kw.get('disabled')
    column = Mock(); column.button.side_effect = st.button.side_effect
    st.columns.return_value = (column, column)
    send = Mock(return_value={'status': 'queued', 'sent': True, 'message': 'Accepted by provider (not yet delivered).'})
    alert = Mock(CONTROLLED_STATES=sms.CONTROLLED_STATES, send_controlled_test_sms=send,
                 provider_health=Mock(return_value={'provider': 'Configured', 'controlled_test': state, 'public_delivery': 'Disabled', 'last_test': None}))
    namespace = {'st': st, 'sms_alert': alert, 'test_mode': simulation, 'pd': pd, 'SAST': None, 'dashboard_theme': Mock()}
    exec(compile(ast.Module(body=[panel], type_ignores=[]), '<sms provider panel>', 'exec'), namespace)
    namespace['sms_provider_panel']()
    return send, st, st.session_state


class SmsTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='sms-test-',dir=ROOT/'outputs')
        self.addCleanup(self.temp.cleanup)
        log = patch.object(sms,'SMS_LOG_FILE',Path(self.temp.name)/'sms.csv')
        log.start(); self.addCleanup(log.stop)
        env = patch.dict(sms.os.environ,{
            'TWILIO_ACCOUNT_SID':'test-only-account','TWILIO_AUTH_TOKEN':'test-only-token',
            'TWILIO_FROM_NUMBER':'+15555550100','ALERT_TO_NUMBERS':'+15555550101'},clear=True)
        env.start(); self.addCleanup(env.stop)
        self.client = Mock()
        self.client.messages.create.return_value = Mock(sid='SM-test-only',status='queued')
        self.client.messages.return_value.fetch.return_value = Mock(status='queued')
        client = patch.object(sms,'_create_twilio_client',return_value=self.client)
        client.start(); self.addCleanup(client.stop)

    def send(self, probability=.35, target='2026-10-10T19:00:00Z', **kwargs):
        return sms.send_storm_sms(target,probability,**kwargs)

    def test_below_threshold_never_submits(self):
        self.assertEqual(self.send(.349999)['status'],'not_required')
        self.client.messages.create.assert_not_called()

    def test_exact_threshold_submits_real_warning(self):
        result = self.send()
        self.assertTrue(result['sent'])
        self.assertIn('Delivery not yet confirmed',result['message'])
        self.assertEqual(self.client.messages.create.call_count,1)
        body = self.client.messages.create.call_args.kwargs['body']
        for text in ['MATATIELE','10 Oct 20:00-21:00 SAST','Storm risk 35%',
                     'stay indoors','lightning','flooded roads','SAWS']:
            self.assertIn(text,body)

    def test_invalid_probabilities_and_thresholds_fail_closed(self):
        for value in [float('nan'),float('inf'),-1,1.1,'invalid',None]:
            with self.subTest(value=value):self.assertFalse(self.send(value)['sent'])
        for value in [.34,.5,float('nan')]:
            self.assertFalse(self.send(threshold=value)['sent'])
        self.client.messages.create.assert_not_called()

    def test_invalid_targets_and_other_locations_fail_closed(self):
        for target in ['invalid','',None,'2026-10-10T19:15:00Z']:
            self.assertFalse(self.send(target=target)['sent'])
        self.assertFalse(self.send(location='Other town')['sent'])
        self.client.messages.create.assert_not_called()

    def test_recipient_validation_rejects_entire_configuration(self):
        for recipient in ['','123','+0123456789','+15555550101,invalid', '+1234567890123456']:
            with patch.dict(sms.os.environ,{'ALERT_TO_NUMBERS':recipient}):
                self.assertFalse(sms.sms_is_configured())
                self.assertFalse(self.send()['sent'])
        self.client.messages.create.assert_not_called()

    def test_invalid_sender_is_not_configured(self):
        with patch.dict(sms.os.environ,{'TWILIO_FROM_NUMBER':'invalid'}):
            self.assertFalse(self.send()['sent'])
        self.client.messages.create.assert_not_called()

    def test_multiple_recipients_are_deduplicated(self):
        with patch.dict(sms.os.environ,{'ALERT_TO_NUMBERS':'+15555550101,+15555550102,+15555550101'}):
            self.assertTrue(self.send()['sent'])
        self.assertEqual(self.client.messages.create.call_count,2)

    def test_missing_credentials_prevent_submission(self):
        with patch.dict(sms.os.environ,{'TWILIO_AUTH_TOKEN':''}):
            self.assertEqual(self.send()['status'],'not_configured')
        self.client.messages.create.assert_not_called()

    def test_repeat_pending_target_and_equivalent_timezone_are_duplicates(self):
        self.send()
        self.assertEqual(self.send(target='2026-10-10T21:00:00+02:00')['status'],'duplicate')
        self.assertEqual(self.client.messages.create.call_count,1)

    def test_delivered_receipt_is_logged_and_not_resent(self):
        self.send()
        self.client.messages.return_value.fetch.return_value = Mock(status='delivered',error_code=None)
        self.assertEqual(self.send()['status'],'duplicate')
        self.assertEqual(sms._read_log()[-1]['status'],'delivered')
        self.assertEqual(self.client.messages.create.call_count,1)

    def test_delivery_fetch_failure_does_not_resend(self):
        self.send()
        self.client.messages.return_value.fetch.side_effect=RuntimeError('network unavailable')
        self.assertEqual(self.send()['status'],'duplicate')
        self.assertEqual(self.client.messages.create.call_count,1)

    def test_unrecognised_or_missing_provider_acceptance_is_not_reported_successful(self):
        for message in [Mock(sid='',status='queued'),Mock(sid='SM-test',status='unknown')]:
            self.client.messages.create.return_value=message
            target='2026-10-10T19:00Z' if not message.sid else '2026-10-10T20:00Z'
            self.assertFalse(self.send(target=target)['sent'])
            self.assertEqual(self.send(target=target)['status'],'duplicate')
        self.assertEqual(self.client.messages.create.call_count,2)

    def test_explicit_failed_delivery_can_be_retried(self):
        self.send()
        self.client.messages.return_value.fetch.return_value=Mock(status='undelivered',error_code=30003)
        self.assertTrue(self.send()['sent'])
        self.assertEqual(self.client.messages.create.call_count,2)

    def test_partial_recipient_failure_reports_partial_not_success(self):
        with patch.dict(sms.os.environ,{'ALERT_TO_NUMBERS':'+15555550101,+15555550102'}):
            self.client.messages.create.side_effect=[Mock(sid='SM-1',status='queued'),Mock(sid='SM-2',status='failed')]
            result=self.send()
        self.assertFalse(result['sent'])
        self.assertEqual(result['status'], 'partial')
        self.assertEqual(result['submitted'], 1)
        self.assertEqual(result['failed_or_uncertain'], 1)
        self.assertIn('1 of 2',result['message'])
        self.assertEqual(sms._read_log()[-1]['status'],'failed')

    def test_uncertain_submission_is_reserved_and_never_automatically_retried(self):
        self.client.messages.create.side_effect=TimeoutError('SECRET private phone')
        self.assertFalse(self.send()['sent'])
        self.assertEqual(self.send()['status'],'duplicate')
        self.assertEqual(self.client.messages.create.call_count,1)
        self.assertNotIn('SECRET',sms.SMS_LOG_FILE.read_text())
        self.assertNotIn('private phone',sms.SMS_LOG_FILE.read_text())

    def test_definite_provider_rejection_is_retryable(self):
        from twilio.base.exceptions import TwilioRestException
        self.client.messages.create.side_effect=TwilioRestException(400,'private-uri',msg='SECRET',code=21211)
        self.assertFalse(self.send()['sent'])
        self.assertEqual(sms._read_log()[-1]['status'],'failed')
        self.client.messages.create.side_effect=None
        self.assertTrue(self.send()['sent'])
        self.assertNotIn('SECRET',sms.SMS_LOG_FILE.read_text())

    def test_reservation_write_failure_blocks_provider_call(self):
        with patch.object(sms,'_log_attempt',side_effect=OSError('disk unavailable')):
            self.assertFalse(self.send()['sent'])
        self.client.messages.create.assert_not_called()

    def test_log_write_failure_after_acceptance_preserves_reservation(self):
        original=sms._log_attempt
        def log(*args,**kwargs):
            if args[3] != 'reserved':raise OSError('disk unavailable')
            return original(*args,**kwargs)
        with patch.object(sms,'_log_attempt',side_effect=log):
            self.assertFalse(self.send()['sent'])
        self.assertEqual(self.send()['status'],'duplicate')
        self.assertEqual(self.client.messages.create.call_count,1)

    def test_corrupt_history_blocks_provider_call(self):
        sms.SMS_LOG_FILE.write_text('invalid,header\n')
        self.assertFalse(self.send()['sent'])
        self.client.messages.create.assert_not_called()

    def test_test_sms_uses_provider_and_is_not_a_weather_warning(self):
        result=sms.send_test_sms()
        self.assertEqual(result['status'],'test_sent')
        body=self.client.messages.create.call_args.kwargs['body']
        self.assertIn('NO WEATHER WARNING',body)
        self.assertIn('MATATIELE SMS TEST',body)
        self.assertNotIn('Storm risk',body)

    def test_manual_actions_connectivity_uses_existing_test_message_and_reserves_reruns(self):
        from test_scheduled_sms_worker import load_worker
        with patch.dict(sms.os.environ, {'GITHUB_ACTIONS':'true', 'GITHUB_EVENT_NAME':'workflow_dispatch',
                'SMS_TEST_CONFIRMED':'true', 'GITHUB_RUN_ID':'12345',
                'GITHUB_REPOSITORY':'example/research', 'GH_TOKEN':'dummy-only', 'ENABLE_REAL_SMS':'false'}):
            worker=load_worker()
            with patch.object(worker,'reserve_hour',side_effect=[1,None]) as reserve, \
                 patch.object(worker,'report') as report, patch.object(worker.subprocess,'run') as inference, \
                 patch.object(sms,'send_storm_sms') as storm:
                worker.main(['--test-sms'])
                worker.main(['--test-sms'])
                self.assertEqual(reserve.call_args.args[0],'CONNECTIVITY-TEST-RUN-12345')
                report.assert_called_once()
                inference.assert_not_called()
                storm.assert_not_called()
        self.client.messages.create.assert_called_once()
        self.assertEqual(self.client.messages.create.call_args.kwargs['body'],
                         'MATATIELE SMS TEST. Notification service check only. NO WEATHER WARNING.')

    def test_manual_actions_connectivity_rejects_schedule_unconfirmed_and_multiple_recipients(self):
        from test_scheduled_sms_worker import load_worker
        base={'GITHUB_ACTIONS':'true','GITHUB_EVENT_NAME':'workflow_dispatch','SMS_TEST_CONFIRMED':'true',
              'GITHUB_RUN_ID':'12345','GITHUB_REPOSITORY':'example/research','GH_TOKEN':'dummy-only'}
        for changed in [{'GITHUB_EVENT_NAME':'schedule'}, {'SMS_TEST_CONFIRMED':'false'},
                        {'GITHUB_ACTIONS':'false'}, {'GITHUB_RUN_ID':''},
                        {'ALERT_TO_NUMBERS':'+15555550101,+15555550102'}, {'TWILIO_AUTH_TOKEN':''}]:
            with self.subTest(changed=changed),patch.dict(sms.os.environ,{**base,**changed}):
                worker=load_worker()
                with patch.object(worker,'reserve_hour') as reserve:
                    with self.assertRaises(worker.WorkerError):worker.main(['--test-sms'])
                    reserve.assert_not_called()
        self.client.messages.create.assert_not_called()

    def test_connectivity_uncertainty_does_not_retry_within_worker(self):
        from test_scheduled_sms_worker import load_worker
        with patch.dict(sms.os.environ, {'GITHUB_ACTIONS':'true','GITHUB_EVENT_NAME':'workflow_dispatch',
                'SMS_TEST_CONFIRMED':'true','GITHUB_RUN_ID':'12345',
                'GITHUB_REPOSITORY':'example/research','GH_TOKEN':'dummy-only'}):
            worker=load_worker()
            self.client.messages.create.side_effect=TimeoutError('private provider error')
            with patch.object(worker,'reserve_hour',side_effect=[1,None]),patch.object(worker,'report'):
                with self.assertRaises(worker.WorkerError):worker.main(['--test-sms'])
                worker.main(['--test-sms'])
        self.client.messages.create.assert_called_once()

    def test_actual_twilio_constructor_is_used_without_network(self):
        with patch('twilio.rest.Client') as constructor:
            # setUp replaces the factory; call its original implementation through
            # an isolated AST definition to verify the actual production factory.
            tree=ast.parse((ROOT/'sms_alert.py').read_text())
            fn=next(n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name=='_create_twilio_client')
            namespace={'sms_is_configured':sms.sms_is_configured,'get_setting':sms.get_setting}
            exec(compile(ast.Module(body=[fn],type_ignores=[]),'<factory>','exec'),namespace)
            namespace['_create_twilio_client']()
            constructor.assert_called_once_with('test-only-account','test-only-token')

    def test_midnight_message_contains_both_dates(self):
        self.send(target='2026-10-10T22:00:00Z')
        body=self.client.messages.create.call_args.kwargs['body']
        self.assertIn('10 Oct 23:00-11 Oct 00:00 SAST',body)

    @unittest.skipUnless((ROOT/'outputs/model_live/live_model_test_predictions.csv').is_file(),
                         'Historical evaluation predictions are not included in every checkout')
    def test_threshold_with_recomputed_genuine_random_forest_outputs(self):
        import joblib
        import pandas as pd
        model_dir=ROOT/'outputs/model_live'
        frame=pd.read_csv(model_dir/'live_model_test_predictions.csv')
        # These are genuine historical evaluation rows, NOT current forecasts.
        frame=frame[(frame['latitude']==-30.25) & (frame['longitude']==28.75)]
        model=joblib.load(model_dir/'random_forest_live_model.pkl')
        features=(model_dir/'live_model_features.txt').read_text().splitlines()
        for above in [False,True]:
            eligible=frame[frame['live_model_probability'].ge(.35)==above]
            self.assertFalse(eligible.empty)
            row=eligible.iloc[0]
            inputs=pd.DataFrame([row[features].to_dict()],columns=features)
            probability=float(model.predict_proba(inputs)[0][1])
            self.assertAlmostEqual(probability,float(row['live_model_probability']))
            target=pd.to_datetime(row['valid_time'],utc=True)+pd.Timedelta(hours=1)
            result=self.send(probability,target=target.isoformat())
            self.assertEqual(result['sent'],above)
        self.assertEqual(self.client.messages.create.call_count,1)

    def test_dashboard_cannot_send_storm_warnings(self):
        tree=ast.parse((ROOT/'16_dashboard.py').read_text(encoding='utf-8'))
        calls=[n.func.id for n in ast.walk(tree) if isinstance(n,ast.Call) and isinstance(n.func,ast.Name)]
        self.assertNotIn('send_storm_sms',calls)
        self.assertNotIn('send_simulated_storm_sms',calls)
        self.assertNotIn('send_test_sms',calls)  # the dashboard-local test to the warning recipients was replaced
        attributes=[n.func.attr for n in ast.walk(tree) if isinstance(n,ast.Call) and isinstance(n.func,ast.Attribute)]
        self.assertIn('send_controlled_test_sms',attributes)  # the only sending call: one SMS to the allowlisted test phone
        imports=[alias.name for n in ast.walk(tree) if isinstance(n,ast.ImportFrom) and n.module=='sms_alert' for alias in n.names]
        self.assertNotIn('send_storm_sms',imports)

    def test_partial_uncertain_recipient_is_not_retried(self):
        with patch.dict(sms.os.environ,{'ALERT_TO_NUMBERS':'+15555550101,+15555550102'}):
            self.client.messages.create.side_effect=[Mock(sid='SM-1',status='queued'),TimeoutError('mock timeout')]
            result=self.send()
            self.assertEqual(result['status'],'partial')
            self.assertFalse(result['sent'])
            self.assertEqual(self.send()['status'],'duplicate')
        self.assertEqual(self.client.messages.create.call_count,2)

    def test_legacy_validator_only_runs_mocked_worker_tests(self):
        import importlib.util
        spec=importlib.util.spec_from_file_location('legacy_validator',ROOT/'17_validate_warning_pipeline.py')
        module=importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        with patch.object(module.subprocess,'run',return_value=Mock(returncode=0)) as run, patch.object(sms,'send_storm_sms') as send:
            self.assertEqual(module.main(),0)
            command=run.call_args.args[0]
            self.assertIn('test_scheduled_sms_worker.py',command)
            send.assert_not_called()

    def test_controlled_test_needs_ready_configuration_no_simulation_and_a_second_confirmation(self):
        for state, simulation, clicks, sends in [('ready', False, {'sms_test_ask'}, 0),            # first click only asks
                                                 ('disabled', False, {'sms_test_ask', 'sms_test_yes'}, 0),
                                                 ('not_configured', False, {'sms_test_ask', 'sms_test_yes'}, 0),
                                                 ('invalid_recipient', False, {'sms_test_ask', 'sms_test_yes'}, 0),
                                                 ('ready', True, {'sms_test_ask', 'sms_test_yes'}, 0),    # simulation on
                                                 ('ready', False, {'sms_test_ask', 'sms_test_yes'}, 1)]:
            with self.subTest(state=state, simulation=simulation, clicks=clicks):
                send, st, _ = run_sms_panel(state, simulation, clicks)
                self.assertEqual(send.call_count, sends)
                for call in send.call_args_list:
                    self.assertEqual(call.kwargs, {'confirmed': True}); self.assertEqual(call.args, ())  # no number, ever
        _, st, session = run_sms_panel('ready', False, {'sms_test_ask'})
        self.assertIn('This will send one real SMS to the configured test recipient. Continue?', [c.args[0] for c in st.warning.call_args_list])
        send, _, _ = run_sms_panel('ready', False, {'sms_test_no'}, session)                # cancelled
        self.assertEqual(send.call_count, 0); self.assertFalse(session['sms_test_confirm'])
        self.assertFalse(any(c.args and 'text_input' in str(c) for c in st.mock_calls))     # no phone-number entry
        st.text_input.assert_not_called()


class ControlledLiveTest(unittest.TestCase):
    """The controlled live test: one real SMS to the allowlisted test recipient only (all mocked here, nothing sent)."""

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='sms-controlled-', dir=ROOT / 'outputs')
        self.addCleanup(self.temp.cleanup)
        self.log = Path(self.temp.name) / 'sms.csv'
        patcher = patch.object(sms, 'SMS_LOG_FILE', self.log); patcher.start(); self.addCleanup(patcher.stop)
        self.env = {'TWILIO_ACCOUNT_SID': 'test-only-account', 'TWILIO_AUTH_TOKEN': 'test-only-secret', 'TWILIO_FROM_NUMBER': '+15555550100',
                    'ALERT_TO_NUMBERS': '+15555550101', 'SMS_LIVE_TEST_ENABLED': 'true', 'SMS_TEST_RECIPIENT': '+15555550109'}
        self.client = Mock()
        self.client.messages.create.return_value = Mock(sid='SM-controlled', status='queued')

    def use(self, **changes):
        env = patch.dict(sms.os.environ, {k: v for k, v in {**self.env, **changes}.items() if v is not None}, clear=True)
        env.start(); self.addCleanup(env.stop)

    def test_states_and_disabled_or_unconfirmed_never_reach_the_provider(self):
        for changes, state in [({'SMS_LIVE_TEST_ENABLED': None}, 'disabled'), ({'SMS_LIVE_TEST_ENABLED': 'false'}, 'disabled'),
                               ({'TWILIO_AUTH_TOKEN': None}, 'not_configured'), ({'SMS_TEST_RECIPIENT': None}, 'invalid_recipient'),
                               ({'SMS_TEST_RECIPIENT': '+15555550109,+15555550101'}, 'invalid_recipient'),   # one allowlisted number only
                               ({'SMS_TEST_RECIPIENT': '0821234567'}, 'invalid_recipient'), ({}, 'ready')]:
            with self.subTest(changes=changes):
                with patch.dict(sms.os.environ, {k: v for k, v in {**self.env, **changes}.items() if v is not None}, clear=True):
                    self.assertEqual(sms.controlled_test_state(), state)
                    if state != 'ready':
                        self.assertEqual(sms.send_controlled_test_sms(confirmed=True, client=self.client)['status'], state)
                    self.assertEqual(sms.send_controlled_test_sms(confirmed=False, client=self.client)['sent'], False)
        self.client.messages.create.assert_not_called()

    def test_sends_once_to_the_test_recipient_only_and_never_logs_the_number(self):
        self.use()
        result = sms.send_controlled_test_sms(confirmed=True, client=self.client)
        self.assertEqual((result['status'], result['sent']), ('queued', True))
        self.assertEqual(result['message'], 'Accepted by provider (not yet delivered).')   # not "delivered"
        self.client.messages.create.assert_called_once()
        call = self.client.messages.create.call_args.kwargs
        self.assertEqual(call['to'], '+15555550109')
        self.assertIn('NOT A WEATHER WARNING', call['body'])
        log = self.log.read_text(encoding='utf-8')
        for private in ('+15555550109', '+15555550101', 'test-only-secret'):
            self.assertNotIn(private, log)
        self.assertNotIn('+15555550109', str(sms.provider_health()))
        self.assertEqual(sms.last_controlled_test()['status'], 'queued')

    def test_provider_failure_and_uncertainty_are_recorded_honestly(self):
        self.use()
        rejected = Exception('rejected'); rejected.status = 400; rejected.code = 21608
        self.client.messages.create.side_effect = rejected
        self.assertEqual(sms.send_controlled_test_sms(confirmed=True, client=self.client)['status'], 'failed')
        self.client.messages.create.side_effect = TimeoutError('timeout')
        result = sms.send_controlled_test_sms(confirmed=True, client=self.client)
        self.assertEqual(result['status'], 'submission_unknown')
        self.assertIn('uncertain', result['message'])
        self.assertEqual(sms.last_controlled_test()['label'], 'Outcome uncertain: check the provider console before trying again')

    def test_delivery_is_reported_only_when_the_provider_confirms_it(self):
        self.use()
        sms.send_controlled_test_sms(confirmed=True, client=self.client)
        self.client.messages.return_value.fetch.return_value = Mock(status='sent', error_code=None)
        self.assertEqual(sms.refresh_controlled_test_status(self.client), 'sent')
        self.assertNotIn('Delivered', sms.last_controlled_test()['label'])
        self.client.messages.return_value.fetch.return_value = Mock(status='delivered', error_code=None)
        self.assertEqual(sms.refresh_controlled_test_status(self.client), 'delivered')
        self.assertEqual(sms.last_controlled_test()['label'], 'Delivered to handset (confirmed by the provider)')
        for status, label in [('queued', 'Accepted by provider (not yet delivered)'), ('accepted', 'Accepted by provider (not yet delivered)'),
                              ('undelivered', 'Failed'), ('failed', 'Failed'), ('', 'Unknown')]:
            self.assertEqual(sms.delivery_label(status), label)

    def test_health_reports_public_delivery_disabled_by_default_and_trial_accounts(self):
        self.use()
        health = sms.provider_health()
        self.assertEqual((health['provider'], health['controlled_test'], health['public_delivery']), ('Configured', 'ready', 'Disabled'))
        self.client.api.v2010.accounts.return_value.fetch.return_value = Mock(type='Trial')
        self.assertEqual(sms.provider_account_type(self.client), 'Trial')
        self.client.api.v2010.accounts.return_value.fetch.side_effect = RuntimeError('network')
        self.assertEqual(sms.provider_account_type(self.client), 'Unknown')


if __name__ == '__main__':
    unittest.main()
