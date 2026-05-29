import os
from io import StringIO
from unittest.mock import patch

from crazy_workers.cli.main import main as cli_main
from tests.base import BaseTestCase


class TestCli(BaseTestCase):
  def setUp(self):
    super().setUp()
    self.env_patcher = patch.dict(os.environ, {})
    self.env_patcher.start()

  def tearDown(self):
    self.env_patcher.stop()
    super().tearDown()

  def test_cli_list(self):
    # Start a worker first
    self.manager.start_worker('example_worker', worker_key='cli_test')

    argv = ['crazy-workers', '--workers-dir', self.workers_path, 'list']
    with patch('sys.argv', argv):
      with patch('sys.stdout', new=StringIO()) as fake_out:
        cli_main()
        output = fake_out.getvalue()
        self.assertIn('cli_test', output)
        self.assertIn('RUNNING', output)

  def test_cli_env_discovery(self):
    self.manager.start_worker('example_worker', worker_key='env_test')

    argv = ['crazy-workers', 'list']
    with patch('sys.argv', argv):
      with patch.dict(os.environ, {'CRAZY_WORKERS_DIR': self.workers_path}):
        with patch('sys.stdout', new=StringIO()) as fake_out:
          cli_main()
          output = fake_out.getvalue()
          self.assertIn('env_test', output)

  def test_cli_autodetect_discovery(self):
    # We mock isdir to return True only for 'workers' and abspath to return our test path
    # To avoid recursion, we capture the original functions
    original_isdir = os.path.isdir
    original_abspath = os.path.abspath

    def mocked_isdir(p):
      if p == 'workers':
        return True
      return original_isdir(p)

    def mocked_abspath(p):
      if p == 'workers':
        return self.workers_path
      return original_abspath(p)

    # Ensure the DB in self.workers_path is updated
    from crazy_workers.database.storage import Storage

    db_path = os.path.join(self.workers_path, '.service', 'workers.db')
    Storage(db_path).dispose()

    with patch('crazy_workers.cli.discovery.os.path.isdir', side_effect=mocked_isdir):
      with patch('crazy_workers.cli.discovery.os.path.abspath', side_effect=mocked_abspath):
        argv = ['crazy-workers', 'list']
        with patch('sys.argv', argv):
          with patch('sys.stdin.isatty', return_value=False):
            with patch('sys.stdout', new=StringIO()) as fake_out:
              cli_main()
              output = fake_out.getvalue()
              self.assertTrue('Active & Registered' in output or 'No workers' in output)

  def test_cli_env_file_discovery(self):
    env_path = os.path.abspath('.env_test')
    with open(env_path, 'w') as f:
      f.write(f'CRAZY_WORKERS_DIR={self.workers_path}\n')

    # Ensure the DB in self.workers_path is updated
    from crazy_workers.database.storage import Storage

    db_path = os.path.join(self.workers_path, '.service', 'workers.db')
    Storage(db_path).dispose()

    try:
      # Mock load_env to read our custom env file
      def mock_load_env():
        if os.path.exists(env_path):
          with open(env_path, 'r') as f:
            for line in f:
              if '=' in line:
                k, v = line.strip().split('=', 1)
                os.environ[k] = v

      with patch('crazy_workers.cli.discovery.load_env', side_effect=mock_load_env):
        argv = ['crazy-workers', 'list']
        with patch('sys.argv', argv):
          with patch('sys.stdout', new=StringIO()) as fake_out:
            cli_main()
            output = fake_out.getvalue()
            self.assertTrue('Active & Registered' in output or 'No workers' in output)
    finally:
      if os.path.exists(env_path):
        os.remove(env_path)

  def test_cli_flag_override(self):
    # Flag should override ENV
    argv = ['crazy-workers', '--workers-dir', self.workers_path, 'list']
    with patch('sys.argv', argv):
      # We use a non-existent path in ENV, but since flag is provided, it should work if flag is valid
      with patch.dict(os.environ, {'CRAZY_WORKERS_DIR': '/non/existent/path/env'}):
        with patch('sys.stdout', new=StringIO()) as fake_out:
          cli_main()
          output = fake_out.getvalue()
          self.assertIn('NEVER_STARTED', output)

  def test_cli_error_missing_dir(self):
    argv = ['crazy-workers', '--workers-dir', '/non/existent/path/flag', 'list']
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
