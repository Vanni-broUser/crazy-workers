from io import StringIO
from unittest.mock import MagicMock, patch

from crazy_workers.cli.commands import list_workers, start_worker, stop_worker
from tests.base import BaseTestCase


class TestCliInteractive(BaseTestCase):
  def test_list_workers_empty(self):
    self.manager.list_workers = MagicMock(return_value=[])
    with patch('sys.stdout', new=StringIO()) as fake_out:
      res = list_workers(self.manager)
      self.assertEqual(res, [])
      self.assertIn('No workers found', fake_out.getvalue())

  def test_stop_worker_interactive_no_running(self):
    # Mock list_workers to return only STOPPED workers
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

    # Mock IntPrompt to select the first one (k1)
    with patch('rich.prompt.IntPrompt.ask', return_value=1):
      with patch('sys.stdout', new=StringIO()):
        res = stop_worker(self.manager, None)
        self.assertTrue(res)
        self.manager.stop_worker.assert_called_with('k1')

  def test_start_worker_interactive_no_files(self):
    with patch('os.listdir', return_value=[]):
      with patch('sys.stdout', new=StringIO()) as fake_out:
        res = start_worker(self.manager, None)
        self.assertFalse(res)
        self.assertIn('No worker scripts found', fake_out.getvalue())

  def test_start_worker_interactive_selection(self):
    with patch('os.listdir', return_value=['w1.py', 'w2.py', 'not_python.txt']):
      self.manager.start_worker = MagicMock(return_value=(True, {'worker_key': 'w1', 'worker_type': 'w1', 'pid': 456}))
      # Select 'w1' (first in alphabetical order: w1, w2)
      with patch('rich.prompt.IntPrompt.ask', return_value=1):
        with patch('sys.stdout', new=StringIO()):
          res = start_worker(self.manager, None)
          self.assertTrue(res)
          self.manager.start_worker.assert_called_with('w1', worker_key=None, parameters=None)

  def test_start_worker_error_reading_dir(self):
    with patch('os.listdir', side_effect=OSError('Permission denied')):
      with patch('sys.stderr', new=StringIO()) as fake_err:
        res = start_worker(self.manager, None)
        self.assertFalse(res)
        self.assertIn('Error reading workers directory', fake_err.getvalue())
