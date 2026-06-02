import json
import os
import sys
import unittest
from unittest.mock import MagicMock, mock_open, patch

from tests.base import BaseTestCase


_WORKERS_SRC = os.path.join(
  os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))),
  'example_app',
  'workers',
)


class TestSubprocessWorkerUnit(unittest.TestCase):
  def setUp(self):
    from example_app.workers import subprocess_worker

    self.mod = subprocess_worker

  def _make_child(self, pid=1234):
    child = MagicMock()
    child.pid = pid
    return child

  def test_starts_child_process(self):
    child = self._make_child()
    with (
      patch.object(sys, 'argv', ['subprocess_worker.py']),
      patch('subprocess.Popen', return_value=child) as mock_popen,
      patch('time.sleep', side_effect=KeyboardInterrupt),
    ):
      self.mod.main()
    mock_popen.assert_called_once()

  def test_writes_pid_file(self):
    child = self._make_child(pid=9999)
    argv = ['subprocess_worker.py', json.dumps({'pid_file': '/tmp/test.pid'})]
    m = mock_open()
    with (
      patch.object(sys, 'argv', argv),
      patch('subprocess.Popen', return_value=child),
      patch('builtins.open', m),
      patch('time.sleep', side_effect=KeyboardInterrupt),
    ):
      self.mod.main()
    m.assert_called_once_with('/tmp/test.pid', 'w')
    m().write.assert_called_once_with('9999')

  def test_no_pid_file_skips_write(self):
    child = self._make_child()
    with (
      patch.object(sys, 'argv', ['subprocess_worker.py']),
      patch('subprocess.Popen', return_value=child),
      patch('builtins.open', mock_open()) as m,
      patch('time.sleep', side_effect=KeyboardInterrupt),
    ):
      self.mod.main()
    m.assert_not_called()

  def test_child_terminated_on_exit(self):
    child = self._make_child()
    with (
      patch.object(sys, 'argv', ['subprocess_worker.py']),
      patch('subprocess.Popen', return_value=child),
      patch('time.sleep', side_effect=KeyboardInterrupt),
    ):
      self.mod.main()
    child.terminate.assert_called_once()
    child.wait.assert_called_once_with(timeout=3)

  def test_child_terminate_exception_suppressed(self):
    child = self._make_child()
    child.terminate.side_effect = OSError('already dead')
    with (
      patch.object(sys, 'argv', ['subprocess_worker.py']),
      patch('subprocess.Popen', return_value=child),
      patch('time.sleep', side_effect=KeyboardInterrupt),
    ):
      self.mod.main()
    child.terminate.assert_called_once()


class TestSubprocessWorkerSmoke(BaseTestCase):
  def setUp(self):
    super().setUp()
    import shutil

    shutil.copy(os.path.join(_WORKERS_SRC, 'subprocess_worker.py'), self.workers_path)

  def test_starts_child_and_writes_pid(self):
    pid_file = os.path.join(self.test_dir, 'child.pid')
    success, _ = self.manager.start_worker(
      'subprocess_worker', worker_key='smoke_subprocess', parameters={'pid_file': pid_file}
    )
    self.assertTrue(success)
    self.wait_for_file(pid_file)
    self.manager.stop_worker('smoke_subprocess')
