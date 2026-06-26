from io import StringIO
from unittest.mock import MagicMock, patch

from crazy_workers.cli.commands import stop_worker
from tests.base import BaseTestCase


class TestCliCommandStopper(BaseTestCase):
  def test_stop_worker_interactive_no_desired_running(self):
    client = MagicMock()
    client.list.return_value = [
      {'worker_key': 'k1', 'worker_type': 't1', 'status': 'STOPPED', 'desired_status': 'STOPPED', 'pid': None},
    ]
    with patch('sys.stdout', new=StringIO()) as fake_out:
      res = stop_worker(client, None)
      self.assertFalse(res)
      self.assertIn('No workers desired RUNNING', fake_out.getvalue())

  def test_stop_worker_interactive_selection(self):
    client = MagicMock()
    client.list.return_value = [
      {'worker_key': 'k1', 'worker_type': 't1', 'status': 'RUNNING', 'desired_status': 'RUNNING', 'pid': 123},
      {'worker_key': 'k2', 'worker_type': 't2', 'status': 'STOPPED', 'desired_status': 'STOPPED', 'pid': None},
    ]
    client.request_stop.return_value = True

    with patch('rich.prompt.IntPrompt.ask', return_value=1):
      with patch('sys.stdout', new=StringIO()):
        res = stop_worker(client, None)
        self.assertTrue(res)
        client.request_stop.assert_called_with('k1')

  def test_stop_worker_explicit_ok(self):
    client = MagicMock()
    client.request_stop.return_value = True
    with patch('sys.stdout', new=StringIO()) as fake_out:
      res = stop_worker(client, 'k1')
      self.assertTrue(res)
      self.assertIn('Requested', fake_out.getvalue())
    client.request_stop.assert_called_with('k1')

  def test_stop_worker_explicit_not_found(self):
    client = MagicMock()
    client.request_stop.return_value = False
    with patch('sys.stderr', new=StringIO()) as fake_err:
      res = stop_worker(client, 'nope')
      self.assertFalse(res)
      self.assertIn('not found', fake_err.getvalue())
