"""Unit tests with mocked API calls; these are NOT a real GitLab E2E test."""
import argparse
import contextlib
import copy
import io
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch
from lab import cli
from lab.api import APIError
from lab.storage import read_json, write_json

def state_fixture(phase='prepared'):
    return {'gitlab_version': '19.4.1', 'groups': {'root': 10, 'artifacts': 11},
        'projects': {'automation': 20, 'config': 21, 'packages': 22, 'deployment': 23}, 'schedule_id': 50,
        'baseline': {'status': 'success'}, 'roles': {
            'reader': {'phase': phase, 'legacy': {'user_id': 101, 'token_id': 201}, 'native': {'user_id': 102, 'token_id': 202},
                       'before': {'direct': [], 'effective': []}},
            'publisher': {'phase': 'seeded', 'legacy': {'user_id': 103}},
            'deployer': {'phase': 'seeded', 'legacy': {'user_id': 104}}}}

class GuardTests(unittest.TestCase):
    def test_one_account_at_a_time(self):
        state = state_fixture(); state['roles']['publisher']['phase'] = 'switched'
        with self.assertRaises(ValueError): cli.ensure_exclusive(state, 'reader')
    def test_retired_accounts_dont_block(self):
        state = state_fixture(); state['roles']['publisher']['phase'] = 'retired'
        cli.ensure_exclusive(state, 'reader')
    def test_active_side_legacy_before_cutover(self):
        self.assertEqual(cli.active_side({'phase': 'prepared'}), 'legacy')
    def test_active_side_native_after_cutover(self):
        self.assertEqual(cli.active_side({'phase': 'switched'}), 'native')
    def test_active_side_rollback(self):
        self.assertEqual(cli.active_side({'phase': 'rolling_back'}), 'legacy')
    def test_unsafe_retire_rejected(self):
        with patch.object(cli, 'load', return_value=state_fixture('switched')):
            with self.assertRaises(ValueError): cli.cmd_retire(argparse.Namespace(role='reader', confirm='reader'))
    def test_missing_confirmation_rejected(self):
        with patch.object(cli, 'load', return_value=state_fixture('validated')):
            with self.assertRaises(ValueError): cli.cmd_retire(argparse.Namespace(role='reader', confirm='publisher'))
    def test_rollback_after_revocation_rejected(self):
        with patch.object(cli, 'load', return_value=state_fixture('retiring')):
            with self.assertRaises(ValueError): cli.cmd_rollback(argparse.Namespace(role='reader'))
    def test_running_pipeline_blocks(self):
        a = Mock(); a.pages.return_value = [{'status': 'running'}]
        with patch.object(cli, 'admin', return_value=a):
            with self.assertRaises(ValueError): cli.ensure_idle(state_fixture())
    def test_active_schedule_blocks(self):
        a = Mock(); a.pages.side_effect = [[], [{'active': True}]]
        with patch.object(cli, 'admin', return_value=a):
            with self.assertRaises(ValueError): cli.ensure_idle(state_fixture())
    def test_variable_scope_encoded(self):
        value = cli.variable_path(5, 'TOKEN')
        self.assertIn('filter%5Benvironment_scope%5D=%2A', value)
    def test_restore_preserves_metadata_not_readonly_fields(self):
        a = Mock()
        var = {'value': 'not-a-real-token', 'masked': True, 'protected': True, 'environment_scope': '*',
               'raw': True, 'variable_type': 'env_var', 'key': 'TOKEN', 'hidden': False}
        cli.restore_variables(a, 20, {'TOKEN': var})
        payload = a.request.call_args.args[2]
        self.assertTrue(payload['protected']); self.assertTrue(payload['masked'])
        self.assertNotIn('key', payload); self.assertNotIn('hidden', payload)
    def test_revoked_token_is_idempotent(self):
        a = Mock(); a.get.return_value = {'revoked': True}
        cli.revoke(a, 2); a.request.assert_not_called()
    def test_active_token_revoked(self):
        a = Mock(); a.get.return_value = {'revoked': False}
        cli.revoke(a, 2); a.request.assert_called_once_with('DELETE', '/personal_access_tokens/2')

class CutoverTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(); self.root = Path(self.temp.name)
        self.state = state_fixture()
        self.stack = contextlib.ExitStack()
        self.stack.enter_context(patch.object(cli, 'WORK', self.root))
        self.stack.enter_context(patch.object(cli, 'ensure_idle'))
        self.stack.enter_context(patch.object(cli, 'admin', return_value=Mock()))
        self.stack.enter_context(patch.object(cli, 'snapshot_variables', return_value={'READER_TOKEN': {'value': 'old'}}))
        self.stack.enter_context(patch.object(cli, 'token_for', return_value='new'))
        self.stack.enter_context(patch.object(cli, 'event'))
        self.stack.enter_context(contextlib.redirect_stdout(io.StringIO()))
        write_json(self.root / 'state.json', self.state)
    def tearDown(self):
        self.stack.close(); self.temp.cleanup()
    def test_checkpoint_before_first_write(self):
        def verify(*args, **kwargs):
            self.assertEqual(read_json(self.root / 'state.json')['roles']['reader']['phase'], 'switching')
        with patch.object(cli, 'put_variable', side_effect=verify), patch.object(cli, 'set_worker'):
            cli.cmd_cutover(argparse.Namespace(role='reader', ticket='LAB-1', owner='simulated-team'))
        self.assertEqual(read_json(self.root / 'state.json')['roles']['reader']['phase'], 'switched')
    def test_partial_failure_remains_recoverable(self):
        with patch.object(cli, 'put_variable', side_effect=APIError(503, 'PUT', '/variables')):
            with self.assertRaises(APIError): cli.cmd_cutover(argparse.Namespace(role='reader', ticket='LAB-1', owner='simulated-team'))
        self.assertEqual(read_json(self.root / 'state.json')['roles']['reader']['phase'], 'switching')
        self.assertTrue((self.root / 'backups/reader.json').exists())
    def test_owner_mandatory(self):
        with self.assertRaises(ValueError): cli.cmd_cutover(argparse.Namespace(role='reader', ticket='LAB-1', owner=' '))
    def test_ticket_mandatory(self):
        with self.assertRaises(ValueError): cli.cmd_cutover(argparse.Namespace(role='reader', ticket='', owner='team'))

if __name__ == '__main__': unittest.main()
