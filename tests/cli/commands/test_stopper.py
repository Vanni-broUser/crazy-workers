from io import StringIO
from unittest.mock import MagicMock, patch

from crazy_workers.cli.commands import stop_worker
from tests.base import BaseTestCase


class TestCliCommandStopper(BaseTestCase):
  def test_stop_worker_interactive_no_running(self):
    self.manager.list_workers = MagicMock(
      return_value=[{'worker_key': 'k1', 'worker_type': 't1', 'status': 'STOPPED', 'pid': None}]
    )
    with patch('sys.stdout', new=StringIO()) as fake_out:
      res = stop_worker(self.manager, None)
      self.assertFalse(res)
      self.assertIn('No running workers to stop', fake_out.getvalue())

  def test_stop_worker_interactive_selection(self):
    self.manager.list_workers = MagicMock(
      return_value=[
        {'worker_key': 'k1', 'worker_type': 't1', 'status': 'RUNNING', 'pid': 123},
        {'worker_key': 'k2', 'worker_type': 't2', 'status': 'STOPPED', 'pid': None},
      ]
    )
    self.manager.stop_worker = MagicMock(return_value=(True, 'Stopped'))

    with patch('rich.prompt.IntPrompt.ask', return_value=1):
      with patch('sys.stdout', new=StringIO()):
        res = stop_worker(self.manager, None)
        self.assertTrue(res)
        self.manager.stop_worker.assert_called_with('k1')
