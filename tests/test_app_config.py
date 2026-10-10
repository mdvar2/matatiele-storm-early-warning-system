"""Placeholder-only configuration tests; never access real Twilio or secrets."""
import os
import ast
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock, patch

import app_config as config
import sms_alert as sms

ROOT = Path(__file__).resolve().parents[1]
VALUES = {'ADMIN_PASSWORD':'test-only-password','TWILIO_ACCOUNT_SID':'test-only-sid',
          'TWILIO_AUTH_TOKEN':'test-only-token','TWILIO_FROM_NUMBER':'+15555550100',
          'ALERT_TO_NUMBERS':'+15555550101,+15555550102'}


class ConfigTests(unittest.TestCase):
    def setUp(self):
        temp=tempfile.TemporaryDirectory(prefix='config-test-',dir=ROOT/'outputs')
        self.addCleanup(temp.cleanup)
        self.file=Path(temp.name)/'secrets.toml'
        for context in [patch.object(config,'LOCAL_SECRETS',self.file),
                        patch.object(config,'get_script_run_ctx',return_value=object()),
                        patch.object(config.st,'secrets',{}),
                        patch.dict(os.environ,{},clear=True)]:
            context.start();self.addCleanup(context.stop)

    def write(self,values):
        self.file.write_text('\n'.join(f'{key} = "{value}"' for key,value in values.items()),encoding='utf-8')

    def test_all_five_keys_load_from_local_file(self):
        self.write(VALUES)
        for key,value in VALUES.items():self.assertEqual(config.get_setting(key),value)
        self.assertTrue(sms.sms_is_configured())
        self.assertEqual(len(sms._get_recipients()),2)

    def test_file_values_take_precedence_over_environment(self):
        self.write(VALUES)
        with patch.dict(os.environ,{'ADMIN_PASSWORD':'other-test-password'}):
            self.assertEqual(config.get_setting('ADMIN_PASSWORD'),VALUES['ADMIN_PASSWORD'])

    def test_missing_and_empty_file_keys_fall_back_to_environment(self):
        self.write({'ADMIN_PASSWORD':'','TWILIO_ACCOUNT_SID':'test-only-sid'})
        with patch.dict(os.environ,VALUES):
            for key,value in VALUES.items():self.assertEqual(config.get_setting(key),value)

    def test_missing_file_environment_fallback(self):
        with patch.dict(os.environ,VALUES):self.assertTrue(sms.sms_is_configured())

    def test_misplaced_nested_file_is_not_a_standard_streamlit_secrets_file(self):
        misplaced=self.file.parent/'.streamlit'/'secrets.toml'
        misplaced.parent.mkdir()
        misplaced.write_text('\n'.join(f'{key} = "{value}"' for key,value in VALUES.items()),encoding='utf-8')
        self.assertFalse(sms.sms_is_configured())
        misplaced.rename(self.file)
        self.assertTrue(sms.sms_is_configured())

    def test_admin_password_does_not_imply_valid_twilio_sender(self):
        self.write({**VALUES,'TWILIO_FROM_NUMBER':'+1 555-555-0100'})
        self.assertEqual(config.get_setting('ADMIN_PASSWORD'),VALUES['ADMIN_PASSWORD'])
        self.assertFalse(sms.sms_is_configured())
        self.write(VALUES)
        self.assertTrue(sms.sms_is_configured())

    def test_native_streamlit_secrets_without_local_file(self):
        with patch.object(config.st,'secrets',VALUES):
            self.assertTrue(sms.sms_is_configured())
            self.assertEqual(config.get_setting('ADMIN_PASSWORD'),VALUES['ADMIN_PASSWORD'])

    def test_missing_configuration_never_initialises_twilio(self):
        with patch('twilio.rest.Client') as client:
            self.assertFalse(sms.sms_is_configured())
            self.assertIsNone(sms._create_twilio_client())
            client.assert_not_called()

    def test_invalid_toml_fails_without_exposing_values(self):
        self.file.write_text('ADMIN_PASSWORD = "unterminated',encoding='utf-8')
        self.assertEqual(config.get_setting('ADMIN_PASSWORD'),'')
        self.assertFalse(sms.sms_is_configured())

    def test_cli_and_actions_keep_environment_only_configuration(self):
        self.write(VALUES)
        with patch.object(config,'get_script_run_ctx',return_value=None),patch.dict(os.environ,{'GITHUB_ACTIONS':'true'}):
            self.assertFalse(sms.sms_is_configured())
            with patch.dict(os.environ,VALUES):self.assertTrue(sms.sms_is_configured())

    def test_twilio_factory_uses_secrets_without_submitting_messages(self):
        self.write(VALUES)
        with patch('twilio.rest.Client') as client:
            sms._create_twilio_client()
            client.assert_called_once_with(VALUES['TWILIO_ACCOUNT_SID'],VALUES['TWILIO_AUTH_TOKEN'])
            client.return_value.messages.create.assert_not_called()

    def test_placeholder_example_is_valid_and_contains_no_credentials(self):
        import tomllib
        example=ROOT/'.streamlit/secrets.toml.example'
        with example.open('rb') as handle:values=tomllib.load(handle)
        self.assertEqual(set(values),set(VALUES))
        self.assertTrue(all(value=='' for value in values.values()))

    def test_configured_admin_sees_test_button_only_with_preview_off(self):
        self.write(VALUES)
        tree=ast.parse((ROOT/'16_dashboard.py').read_text(encoding='utf-8'))
        sidebar=next(n for n in tree.body if isinstance(n,ast.With)
                     and any(isinstance(c,ast.Call) and isinstance(c.func,ast.Name)
                             and c.func.id=='send_test_sms' for c in ast.walk(n)))
        guard=next(n for n in sidebar.body if isinstance(n,ast.If)
                   and any(isinstance(c,ast.Call) and isinstance(c.func,ast.Name)
                           and c.func.id=='send_test_sms' for c in ast.walk(n)))
        for admin,preview in [(False,False),(True,True),(True,False)]:
            st=Mock();st.toggle.return_value=preview;st.button.return_value=False
            send=Mock()
            namespace={'st':st,'is_admin':admin,'sms_is_configured':sms.sms_is_configured,'send_test_sms':send}
            exec(compile(ast.Module(body=[guard],type_ignores=[]),'<configured admin controls>','exec'),namespace)
            buttons=[call.args[0] for call in st.button.call_args_list]
            self.assertEqual(any('Send Test SMS' in label for label in buttons),admin and not preview)
            send.assert_not_called()


if __name__=='__main__':unittest.main()
