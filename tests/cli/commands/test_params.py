import os
from io import StringIO
from unittest.mock import MagicMock, patch

from crazy_workers import WorkerClient
from crazy_workers.cli.commands import show_params
from crazy_workers.cli.main import main as cli_main
from tests.base import BaseTestCase


class TestCliCommandParams(BaseTestCase):
  def setUp(self):
    super().setUp()
    self.env_patcher = patch.dict(os.environ, {'CRAZY_WORKERS_DIR': self.workers_path})
    self.env_patcher.start()

  def tearDown(self):
    self.env_patcher.stop()
    super().tearDown()

  def _client_with(self, workers):
    client = MagicMock()
    client.list.return_value = workers
    return client

  def test_params_explicit(self):
    client = self._client_with(
      [
        {
          'worker_key': 'show_test',
          'worker_type': 'example_worker',
          'status': 'RUNNING',
          'parameters': {'secret': 'data', 'id': 42},
        }
      ]
    )
    with patch('rich.console.Console.print'):
      with patch('rich.console.Console.print_json') as mock_print_json:
        self.assertTrue(show_params(client, 'show_test'))
        mock_print_json.assert_called_once()
        self.assertIn('"secret": "data"', mock_print_json.call_args[0][0])

  def test_params_interactive(self):
    client = self._client_with([{'worker_key': 'a', 'worker_type': 't', 'status': 'RUNNING', 'parameters': {'k': 'v'}}])
    with patch('rich.console.Console.print'):
      with patch('rich.prompt.IntPrompt.ask', return_value=1):
        with patch('rich.console.Console.print_json') as mock_print_json:
          self.assertTrue(show_params(client, None))
          self.assertIn('"k": "v"', mock_print_json.call_args[0][0])

  def test_params_not_found(self):
    client = self._client_with([{'worker_key': 'a', 'worker_type': 't', 'status': 'RUNNING', 'parameters': {}}])
    with patch('sys.stderr', new=StringIO()) as fake_err:
      self.assertFalse(show_params(client, 'nope'))
      self.assertIn('not found', fake_err.getvalue())

  def test_params_empty(self):
    client = self._client_with([])
    with patch('sys.stdout', new=StringIO()) as fake_out:
      self.assertFalse(show_params(client, None))
      self.assertIn('No workers found', fake_out.getvalue())

  def test_params_cli_integration(self):
    sqlite = f'sqlite:///{os.path.join(self.workers_path, ".service", "workers.db")}'
    with WorkerClient(db_url=sqlite, create_tables=True) as client:
      client.request_start('example_worker', worker_key='pcli', parameters={'a': 1})

    with patch('sys.argv', ['crazy-workers', 'params', 'pcli']):
      with patch('rich.console.Console.print'):
        with patch('rich.console.Console.print_json') as mock_print_json:
          try:
            cli_main()
          except SystemExit as e:
            self.assertEqual(e.code, 0)
          self.assertIn('"a": 1', mock_print_json.call_args[0][0])
