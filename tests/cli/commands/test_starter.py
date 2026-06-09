import json
import os
from io import StringIO
from unittest.mock import MagicMock, patch

from crazy_workers.cli.commands import start_worker
from crazy_workers.cli.main import main as cli_main
from tests.base import BaseTestCase


class TestCliCommandStarter(BaseTestCase):
  def setUp(self):
    super().setUp()
    self.env_patcher = patch.dict(os.environ, {'CRAZY_WORKERS_DIR': self.workers_path})
    self.env_patcher.start()

  def tearDown(self):
    self.env_patcher.stop()
    super().tearDown()

  def test_start_worker_interactive_no_files(self):
    with patch('os.listdir', return_value=[]):
      with patch('sys.stdout', new=StringIO()) as fake_out:
        res = start_worker(self.manager, None)
        self.assertFalse(res)
        self.assertIn('No worker scripts found', fake_out.getvalue())

  def test_start_worker_interactive_selection(self):
    with patch('os.listdir', return_value=['w1.py', 'w2.py', 'not_python.txt']):
      self.manager.start_worker = MagicMock(return_value=(True, {'worker_key': 'w1', 'worker_type': 'w1', 'pid': 456}))
      with patch('rich.prompt.IntPrompt.ask', return_value=1):
        with patch('sys.stdout', new=StringIO()):
          res = start_worker(self.manager, None)
          self.assertTrue(res)
          self.manager.start_worker.assert_called_with('w1', worker_key=None, parameters=None)

  def test_start_worker_error_reading_dir(self):
    with patch('os.listdir', side_effect=OSError('Permission denied')):
      with patch('sys.stderr', new=StringIO()) as fake_err:
        res = start_worker(self.manager, None)
        self.assertFalse(res)
        self.assertIn('Error reading workers directory', fake_err.getvalue())

  def test_cli_start_with_params(self):
    params = {'test_key': 'test_val', 'num': 123}
    args = ['crazy-workers', 'start', 'example_worker', '--key', 'params_test', '--params', json.dumps(params)]
    with patch('sys.argv', args):
      with patch('sys.stdout', new=StringIO()) as fake_out:
        try:
          cli_main()
        except SystemExit as e:
          self.assertEqual(e.code, 0)
        self.assertIn('Worker started', fake_out.getvalue())
        self.assertIn('params_test', fake_out.getvalue())

    workers = self.manager.list_workers()
    worker = next(w for w in workers if w['worker_key'] == 'params_test')
    self.assertEqual(worker['parameters'], params)
    self.manager.stop_worker('params_test')

  def test_start_worker_failure_message(self):
    self.manager.start_worker = MagicMock(return_value=(False, 'worker crashed'))
    with patch('sys.stderr', new=StringIO()) as fake_err:
      res = start_worker(self.manager, 'example_worker')
      self.assertFalse(res)
      self.assertIn('Error', fake_err.getvalue())

  def test_cli_start_invalid_json_params(self):
    args = ['crazy-workers', 'start', 'example_worker', '--params', 'not-valid-json{']
    with patch('sys.argv', args):
      with patch('sys.stderr', new=StringIO()) as fake_err:
        with self.assertRaises(SystemExit) as cm:
          cli_main()
        self.assertEqual(cm.exception.code, 1)
        self.assertIn('Invalid JSON', fake_err.getvalue())
