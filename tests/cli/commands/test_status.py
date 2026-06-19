import os
from io import StringIO
from rich.console import Console
from unittest import mock
from unittest.mock import MagicMock, patch

from crazy_workers.boot.base import BootState
from crazy_workers.cli.commands import show_status
from crazy_workers.cli.commands.status import _build_header
from crazy_workers.cli.main import main as cli_main
from tests.base import BaseTestCase


class _FakeProvider:
  def __init__(self, state):
    self._state = state

  def state(self, workers_dir):
    return self._state


class TestCliStatus(BaseTestCase):
  def setUp(self):
    super().setUp()
    self.env_patcher = patch.dict(os.environ, {'CRAZY_WORKERS_DIR': self.workers_path})
    self.env_patcher.start()

  def tearDown(self):
    self.env_patcher.stop()
    super().tearDown()

  def test_status_empty(self):
    self.manager.list_workers = MagicMock(return_value=[])
    with patch('sys.stdout', new=StringIO()) as fake_out:
      result = show_status(self.manager)
      self.assertEqual(result, [])
      self.assertIn('No workers found', fake_out.getvalue())

  def test_status_truncates_long_params(self):
    params = {'long_param_name_for_testing_truncation': 'value'}
    self.manager.start_worker('example_worker', worker_key='status_test', parameters=params)

    with patch('sys.argv', ['crazy-workers', 'status']):
      with patch('rich.console.Console.print'):
        with patch('rich.table.Table.add_row') as mock_add_row:
          try:
            cli_main()
          except SystemExit as exc:
            self.assertEqual(exc.code, 0)

          found = False
          for call in mock_add_row.call_args_list:
            args = call[0]
            if 'status_test' in args:
              found = True
              self.assertIn('Started', args[-2])
              self.assertTrue(args[-1].endswith('...'))
              break
          self.assertTrue(found)

    self.manager.stop_worker('status_test')

  def test_status_crashed_worker_style(self):
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
        show_status(self.manager)
        args = mock_add_row.call_args[0]
        self.assertIn('bold red', args[3])

  def test_status_stopped_worker_with_timestamp(self):
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
        show_status(self.manager)
        args = mock_add_row.call_args[0]
        self.assertIn('Stopped', args[5])
        self.assertIn('dim', args[3])


class TestStatusHeader(BaseTestCase):
  def setUp(self):
    super().setUp()
    self._env = patch.dict(os.environ, {'CRAZY_WORKERS_NO_BOOT': ''})
    self._env.start()

  def tearDown(self):
    self._env.stop()
    super().tearDown()

  def _render(self):
    buffer = StringIO()
    Console(file=buffer, width=200).print(_build_header(self.manager))
    return buffer.getvalue()

  def test_header_disabled(self):
    os.environ['CRAZY_WORKERS_NO_BOOT'] = '1'
    self.assertIn('disabled', self._render())

  def test_header_enabled(self):
    self.manager._boot_provider = _FakeProvider(
      BootState(supported=True, installed=True, mechanism='systemd-user', at_boot=True, detail='runs at boot')
    )
    self.assertIn('enabled', self._render())

  def test_header_not_installed(self):
    self.manager._boot_provider = _FakeProvider(
      BootState(supported=True, installed=False, mechanism='systemd-user', at_boot=False, detail='runs at user login')
    )
    self.assertIn('not installed', self._render())

  def test_header_unsupported(self):
    with mock.patch('crazy_workers.boot.orchestrator.get_provider', return_value=None):
      self.assertIn('not supported', self._render())
