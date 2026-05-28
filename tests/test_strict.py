import os
import time
import psutil

from crazy_workers import WorkerManager
from crazy_workers.core.recovery import RecoveryLock
from tests.base import BaseTestCase


class TestStrictResilience(BaseTestCase):
  def setUp(self):
    super().setUp()
    # Copy all worker files for strict testing
    import shutil

    base_workers_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'example_app', 'workers')
    for worker_file in os.listdir(base_workers_dir):
      if worker_file.endswith('.py'):
        shutil.copy(os.path.join(base_workers_dir, worker_file), self.workers_path)

  def test_manual_kill_and_recovery(self):
    """Test that if a process is killed externally (SIGKILL), the manager recovers it."""
    # 1. Start a worker
    success, result = self.manager.start_worker('infinite_worker', worker_key='resilience_test')
    self.assertTrue(success)
    pid = result['pid']
    self.assertTrue(psutil.pid_exists(pid))

    # 2. Kill it brutally
    proc = psutil.Process(pid)
    proc.kill()  # Cross-platform SIGKILL

    # Wait for OS to clean up
    time.sleep(0.5)
    self.assertFalse(psutil.pid_exists(pid))

    # 3. Use a fresh manager to trigger recovery
    # (The old manager still has the PID in its internal _active_processes,
    # but more importantly, recover_workers looks for RUNNING in DB)
    self.manager.dispose()
    fresh_manager = WorkerManager(self.workers_path)

    # 4. Trigger recovery
    restarted = fresh_manager.recover_workers()
    self.assertIn('resilience_test', restarted)

    # 5. Verify it's running again with a NEW PID
    workers = fresh_manager.list_workers()
    worker = next(w for w in workers if w['worker_key'] == 'resilience_test')
    self.assertEqual(worker['status'], 'RUNNING')
    self.assertNotEqual(worker['pid'], pid)
    self.assertTrue(psutil.pid_exists(worker['pid']))
    fresh_manager.dispose()

  def test_log_file_capture(self):
    """Verify that worker output is actually captured in the dedicated log file."""
    # infinite_worker prints a start message. We'll use batch_worker for predictable output.
    import shutil

    base_workers_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'example_app', 'workers')
    shutil.copy(os.path.join(base_workers_dir, 'batch_worker.py'), self.workers_path)

    worker_key = 'log_test'
    self.manager.start_worker(
      'batch_worker', worker_key=worker_key, parameters={'items': ['test_item_123'], 'delay': 0.1}
    )

    # Wait for execution
    time.sleep(1)

    log_file_path = os.path.join(self.workers_path, '.service', 'logs', f'{worker_key}.log')
    self.assertTrue(os.path.exists(log_file_path), f'Log file missing at {log_file_path}')

    with open(log_file_path, 'r') as f:
      content = f.read()
      # We removed prints in ruff step, but I'll add them back to workers if needed or assume some output exists
      # Actually, ruff removed prints from my example workers. Let's verify if they have any output now.
      # For a strict test, the worker MUST produce output.
      self.assertIn('Processing: test_item_123', content)

  def test_path_traversal_attempts(self):
    """Aggressively test path traversal protection."""
    forbidden_keys = [
      '../outside',
      '../../etc/passwd',
      'C:\\Windows\\System32\\cmd.exe',
      'sub/../../../secret',
      '..\\..\\test',
    ]

    for key in forbidden_keys:
      success, message = self.manager.start_worker('example_worker', worker_key=key)
      self.assertFalse(success, f'Should have failed for key: {key}')
      self.assertIn('Invalid', message)

  def test_concurrent_recovery_lock(self):
    """Verify that multiple managers don't run recovery at the same time."""
    # This is tricky to test purely sequentially, but we can check the lock mechanism
    lock_path = os.path.join(self.test_dir, 'test.lock')

    lock1 = RecoveryLock(lock_path)
    lock2 = RecoveryLock(lock_path)

    self.assertTrue(lock1.acquire())
    self.assertFalse(lock2.acquire(), 'Second lock should not be acquirable')

    lock1.release()
    self.assertTrue(lock2.acquire(), 'Second lock should now be acquirable')
    lock2.release()
