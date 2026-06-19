import os
from io import StringIO
from unittest.mock import patch

from crazy_workers.cli.main import main as cli_main
from tests.base import BaseTestCase


class TestCliMain(BaseTestCase):
  def setUp(self):
    super().setUp()
    self.env_patcher = patch.dict(os.environ, {})
    self.env_patcher.start()

  def tearDown(self):
    self.env_patcher.stop()
    super().tearDown()

  def test_cli_status(self):
    self.manager.start_worker('example_worker', worker_key='cli_test')

    argv = ['crazy-workers', '--workers-dir', self.workers_path, 'status']
    with patch('sys.argv', argv):
      with patch('sys.stdout', new=StringIO()) as fake_out:
        cli_main()
        output = fake_out.getvalue()
        self.assertIn('cli_test', output)
        self.assertIn('RUNNING', output)

  def test_cli_env_discovery(self):
    self.manager.start_worker('example_worker', worker_key='env_test')

    with patch('sys.argv', ['crazy-workers', 'status']):
      with patch.dict(os.environ, {'CRAZY_WORKERS_DIR': self.workers_path}):
        with patch('sys.stdout', new=StringIO()) as fake_out:
          cli_main()
          output = fake_out.getvalue()
          self.assertIn('env_test', output)

  def test_cli_flag_override(self):
    argv = ['crazy-workers', '--workers-dir', self.workers_path, 'status']
    with patch('sys.argv', argv):
      with patch.dict(os.environ, {'CRAZY_WORKERS_DIR': '/non/existent/path/env'}):
        with patch('sys.stdout', new=StringIO()) as fake_out:
          cli_main()
          output = fake_out.getvalue()
          self.assertIn('NEVER_STARTED', output)

  def test_cli_error_missing_dir(self):
    argv = ['crazy-workers', '--workers-dir', '/non/existent/path/flag', 'status']
    with patch('sys.argv', argv):
      with patch('sys.stderr', new=StringIO()) as fake_err:
        with self.assertRaises(SystemExit) as cm:
          cli_main()
        self.assertEqual(cm.exception.code, 1)
        output = ' '.join(fake_err.getvalue().split())
        self.assertIn('Error: Directory "/non/existent/path/flag" does not exist', output)

  def test_cli_stop(self):
    self.manager.start_worker('example_worker', worker_key='stop_test')

    argv = ['crazy-workers', '--workers-dir', self.workers_path, 'stop', 'stop_test']
    with patch('sys.argv', argv):
      with patch('sys.stdout', new=StringIO()) as fake_out:
        cli_main()
        output = fake_out.getvalue()
        self.assertIn('Success', output)

    workers = self.manager.list_workers()
    worker = next(w for w in workers if w['worker_key'] == 'stop_test')
    self.assertEqual(worker['status'], 'STOPPED')

  def test_cli_stop_error(self):
    argv = ['crazy-workers', '--workers-dir', self.workers_path, 'stop', 'non_existent']
    with patch('sys.argv', argv):
      with patch('sys.stderr', new=StringIO()) as fake_err:
        with self.assertRaises(SystemExit) as cm:
          cli_main()
        self.assertEqual(cm.exception.code, 1)
        self.assertIn('Error', fake_err.getvalue())

  def test_cli_no_command(self):
    with patch('sys.argv', ['crazy-workers']):
      with patch('sys.stdout', new=StringIO()):
        with self.assertRaises(SystemExit) as cm:
          cli_main()
        self.assertEqual(cm.exception.code, 1)
