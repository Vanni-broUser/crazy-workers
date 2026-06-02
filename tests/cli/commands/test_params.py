import os
from io import StringIO
from unittest.mock import patch

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

  def test_params_command(self):
    params = {'secret': 'data', 'id': 42}
    self.manager.start_worker('example_worker', worker_key='show_test', parameters=params)

    with patch('sys.argv', ['crazy-workers', 'params', 'show_test']):
      with patch('rich.console.Console.print'):
        with patch('rich.console.Console.print_json') as mock_print_json:
          try:
            cli_main()
          except SystemExit as e:
            self.assertEqual(e.code, 0)
          mock_print_json.assert_called_once()
          args, _ = mock_print_json.call_args
          self.assertIn('"secret": "data"', args[0])
          self.assertIn('"id": 42', args[0])

    self.manager.stop_worker('show_test')

  def test_params_command_interactive(self):
    params = {'secret': 'data', 'id': 42}
    self.manager.start_worker('example_worker', worker_key='interactive_test', parameters=params)

    with patch('sys.argv', ['crazy-workers', 'params']):
      with patch('rich.console.Console.print'):
        with patch('rich.prompt.IntPrompt.ask', return_value=1):
          with patch('rich.console.Console.print_json') as mock_print_json:
            try:
              cli_main()
            except SystemExit as e:
              self.assertEqual(e.code, 0)
            mock_print_json.assert_called_once()
            args, _ = mock_print_json.call_args
            self.assertIn('"secret": "data"', args[0])

    self.manager.stop_worker('interactive_test')

  def test_params_command_not_found(self):
    with patch('sys.argv', ['crazy-workers', 'params', 'non_existent_key']):
      with patch('rich.console.Console.print'):
        with self.assertRaises(SystemExit) as cm:
          cli_main()
        self.assertEqual(cm.exception.code, 1)

  def test_params_command_no_registered_workers(self):
    workers = self.manager.list_workers()
    for w in workers:
      if w['worker_key']:
        self.manager.stop_worker(w['worker_key'])

    with patch('sys.argv', ['crazy-workers', 'params']):
      with patch('rich.console.Console.print') as mock_print:
        with self.assertRaises(SystemExit) as cm:
          cli_main()
        self.assertEqual(cm.exception.code, 1)
        found_msg = any('No registered workers' in str(call) for call in mock_print.call_args_list)
        self.assertTrue(found_msg)

  def test_params_empty_workers_list(self):
    from unittest.mock import MagicMock

    from crazy_workers.cli.commands.params import show_params

    mock_manager = MagicMock()
    mock_manager.list_workers.return_value = []
    with patch('sys.stdout', new=StringIO()) as fake_out:
      result = show_params(mock_manager, None)
      self.assertFalse(result)
      self.assertIn('No workers found', fake_out.getvalue())
