import os
import psutil
import shutil
import time
from unittest.mock import MagicMock, patch

from crazy_workers import WorkerStatus
from crazy_workers.database.schema import Worker
from tests.base import BaseTestCase


_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))


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
      mock_proc.children.return_value = []
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

  def test_stop_kills_raw_subprocess_children(self):
    """stop_worker() must terminate unmanaged child processes (e.g. ffmpeg)."""
    shutil.copy(
      os.path.join(_ROOT, 'example_app', 'workers', 'subprocess_worker.py'),
      os.path.join(self.workers_path, 'subprocess_worker.py'),
    )

    pid_file = os.path.join(self.test_dir, 'child.pid')
    success, result = self.manager.start_worker(
      'subprocess_worker', worker_key='sub_test', parameters={'pid_file': pid_file}
    )
    self.assertTrue(success, f'Worker failed to start: {result}')

    # Wait for child PID file to appear.
    for _ in range(30):
      if os.path.exists(pid_file):
        break
      time.sleep(0.5)
    self.assertTrue(os.path.exists(pid_file), 'Child PID file never appeared')

    child_pid = int(open(pid_file).read().strip())
    self.assertTrue(psutil.pid_exists(child_pid), 'Child should be alive before stop')

    self.manager.stop_worker('sub_test')
    time.sleep(1)

    self.assertFalse(psutil.pid_exists(child_pid), 'Raw subprocess child must be dead after stop_worker')

  def test_stop_preserves_managed_nested_workers(self):
    """stop_worker() must NOT kill children that are registered crazy-workers."""
    for name in ['nested_worker.py', 'infinite_worker.py']:
      shutil.copy(
        os.path.join(_ROOT, 'example_app', 'workers', name),
        os.path.join(self.workers_path, name),
      )

    success, _ = self.manager.start_worker(
      'nested_worker',
      worker_key='parent_nested',
      parameters={'child_type': 'infinite_worker', 'num_children': 1, 'workers_dir': self.workers_path},
    )
    self.assertTrue(success)
    time.sleep(2)  # let parent spawn child

    workers = self.manager.list_workers()
    child = next((w for w in workers if w['worker_key'] == 'child_0'), None)
    self.assertIsNotNone(child, 'Nested child worker not found in DB')
    self.assertEqual(child['status'], 'RUNNING')
    child_pid = child['pid']

    self.manager.stop_worker('parent_nested')
    time.sleep(1)

    self.assertTrue(psutil.pid_exists(child_pid), 'Managed nested worker must survive parent stop')

    # Cleanup child
    self.manager.stop_worker('child_0')
