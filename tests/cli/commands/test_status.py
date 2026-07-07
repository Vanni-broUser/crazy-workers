import json
import os
from io import StringIO
from rich.console import Console
from unittest.mock import MagicMock, patch

from crazy_workers.cli.commands import show_status
from crazy_workers.cli.commands.status import _build_header, _format_pid, _redact
from tests.base import BaseTestCase


def _worker(key, status, desired, stopped_at=None, started_at=None, pid=None, parameters=None):
  return {
    'worker_key': key,
    'worker_type': 'example_worker',
    'desired_status': desired,
    'status': status,
    'pid': pid,
    'parameters': parameters or {},
    'last_started_at': started_at,
    'last_stopped_at': stopped_at,
  }


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

  def _rows(self, client, **kwargs):
    with patch('os.listdir', return_value=[]):
      with patch('sys.stdout', new=StringIO()):
        with patch('rich.table.Table.add_row') as mock_add_row:
          result = show_status(client, self.workers_path, **kwargs)
    return result, [call[0] for call in mock_add_row.call_args_list]

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

  def test_crashed_shows_restart_pending_note(self):
    client = self._client([_worker('w', 'CRASHED', 'RUNNING')])
    _, rows = self._rows(client)
    # columns: #, key, type, status, pid, last_action, params
    self.assertIn('bold red', rows[0][3])
    self.assertIn('restart pending', rows[0][3])

  def test_running_with_stop_requested_note(self):
    client = self._client([_worker('w', 'RUNNING', 'STOPPED', pid=7)])
    _, rows = self._rows(client)
    self.assertIn('RUNNING', rows[0][3])
    self.assertIn('stop requested', rows[0][3])

  def test_settled_states_carry_no_note(self):
    client = self._client(
      [
        _worker('r', 'RUNNING', 'RUNNING', pid=5),
        _worker('s', 'STOPPED', 'STOPPED', stopped_at='2024-01-01T12:00:00'),
      ]
    )
    _, rows = self._rows(client)
    self.assertNotIn('(', rows[0][3])
    self.assertNotIn('(', rows[1][3])

  def test_stopped_with_timestamp(self):
    client = self._client([_worker('s', 'STOPPED', 'STOPPED', stopped_at='2024-01-01T12:00:00')])
    _, rows = self._rows(client)
    self.assertIn('Stopped', rows[0][5])
    self.assertIn('dim', rows[0][3])

  def test_truncates_long_params_and_shows_started(self):
    client = self._client(
      [
        _worker(
          'lp',
          'RUNNING',
          'RUNNING',
          started_at='2024-01-01T12:00:00',
          pid=5,
          parameters={'long_param_name_for_truncation': 'x' * 50},
        )
      ]
    )
    _, rows = self._rows(client)
    self.assertIn('Started', rows[0][5])
    self.assertTrue(rows[0][6].endswith('...'))

  def test_hides_older_stopped_beyond_two(self):
    client = self._client(
      [
        _worker('old1', 'STOPPED', 'STOPPED', stopped_at='2024-01-01T10:00:00'),
        _worker('old2', 'STOPPED', 'STOPPED', stopped_at='2024-01-01T11:00:00'),
        _worker('recent1', 'STOPPED', 'STOPPED', stopped_at='2024-01-01T12:00:00'),
        _worker('recent2', 'STOPPED', 'STOPPED', stopped_at='2024-01-01T13:00:00'),
        _worker('live', 'RUNNING', 'RUNNING', pid=3),
      ]
    )
    result, rows = self._rows(client)
    keys = [row[1] for row in rows]
    self.assertEqual(keys, ['recent1', 'recent2', 'live'])
    # The return value keeps the full history regardless of the display.
    self.assertEqual(len(result), 5)

  def test_truncation_caption_is_explicit(self):
    client = self._client(
      [_worker(f's{i}', 'STOPPED', 'STOPPED', stopped_at=f'2024-01-01T1{i}:00:00') for i in range(4)]
    )
    with patch('os.listdir', return_value=[]):
      buffer = StringIO()
      with patch('crazy_workers.cli.commands.status.console', return_value=Console(file=buffer, width=200)):
        show_status(client, self.workers_path)
    output = buffer.getvalue()
    self.assertIn('2 more stopped workers hidden', output)
    self.assertIn('--all', output)

  def test_show_all_disables_truncation(self):
    client = self._client(
      [_worker(f's{i}', 'STOPPED', 'STOPPED', stopped_at=f'2024-01-01T1{i}:00:00') for i in range(4)]
    )
    _, rows = self._rows(client, show_all=True)
    self.assertEqual(len(rows), 4)

  def test_start_pending_stopped_is_never_hidden(self):
    client = self._client(
      [_worker(f's{i}', 'STOPPED', 'STOPPED', stopped_at=f'2024-01-01T1{i}:00:00') for i in range(3)]
      + [_worker('starting', 'STOPPED', 'RUNNING', stopped_at='2024-01-01T09:00:00')]
    )
    _, rows = self._rows(client)
    keys = [row[1] for row in rows]
    self.assertIn('starting', keys)
    self.assertIn('start pending', rows[keys.index('starting')][3])

  def test_formats_system_pid_when_namespace_pid_differs(self):
    self.assertEqual(_format_pid({'pid': 17, 'system_pid': 4321}), '4321 [dim](ns 17)[/dim]')

  def test_formats_pid_without_namespace_mapping(self):
    self.assertEqual(_format_pid({'pid': 17, 'system_pid': 17}), '17')


