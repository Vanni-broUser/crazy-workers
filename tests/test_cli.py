import os
from io import StringIO
from unittest.mock import patch

from crazy_workers.cli import main as cli_main
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
    # Create a local 'workers' folder temporarily
    if not os.path.exists('workers'):
      os.makedirs('workers', exist_ok=True)
      cleanup = True
    else:
      cleanup = False

    try:
      argv = ['crazy-workers', 'list']
      with patch('sys.argv', argv):
        with patch('sys.stdin.isatty', return_value=False):
          with patch('sys.stdout', new=StringIO()) as fake_out:
            cli_main()
            # Should not crash and should return a message indicating no workers
            output = fake_out.getvalue()
            self.assertIn('No workers found', output)
    finally:
      if cleanup:
        import shutil

        shutil.rmtree('workers')

  def test_cli_env_file_discovery(self):
    with open('.env', 'w') as f:
      f.write(f'CRAZY_WORKERS_DIR={self.workers_path}\n')

    try:
      argv = ['crazy-workers', 'list']
      with patch('sys.argv', argv):
        with patch('sys.stdout', new=StringIO()) as fake_out:
          cli_main()
          output = fake_out.getvalue()
          # Rich output should at least contain the header or empty message
          self.assertTrue('Workers' in output or 'No workers' in output)
    finally:
      if os.path.exists('.env'):
        os.remove('.env')

  def test_cli_flag_override(self):
    # Flag should override ENV
    argv = ['crazy-workers', '--workers-dir', self.workers_path, 'list']
    with patch('sys.argv', argv):
      # We use a non-existent path in ENV, but since flag is provided, it should work if flag is valid
      with patch.dict(os.environ, {'CRAZY_WORKERS_DIR': '/non/existent/path/env'}):
        with patch('sys.stdout', new=StringIO()) as fake_out:
          cli_main()
          output = fake_out.getvalue()
          self.assertIn('No workers found', output)

  def test_cli_error_missing_dir(self):
    argv = ['crazy-workers', '--workers-dir', '/non/existent/path/flag', 'list']
    with patch('sys.argv', argv):
      with patch('sys.stderr', new=StringIO()) as fake_err:
        with self.assertRaises(SystemExit) as cm:
          cli_main()
        self.assertEqual(cm.exception.code, 1)
        self.assertIn('Error: Directory "/non/existent/path/flag" does not exist', fake_err.getvalue())

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
