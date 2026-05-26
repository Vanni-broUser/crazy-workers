from io import StringIO
from unittest.mock import patch

from crazy_workers.cli import main as cli_main
from tests.base import BaseTestCase


class TestCli(BaseTestCase):
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