class TestCliStatusJson(BaseTestCase):
  def _client(self, workers):
    client = MagicMock()
    client.list.return_value = workers
    return client

  def test_json_mode_outputs_valid_json(self):
    workers = [
      _worker('w1', 'RUNNING', 'RUNNING', started_at='2024-01-01T12:00:00', pid=42, parameters={'vault_path': '/x'})
    ]
    with patch('os.listdir', return_value=[]):
      with patch('sys.stdout', new=StringIO()) as fake_out:
        show_status(self._client(workers), self.workers_path, json_mode=True)
        data = json.loads(fake_out.getvalue())
    self.assertIn('workers', data)
    self.assertEqual(len(data['workers']), 1)
    self.assertEqual(data['workers'][0]['worker_key'], 'w1')
    self.assertEqual(data['workers'][0]['desired_status'], 'RUNNING')
    self.assertEqual(data['workers'][0]['status'], 'RUNNING')
    self.assertEqual(data['workers'][0]['system_pid'], 42)

  def test_json_mode_never_truncates_stopped_workers(self):
    workers = [_worker(f's{i}', 'STOPPED', 'STOPPED', stopped_at=f'2024-01-01T1{i}:00:00') for i in range(5)]
    with patch('os.listdir', return_value=[]):
      with patch('sys.stdout', new=StringIO()) as fake_out:
        show_status(self._client(workers), self.workers_path, json_mode=True)
        data = json.loads(fake_out.getvalue())
    self.assertEqual(len(data['workers']), 5)

  def test_json_mode_empty_returns_empty_list(self):
    with patch('os.listdir', return_value=[]):
      with patch('sys.stdout', new=StringIO()) as fake_out:
        show_status(self._client([]), self.workers_path, json_mode=True)
        data = json.loads(fake_out.getvalue())
    self.assertEqual(data, {'workers': []})

  def test_json_mode_suppresses_rich_output(self):
    workers = [_worker('w1', 'RUNNING', 'RUNNING', pid=1)]
    with patch('os.listdir', return_value=[]):
      with patch('sys.stdout', new=StringIO()) as fake_out:
        show_status(self._client(workers), self.workers_path, json_mode=True)
        output = fake_out.getvalue()
    # must be valid JSON and contain nothing else
    data = json.loads(output.strip())
    self.assertIn('workers', data)


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
