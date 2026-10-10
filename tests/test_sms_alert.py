"""Isolated Twilio integration tests: dummy credentials, temporary logs, no network."""
import ast
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock, patch

import sms_alert as sms

ROOT = Path(__file__).resolve().parents[1]


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
        self.assertIn('send_test_sms',calls)
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

    def test_dashboard_test_button_requires_admin_and_disables_simulation_sending(self):
        tree=ast.parse((ROOT/'16_dashboard.py').read_text(encoding='utf-8'))
        sidebar=next(n for n in tree.body if isinstance(n,ast.With)
                     and any(isinstance(c,ast.Call) and isinstance(c.func,ast.Name)
                             and c.func.id=='send_test_sms' for c in ast.walk(n)))
        guard=next(n for n in sidebar.body if isinstance(n,ast.If)
                   and any(isinstance(c,ast.Call) and isinstance(c.func,ast.Name)
                           and c.func.id=='send_test_sms' for c in ast.walk(n)))
        for admin,simulation,configured,clicked in [(False,False,True,True),(True,True,True,True),
                                                    (True,False,False,True),(True,False,True,False),
                                                    (True,False,True,True)]:
            st=Mock();st.toggle.return_value=simulation;st.button.return_value=clicked
            send=Mock(return_value={'sent':True})
            namespace={'st':st,'is_admin':admin,'sms_is_configured':lambda:configured,'send_test_sms':send}
            exec(compile(ast.Module(body=[guard],type_ignores=[]),'<dashboard test SMS guard>','exec'),namespace)
            self.assertEqual(send.call_count,int(admin and not simulation and configured and clicked))


if __name__ == '__main__':
    unittest.main()
