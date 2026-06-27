import os
import psutil
import subprocess
import sys
import tempfile
from unittest.mock import MagicMock, mock_open, patch

from crazy_workers.core.engine import (
  get_running_process,
  is_process_running,
  is_worker_process,
  resolve_system_pid,
  terminate_process,
  worker_key_token,
)
from tests.base import BaseTestCase


class TestEngine(BaseTestCase):
  def test_is_process_running_none_pid(self):
    self.assertFalse(is_process_running(None))

  def test_is_process_running_dead_pid(self):
    self.assertFalse(is_process_running(99999999))

  def test_is_process_running_live_process(self):
    proc = subprocess.Popen([sys.executable, '-c', 'import time; time.sleep(10)'])
    try:
      self.assertTrue(is_process_running(proc.pid))
    finally:
      proc.terminate()
      proc.wait()

  def test_is_process_running_psutil_error(self):
    with patch('crazy_workers.core.engine.psutil.Process', side_effect=psutil.AccessDenied(pid=123)):
      self.assertFalse(is_process_running(123))

  def test_get_running_process_returns_none_for_dead_pid(self):
    self.assertIsNone(get_running_process(99999999))

  def test_get_running_process_returns_none_for_none(self):
    self.assertIsNone(get_running_process(None))

  def test_terminate_process_already_dead(self):
    # Should return True without raising when the process doesn't exist
    result = terminate_process(99999999)
    self.assertTrue(result)

  def test_terminate_process_graceful(self):
    proc = subprocess.Popen([sys.executable, '-c', 'import time; time.sleep(10)'])
    pid = proc.pid
    self.assertTrue(is_process_running(pid))

    result = terminate_process(pid, popen_process=proc)
    self.assertTrue(result)

    self.wait_for_pid_dead(pid)

  def test_terminate_process_kills_on_timeout(self):
    mock_proc = MagicMock(spec=psutil.Process)
    mock_proc.is_running.return_value = True
    mock_proc.status.return_value = psutil.STATUS_RUNNING
    mock_proc.children.return_value = []

    mock_popen = MagicMock()
    # First wait() times out; second wait() (after kill) succeeds.
    mock_popen.wait.side_effect = [subprocess.TimeoutExpired(cmd='test', timeout=1), None]

    with patch('crazy_workers.core.engine.get_running_process', return_value=mock_proc):
      terminate_process(123, popen_process=mock_popen, timeout=1)

    mock_popen.kill.assert_called_once()
    self.assertEqual(mock_popen.wait.call_count, 2)

  def test_is_process_running_oserror(self):
    with patch('crazy_workers.core.engine.get_running_process', side_effect=OSError('disk error')):
      self.assertFalse(is_process_running(123))

  def test_resolve_system_pid_none(self):
    self.assertIsNone(resolve_system_pid(None))

  def test_resolve_system_pid_windows_returns_control_pid(self):
    with patch('crazy_workers.core.engine.os.name', 'nt'):
      self.assertEqual(resolve_system_pid(123), 123)

  def test_resolve_system_pid_reads_linux_nspid(self):
    with patch('crazy_workers.core.engine.os.name', 'posix'):
      with patch('builtins.open', mock_open(read_data='Name:\tpython\nNSpid:\t4321\t17\n')):
        self.assertEqual(resolve_system_pid(17), 4321)

  def test_resolve_system_pid_reads_host_proc_mount(self):
    with tempfile.TemporaryDirectory() as host_proc:
      proc_dir = f'{host_proc}/4321'

      os.mkdir(proc_dir)
      with open(f'{proc_dir}/status', 'w', encoding='utf-8') as f:
        f.write('Name:\tpython\nNSpid:\t4321\t17\n')
      with open(f'{proc_dir}/cmdline', 'wb') as f:
        f.write(b'python\0-u\0--cw-key=register_1\0')

      with patch('crazy_workers.core.engine.os.name', 'posix'):
        with patch.dict(os.environ, {'CRAZY_WORKERS_HOST_PROC': host_proc}):
          self.assertEqual(resolve_system_pid(17, worker_key='register_1'), 4321)

  def test_resolve_system_pid_ignores_host_proc_key_mismatch(self):
    with tempfile.TemporaryDirectory() as host_proc:
      proc_dir = f'{host_proc}/4321'

      os.mkdir(proc_dir)
      with open(f'{proc_dir}/status', 'w', encoding='utf-8') as f:
        f.write('Name:\tpython\nNSpid:\t4321\t17\n')
      with open(f'{proc_dir}/cmdline', 'wb') as f:
        f.write(b'python\0-u\0--cw-key=other\0')

      with patch('crazy_workers.core.engine.os.name', 'posix'):
        with patch.dict(os.environ, {'CRAZY_WORKERS_HOST_PROC': host_proc}):
          self.assertEqual(resolve_system_pid(17, worker_key='register_1'), 17)

  def test_resolve_system_pid_falls_back_on_proc_error(self):
    with patch('crazy_workers.core.engine.os.name', 'posix'):
      with patch('builtins.open', side_effect=OSError('no proc')):
        self.assertEqual(resolve_system_pid(17), 17)

  def test_terminate_exclude_pids_psutil_error(self):
    mock_proc = MagicMock(spec=psutil.Process)
    mock_proc.children.return_value = []
    with patch('crazy_workers.core.engine.get_running_process', return_value=mock_proc):
      with patch('crazy_workers.core.engine.psutil.Process', side_effect=psutil.AccessDenied(pid=99)):
        terminate_process(123, exclude_pids={99})
    # lines 51-52: AccessDenied while building exclusion set descendants — should not raise

  def test_terminate_children_snapshot_fails(self):
    mock_proc = MagicMock(spec=psutil.Process)
    mock_proc.children.side_effect = psutil.AccessDenied(pid=123)
    with patch('crazy_workers.core.engine.get_running_process', return_value=mock_proc):
      terminate_process(123)
    # lines 59-60: children snapshot raises → children = []

  def test_terminate_child_terminate_fails(self):
    mock_child = MagicMock(spec=psutil.Process)
    mock_child.pid = 456
    mock_child.terminate.side_effect = psutil.NoSuchProcess(pid=456)

    mock_proc = MagicMock(spec=psutil.Process)
    mock_proc.children.return_value = [mock_child]
    mock_proc.wait.return_value = None

    with patch('crazy_workers.core.engine.get_running_process', return_value=mock_proc):
      terminate_process(123)
    # lines 66-67: child.terminate() raises NoSuchProcess — swallowed correctly

  def test_terminate_kills_children_on_psutil_timeout(self):
    mock_child = MagicMock(spec=psutil.Process)
    mock_child.pid = 456
    mock_child.is_running.return_value = True

    mock_proc = MagicMock(spec=psutil.Process)
    mock_proc.children.return_value = [mock_child]
    mock_proc.wait.side_effect = psutil.TimeoutExpired(seconds=1)

    with patch('crazy_workers.core.engine.get_running_process', return_value=mock_proc):
      terminate_process(123, timeout=1)

    mock_proc.kill.assert_called_once()
    mock_child.kill.assert_called_once()

  def test_terminate_child_kill_after_timeout_fails(self):
    mock_child = MagicMock(spec=psutil.Process)
    mock_child.pid = 456
    mock_child.is_running.side_effect = psutil.NoSuchProcess(pid=456)

    mock_proc = MagicMock(spec=psutil.Process)
    mock_proc.children.return_value = [mock_child]
    mock_proc.wait.side_effect = psutil.TimeoutExpired(seconds=1)

    with patch('crazy_workers.core.engine.get_running_process', return_value=mock_proc):
      terminate_process(123, timeout=1)
    # lines 84-85: child.is_running() raises — swallowed correctly

  def test_worker_key_token_format(self):
    self.assertEqual(worker_key_token('job_1'), '--cw-key=job_1')

  def test_is_worker_process_dead_pid(self):
    self.assertFalse(is_worker_process(99999999, 'anything'))

  def test_is_worker_process_matches_injected_token(self):
    token = worker_key_token('identity_key')
    proc = subprocess.Popen([sys.executable, '-c', 'import time; time.sleep(10)', token])
    try:
      self.assertTrue(is_worker_process(proc.pid, 'identity_key'))
      # A different key must NOT match the same process.
      self.assertFalse(is_worker_process(proc.pid, 'other_key'))
    finally:
      proc.terminate()
      proc.wait()

  def test_is_worker_process_live_process_without_token(self):
    # Simulates a recycled PID now held by an unrelated process.
    proc = subprocess.Popen([sys.executable, '-c', 'import time; time.sleep(10)'])
    try:
      self.assertFalse(is_worker_process(proc.pid, 'identity_key'))
    finally:
      proc.terminate()
      proc.wait()

  def test_is_worker_process_cmdline_unreadable(self):
    mock_proc = MagicMock(spec=psutil.Process)
    mock_proc.cmdline.side_effect = psutil.AccessDenied(pid=123)
    with patch('crazy_workers.core.engine.get_running_process', return_value=mock_proc):
      self.assertFalse(is_worker_process(123, 'identity_key'))

  def test_terminate_unexpected_exception_reraised(self):
    mock_proc = MagicMock(spec=psutil.Process)
    mock_proc.children.return_value = []
    mock_proc.terminate.side_effect = RuntimeError('something went wrong')

    with patch('crazy_workers.core.engine.get_running_process', return_value=mock_proc):
      with self.assertRaises(RuntimeError):
        terminate_process(123)
    # lines 88-90: unexpected exception is logged and re-raised
