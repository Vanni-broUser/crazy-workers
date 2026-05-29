import psutil
from unittest.mock import MagicMock, patch

from crazy_workers import WorkerStatus
from crazy_workers.database.schema import Worker
from tests.base import BaseTestCase


class TestManagerStopper(BaseTestCase):
  def test_library_stop_not_found(self):
    success, msg = self.manager.stop_worker('no_such_key')
    self.assertFalse(success)
    self.assertEqual(msg, 'Worker not found')

  def test_library_stop_not_running(self):
    self.manager.start_worker('example_worker', worker_key='not_running_key')
    self.manager.stop_worker('not_running_key')
    success, msg = self.manager.stop_worker('not_running_key')
    self.assertFalse(success)
    self.assertEqual(msg, 'Worker is not running')

  def test_library_stop_timeout(self):
    with patch('crazy_workers.core.engine.psutil.Process') as mock_process_class:
      mock_proc = MagicMock()
      mock_proc.wait.side_effect = psutil.TimeoutExpired(3)
      mock_process_class.return_value = mock_proc

      session = self.manager.storage.get_session()
      worker = Worker(
        worker_key='timeout_test', worker_type='example_worker', parameters={}, status=WorkerStatus.RUNNING, pid=12345
      )
      session.add(worker)
      session.commit()
      session.close()

      with patch('crazy_workers.core.engine.is_process_running', return_value=True):
        success, msg = self.manager.stop_worker('timeout_test')
        self.assertTrue(success)
        mock_proc.kill.assert_called_once()

  def test_library_stop_exception(self):
    with patch('crazy_workers.core.engine.psutil.Process', side_effect=Exception('Generic error')):
      session = self.manager.storage.get_session()
      worker = Worker(
        worker_key='exc_test', worker_type='example_worker', parameters={}, status=WorkerStatus.RUNNING, pid=12345
      )
      session.add(worker)
      session.commit()
      session.close()

      with patch('crazy_workers.core.engine.is_process_running', return_value=True):
        success, msg = self.manager.stop_worker('exc_test')
        self.assertFalse(success)
        self.assertEqual(msg, 'Generic error')
