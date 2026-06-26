import os
from io import StringIO
from rich.console import Console
from unittest.mock import MagicMock, patch

from crazy_workers.cli.commands import show_status
from crazy_workers.cli.commands.status import _build_header, _redact
from tests.base import BaseTestCase


class TestCliStatus(BaseTestCase):
  def setUp(self):
    super().setUp()
    self.env_patcher = patch.dict(os.environ, {'CRAZY_WORKERS_DIR': self.workers_path})
    self.env_patcher.start()

  def tearDown(self):
    self.env_patcher.stop()
    super().tearDown()

  def _client(self, workers):
    client = MagicMock()
    client.list.return_value = workers
    return client

  def test_lists_filesystem_types_when_db_empty(self):
    # No DB rows, but example_worker.py exists → a NEVER_STARTED virtual row.
    with patch('sys.stdout', new=StringIO()):
      result = show_status(self._client([]), self.workers_path)
    types = {w['worker_type'] for w in result}
    self.assertIn('example_worker', types)
    self.assertTrue(all(w['status'] == 'NEVER_STARTED' for w in result))

  def test_empty_when_no_files_and_no_rows(self):
    with patch('os.listdir', return_value=[]):
      with patch('sys.stdout', new=StringIO()) as fake_out:
        result = show_status(self._client([]), self.workers_path)
        self.assertEqual(result, [])
        self.assertIn('No workers found', fake_out.getvalue())

  def test_desired_vs_actual_columns(self):
    client = self._client(
      [
        {
          'worker_key': 'w',
          'worker_type': 'example_worker',
          'desired_status': 'RUNNING',
          'status': 'CRASHED',
          'pid': None,
          'parameters': {},
          'last_started_at': None,
          'last_stopped_at': None,
        }
      ]
    )
    with patch('os.listdir', return_value=[]):
      with patch('sys.stdout', new=StringIO()):
        with patch('rich.table.Table.add_row') as mock_add_row:
          show_status(client, self.workers_path)
          args = mock_add_row.call_args[0]
          # columns: #, key, type, desired, status, pid, last_action, params
          self.assertIn('RUNNING', args[3])  # desired
          self.assertIn('bold red', args[4])  # CRASHED actual style

  def test_stopped_with_timestamp(self):
    client = self._client(
      [
        {
          'worker_key': 's',
          'worker_type': 'example_worker',
          'desired_status': 'STOPPED',
          'status': 'STOPPED',
          'pid': None,
          'parameters': {},
          'last_started_at': None,
          'last_stopped_at': '2024-01-01T12:00:00',
        }
      ]
    )
    with patch('os.listdir', return_value=[]):
      with patch('sys.stdout', new=StringIO()):
        with patch('rich.table.Table.add_row') as mock_add_row:
          show_status(client, self.workers_path)
          args = mock_add_row.call_args[0]
          self.assertIn('Stopped', args[6])  # last action
          self.assertIn('dim', args[4])  # stopped style

  def test_truncates_long_params_and_shows_started(self):
    client = self._client(
      [
        {
          'worker_key': 'lp',
          'worker_type': 'example_worker',
          'desired_status': 'RUNNING',
          'status': 'RUNNING',
          'pid': 5,
          'parameters': {'long_param_name_for_truncation': 'x' * 50},
          'last_started_at': '2024-01-01T12:00:00',
          'last_stopped_at': None,
        }
      ]
    )
    with patch('os.listdir', return_value=[]):
      with patch('sys.stdout', new=StringIO()):
        with patch('rich.table.Table.add_row') as mock_add_row:
          show_status(client, self.workers_path)
          args = mock_add_row.call_args[0]
          self.assertIn('Started', args[6])
          self.assertTrue(args[7].endswith('...'))


class TestStatusHeader(BaseTestCase):
  def _render(self, workers_dir):
    buffer = StringIO()
    Console(file=buffer, width=200).print(_build_header(workers_dir))
    return buffer.getvalue()

  def test_header_self_contained(self):
    with patch.dict(os.environ, {}, clear=False):
      os.environ.pop('CRAZY_WORKERS_DB_URL', None)
      self.assertIn('self-contained', self._render(self.workers_path))

  def test_header_shared_db_redacts_password(self):
    with patch.dict(os.environ, {'CRAZY_WORKERS_DB_URL': 'postgresql://user:secret@host:5432/db'}):
      out = self._render(self.workers_path)
      self.assertIn('shared DB', out)
      self.assertNotIn('secret', out)

  def test_redact(self):
    self.assertEqual(_redact('postgresql://u:p@h/db'), 'postgresql://u:***@h/db')
    self.assertEqual(_redact('sqlite:///x.db'), 'sqlite:///x.db')
