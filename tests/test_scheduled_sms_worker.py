"""Fault injection only; no requests, inference, CSV writes or actual SMS."""
import contextlib
import importlib.util
import io
import os
from pathlib import Path
import subprocess
import unittest
from unittest.mock import patch

import pandas as pd
import requests

ROOT=Path(__file__).resolve().parents[1]


def load_worker():
    spec=importlib.util.spec_from_file_location('scheduled_worker',ROOT/'18_scheduled_sms_worker.py')
    module=importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class WorkerTests(unittest.TestCase):
    def setUp(self):
        self.env=patch.dict(os.environ,{'ENABLE_REAL_SMS':'true','GITHUB_ACTIONS':'true',
            'GITHUB_REPOSITORY':'example/research','GH_TOKEN':'test-only-token'})
        self.env.start();self.addCleanup(self.env.stop)
        self.worker=load_worker()
        self.now=pd.Timestamp.now(tz='UTC')
        self.row={'forecast_source':'Open-Meteo ECMWF','forecast_retrieved_at':self.now.isoformat(),
            'forecast_input_time':self.now.floor('h').isoformat(),
            'prediction_for':(self.now.floor('h')+pd.Timedelta(hours=1)).isoformat(),
            'storm_probability':.40,'decision_threshold':.35,'temperature_c':20,
            'dewpoint_c':15,'pressure_msl_hpa':1012,'precipitation_mm':1,
            'cape':500,'wind_gust_ms':10,'latitude':-30.30,'longitude':28.80}

    def run_main(self,module=None,args=None,rows=None):
        module=module or self.worker
        with patch.object(module.subprocess,'run') as inference, \
             patch.object(module.pd,'read_csv',return_value=pd.DataFrame(rows or [self.row])), \
             patch.object(module.PREDICTION.__class__,'is_file',return_value=True), \
             contextlib.redirect_stdout(io.StringIO()):
            module.main(args or [])
        return inference

    def test_dry_run_overrides_environment_and_never_calls_sms_or_ledger(self):
        with patch('sms_alert.send_storm_sms') as send,patch.object(self.worker,'github') as gh:
            self.run_main();self.run_main(args=['--dry-run'])
            send.assert_not_called();gh.assert_not_called()

    def test_live_flag_requires_activation(self):
        with patch.dict(os.environ,{'ENABLE_REAL_SMS':'false'}),patch.object(self.worker.subprocess,'run') as run:
            with self.assertRaises(self.worker.WorkerError):self.worker.main(['--live'])
            run.assert_not_called()

    def test_workflow_runs_approved_live_schedule_and_requires_explicit_connectivity_dispatch(self):
        workflow=(ROOT/'.github/workflows/scheduled-storm-sms.yml').read_text()
        self.assertIn('default: false',workflow)
        self.assertIn("ENABLE_REAL_SMS: 'true'",workflow)
        self.assertIn("if: ${{ github.event_name != 'workflow_dispatch' || inputs.send_test_sms != true }}",workflow)
        self.assertIn('run: python 18_scheduled_sms_worker.py --live',workflow)
        self.assertIn("if: ${{ github.event_name == 'workflow_dispatch' && inputs.send_test_sms == true }}",workflow)
        self.assertIn('run: python 18_scheduled_sms_worker.py --test-sms',workflow)
        self.assertIn('group: matatiele-hourly-sms',workflow)
        self.assertIn('cancel-in-progress: false',workflow)
        self.assertIn("SMS_TEST_CONFIRMED: ${{ github.event_name == 'workflow_dispatch' && inputs.send_test_sms == true }}",workflow)

    def test_forecast_failure_never_uses_saved_csv(self):
        with patch.object(self.worker.subprocess,'run',side_effect=subprocess.CalledProcessError(1,['inference'])),patch.object(self.worker.pd,'read_csv') as read,patch('sms_alert.send_storm_sms') as send:
            with self.assertRaises(self.worker.WorkerError):self.worker.main(['--dry-run'])
            read.assert_not_called();send.assert_not_called()

    def test_invalid_forecast_inputs_fail_closed(self):
        invalid=[{'storm_probability':float('nan')},{'precipitation_mm':float('inf')},
            {'cape':-1},{'decision_threshold':.5},{'forecast_source':'simulation'},
            {'forecast_retrieved_at':(self.now-pd.Timedelta(hours=1)).isoformat()},
            {'prediction_for':self.now.floor('h').isoformat()},
            {'forecast_input_time':'not-a-timestamp'},{'latitude':0}]
        for changed in invalid:
            with self.subTest(changed=changed),self.assertRaises(self.worker.WorkerError):
                self.worker.validate_prediction(pd.DataFrame([{**self.row,**changed}]),self.now,self.now)
        with self.assertRaises(self.worker.WorkerError):
            self.worker.validate_prediction(pd.DataFrame(),self.now,self.now)

    def test_missing_credentials_do_not_reserve(self):
        with patch('sms_alert.sms_is_configured',return_value=False),patch.object(self.worker,'reserve_hour') as reserve:
            with self.assertRaises(self.worker.WorkerError):self.run_main(args=['--live'])
            reserve.assert_not_called()

    def test_below_threshold_skips_ledger_and_sms(self):
        with patch('sms_alert.send_storm_sms') as send,patch.object(self.worker,'reserve_hour') as reserve:
            self.run_main(args=['--live'],rows=[{**self.row,'storm_probability':.10}])
            send.assert_not_called();reserve.assert_not_called()

    def test_github_errors_are_sanitized(self):
        with patch.object(self.worker.requests,'request',side_effect=requests.ConnectionError('SECRET phone=private')):
            with self.assertRaises(self.worker.WorkerError) as error:self.worker.github('GET','issues')
            self.assertNotIn('SECRET',str(error.exception));self.assertNotIn('private',str(error.exception))

    def test_duplicate_protection_across_fresh_workers_even_after_failure(self):
        # Repository-owned ledger persists, whereas worker modules are reloaded.
        for outcome in [{'status':'sent'}, {'status':'failed','message':'SECRET'}, RuntimeError('SECRET')]:
            with self.subTest(outcome=outcome):
                ledger=[];comments=[]
                def github(method,endpoint,**kwargs):
                    if method=='GET':return list(ledger)
                    if endpoint=='issues':
                        ledger.append({'number':1,'title':kwargs['json']['title'],'state':'closed'})
                        return ledger[-1]
                    comments.append(kwargs['json']['body']);return {}
                first=load_worker();second=load_worker()
                with patch.object(first,'github',side_effect=github),patch.object(second,'github',side_effect=github),patch('sms_alert.sms_is_configured',return_value=True),patch('sms_alert.send_storm_sms') as send:
                    if isinstance(outcome,Exception):send.side_effect=outcome
                    else:send.return_value=outcome
                    if outcome=={'status':'sent'}:self.run_main(first,['--live'])
                    else:
                        with self.assertRaises(first.WorkerError):self.run_main(first,['--live'])
                    self.run_main(second,['--live'])
                    self.assertEqual(send.call_count,1);self.assertEqual(len(ledger),1)
                    self.assertNotIn('SECRET',' '.join(comments))

    def test_ledger_pagination_includes_closed_reservations(self):
        title='[SMS-LEDGER] key'
        with patch.object(self.worker,'github',side_effect=[[{'title':'other'}]*100,[{'title':title,'state':'closed'}]]) as gh:
            self.assertIsNone(self.worker.reserve_hour('key'))
            self.assertEqual(gh.call_count,2)
            self.assertTrue(all(call.args[0]=='GET' for call in gh.call_args_list))

    def test_failed_reservation_never_calls_sms(self):
        with patch('sms_alert.sms_is_configured',return_value=True),patch.object(self.worker,'reserve_hour',side_effect=self.worker.WorkerError('ledger failed')),patch('sms_alert.send_storm_sms') as send:
            with self.assertRaises(self.worker.WorkerError):self.run_main(args=['--live'])
            send.assert_not_called()


if __name__=='__main__':unittest.main()
