import os
from io import StringIO
from unittest.mock import MagicMock, patch

from crazy_workers.cli.commands import list_workers
from crazy_workers.cli.main import main as cli_main
from tests.base import BaseTestCase


class TestCliCommandLister(BaseTestCase):
  def setUp(self):
    super().setUp()
    self.env_patcher = patch.dict(os.environ, {'CRAZY_WORKERS_DIR': self.workers_path})
    self.env_patcher.start()

  def tearDown(self):
    self.env_patcher.stop()
    super().tearDown()

  def test_list_workers_empty(self):
    self.manager.list_workers = MagicMock(return_value=[])
    with patch('sys.stdout', new=StringIO()) as fake_out:
      res = list_workers(self.manager)
      self.assertEqual(res, [])
      self.assertIn('No workers found', fake_out.getvalue())

  def test_list_output_truncates_long_params(self):
    params = {'long_param_name_for_testing_truncation': 'value'}
    self.manager.start_worker('example_worker', worker_key='list_test', parameters=params)

    with patch('sys.argv', ['crazy-workers', 'list']):
      with patch('rich.console.Console.print'):
        with patch('rich.table.Table.add_row') as mock_add_row:
          try:
            cli_main()
          except SystemExit as e:
            self.assertEqual(e.code, 0)

          found = False
          for call in mock_add_row.call_args_list:
            args = call[0]
            if 'list_test' in args:
              found = True
              last_action_col = args[-2]  # second-to-last: Last Action
              params_col = args[-1]       # last: Params
              self.assertIn('Started', last_action_col)
              self.assertTrue(params_col.endswith('...'))
              break
          self.assertTrue(found)

    self.manager.stop_worker('list_test')

  def test_list_crashed_worker_style(self):
    self.manager.list_workers = MagicMock(
      return_value=[
        {
          'worker_key': 'crashed',
          'worker_type': 'example_worker',
          'status': 'CRASHED',
          'pid': None,
          'parameters': {},
          'last_started_at': None,
          'last_stopped_at': None,
        },
      ]
    )
    with patch('sys.stdout', new=StringIO()):
      with patch('rich.table.Table.add_row') as mock_add_row:
        list_workers(self.manager)
        args = mock_add_row.call_args[0]
        self.assertIn('bold red', args[3])

  def test_list_stopped_worker_with_timestamp(self):
    self.manager.list_workers = MagicMock(
      return_value=[
        {
          'worker_key': 'stopped',
          'worker_type': 'example_worker',
          'status': 'STOPPED',
          'pid': None,
          'parameters': {},
          'last_started_at': None,
          'last_stopped_at': '2024-01-01T12:00:00',
        },
      ]
    )
    with patch('sys.stdout', new=StringIO()):
      with patch('rich.table.Table.add_row') as mock_add_row:
        list_workers(self.manager)
        args = mock_add_row.call_args[0]
        self.assertIn('Stopped', args[5])
        self.assertIn('dim', args[3])
