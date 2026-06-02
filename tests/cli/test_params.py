import json
import os
from io import StringIO
from unittest.mock import patch

from crazy_workers.cli.main import main as cli_main
from tests.base import BaseTestCase


class TestCliParams(BaseTestCase):
  def setUp(self):
    super().setUp()
    # Mock environment to use our test workers directory
    self.env_patcher = patch.dict(os.environ, {'CRAZY_WORKERS_DIR': self.workers_path})
    self.env_patcher.start()

  def tearDown(self):
    self.env_patcher.stop()
    super().tearDown()

  def test_cli_start_with_params(self):
    params = {'test_key': 'test_val', 'num': 123}
    params_json = json.dumps(params)

    args = ['crazy-workers', 'start', 'example_worker', '--key', 'params_test', '--params', params_json]
    with patch('sys.argv', args):
      with patch('sys.stdout', new=StringIO()) as fake_out:
        try:
          cli_main()
        except SystemExit as e:
          self.assertEqual(e.code, 0)

        output = fake_out.getvalue()
        self.assertIn('Worker started', output)
        self.assertIn('params_test', output)

    # Verify in DB
    workers = self.manager.list_workers()
    worker = next(w for w in workers if w['worker_key'] == 'params_test')
    self.assertEqual(worker['parameters'], params)

    self.manager.stop_worker('params_test')

  def test_cli_params_command(self):
    params = {'secret': 'data', 'id': 42}
    self.manager.start_worker('example_worker', worker_key='show_test', parameters=params)

    with patch('sys.argv', ['crazy-workers', 'params', 'show_test']):
      with patch('rich.console.Console.print') as _:
        with patch('rich.console.Console.print_json') as mock_print_json:
          try:
            cli_main()
          except SystemExit as e:
            self.assertEqual(e.code, 0)

          # Verify print_json was called with the correct parameters
          mock_print_json.assert_called_once()
          args, kwargs = mock_print_json.call_args
          self.assertIn('"secret": "data"', args[0])
          self.assertIn('"id": 42', args[0])

    self.manager.stop_worker('show_test')

  def test_cli_params_command_interactive(self):
    params = {'secret': 'data', 'id': 42}
    self.manager.start_worker('example_worker', worker_key='interactive_test', parameters=params)

    # Patch IntPrompt.ask to simulate selecting the first worker
    with patch('sys.argv', ['crazy-workers', 'params']):
      with patch('rich.console.Console.print') as _:
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

  def test_cli_params_command_not_found(self):
    with patch('sys.argv', ['crazy-workers', 'params', 'non_existent_key']):
      with patch('rich.console.Console.print') as _:
        try:
          cli_main()
        except SystemExit as e:
          self.assertEqual(e.code, 1)

  def test_cli_params_command_no_registered_workers(self):
    # Ensure no workers are running/registered
    workers = self.manager.list_workers()
    for w in workers:
      if w['worker_key']:
        self.manager.stop_worker(w['worker_key'])

    with patch('sys.argv', ['crazy-workers', 'params']):
      with patch('rich.console.Console.print') as mock_print:
        try:
          cli_main()
        except SystemExit as e:
          self.assertEqual(e.code, 1)  # CLI exits with 1 if show_params returns False

        # Check if the "No registered workers" message was printed
        found_msg = any('No registered workers' in str(call) for call in mock_print.call_args_list)
        self.assertTrue(found_msg)

  def test_cli_list_with_enhanced_output(self):
    params = {'long_param_name_for_testing_truncation': 'value'}
    self.manager.start_worker('example_worker', worker_key='list_test', parameters=params)

    with patch('sys.argv', ['crazy-workers', 'list']):
      with patch('rich.console.Console.print') as _:
        with patch('rich.table.Table.add_row') as mock_add_row:
          try:
            cli_main()
          except SystemExit as e:
            self.assertEqual(e.code, 0)

          # Check if add_row was called with expected columns
          # Column indices: 0:#, 1:Key, 2:Type, 3:Status, 4:PID, 5:Last Action, 6:Params
          found = False
          for call in mock_add_row.call_args_list:
            args = call[0]
            if 'list_test' in args:
              found = True
              self.assertIn('Started', args[5])
              self.assertTrue(args[6].endswith('...'))  # Truncated params
              break
          self.assertTrue(found)

    self.manager.stop_worker('list_test')

  def test_cli_start_invalid_json_params(self):
    args = ['crazy-workers', 'start', 'example_worker', '--params', 'not-valid-json{']
    with patch('sys.argv', args):
      with patch('sys.stderr', new=StringIO()) as fake_err:
        with self.assertRaises(SystemExit) as cm:
          cli_main()
        self.assertEqual(cm.exception.code, 1)
        self.assertIn('Invalid JSON', fake_err.getvalue())
