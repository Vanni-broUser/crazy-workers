import os
from io import StringIO
from unittest.mock import patch

from crazy_workers import WorkerClient
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

  def _sqlite_url(self):
    return f'sqlite:///{os.path.join(self.workers_path, ".service", "workers.db")}'

  def _seed_request(self, worker_type, key):
    with WorkerClient(db_url=self._sqlite_url(), create_tables=True) as client:
      client.request_start(worker_type, worker_key=key)

  def test_cli_status(self):
    self._seed_request('example_worker', 'cli_test')
    argv = ['crazy-workers', '--workers-dir', self.workers_path, 'status']
    with patch.dict(os.environ, {'COLUMNS': '220'}):
      with patch('sys.argv', argv):
        with patch('sys.stdout', new=StringIO()) as fake_out:
          cli_main()
          output = fake_out.getvalue()
          self.assertIn('cli_test', output)
          self.assertIn('RUNNING', output)  # desired column

  def test_cli_env_discovery(self):
    self._seed_request('example_worker', 'env_test')
    with patch('sys.argv', ['crazy-workers', 'status']):
      with patch.dict(os.environ, {'CRAZY_WORKERS_DIR': self.workers_path, 'COLUMNS': '220'}):
        with patch('sys.stdout', new=StringIO()) as fake_out:
          cli_main()
          self.assertIn('env_test', fake_out.getvalue())

  def test_cli_flag_override(self):
    argv = ['crazy-workers', '--workers-dir', self.workers_path, 'status']
    with patch('sys.argv', argv):
      with patch.dict(os.environ, {'CRAZY_WORKERS_DIR': '/non/existent/path/env', 'COLUMNS': '220'}):
        with patch('sys.stdout', new=StringIO()) as fake_out:
          cli_main()
          self.assertIn('NEVER_STARTED', fake_out.getvalue())

  def test_cli_error_missing_dir(self):
    argv = ['crazy-workers', '--workers-dir', '/non/existent/path/flag', 'status']
    with patch('sys.argv', argv):
      with patch('sys.stderr', new=StringIO()) as fake_err:
        with self.assertRaises(SystemExit) as cm:
          cli_main()
        self.assertEqual(cm.exception.code, 1)
        output = ' '.join(fake_err.getvalue().split())
        self.assertIn('Error: Directory "/non/existent/path/flag" does not exist', output)

  def test_cli_stop_requests_stopped(self):
    self._seed_request('example_worker', 'stop_test')
    argv = ['crazy-workers', '--workers-dir', self.workers_path, 'stop', 'stop_test']
    with patch('sys.argv', argv):
      with patch('sys.stdout', new=StringIO()) as fake_out:
        cli_main()
        self.assertIn('Requested', fake_out.getvalue())

    with WorkerClient(db_url=self._sqlite_url()) as client:
      self.assertEqual(client.get('stop_test')['desired_status'], 'STOPPED')

  def test_cli_stop_not_found(self):
    argv = ['crazy-workers', '--workers-dir', self.workers_path, 'stop', 'non_existent']
    with patch('sys.argv', argv):
      with patch('sys.stderr', new=StringIO()) as fake_err:
        with self.assertRaises(SystemExit) as cm:
          cli_main()
        self.assertEqual(cm.exception.code, 1)
        self.assertIn('Error', fake_err.getvalue())

  def test_cli_daemon_subcommand_invokes_daemon(self):
    with patch('crazy_workers.daemon.runner.main', return_value=0) as daemon_main:
      argv = ['crazy-workers', '--workers-dir', self.workers_path, 'daemon', '--interval', '0.5']
      with patch('sys.argv', argv):
        with self.assertRaises(SystemExit) as cm:
          cli_main()
        self.assertEqual(cm.exception.code, 0)
      daemon_main.assert_called_once()
      called_argv = daemon_main.call_args[0][0]
      self.assertIn('--workers-dir', called_argv)
      self.assertIn(self.workers_path, called_argv)
      self.assertIn('0.5', called_argv)

  def test_cli_status_with_shared_db_url(self):
    # Point the CLI at a shared DB (as lotec-be/generic-deploy do) via env var.
    url = self._sqlite_url()
    with WorkerClient(db_url=url, create_tables=True) as client:
      client.request_start('example_worker', worker_key='shared1')

    with patch.dict(os.environ, {'CRAZY_WORKERS_DB_URL': url, 'COLUMNS': '220'}):
      with patch('sys.argv', ['crazy-workers', '--workers-dir', self.workers_path, 'status']):
        with patch('sys.stdout', new=StringIO()) as fake_out:
          cli_main()
          output = fake_out.getvalue()
          self.assertIn('shared1', output)
          self.assertIn('shared DB', output)

  def test_cli_no_command(self):
    with patch('sys.argv', ['crazy-workers']):
      with patch('sys.stdout', new=StringIO()):
        with self.assertRaises(SystemExit) as cm:
          cli_main()
        self.assertEqual(cm.exception.code, 1)
