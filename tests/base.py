import os
import psutil
import shutil
import time
import unittest
import warnings

from crazy_workers import WorkerManager


class BaseTestCase(unittest.TestCase):
  def setUp(self):
    # Suppress ResourceWarnings for orphaned subprocesses (intended behavior)
    warnings.filterwarnings('ignore', category=ResourceWarning)

    # Track existing processes to detect leaks
    self._initial_pids = {p.pid for p in psutil.process_iter(attrs=['pid'])}

    # Create a unique temporary workers directory for each test
    self.test_dir = f'test_env_{self._testMethodName}'
    os.makedirs(self.test_dir, exist_ok=True)

    # Copy example worker to the test dir
    src_worker = os.path.join(
      os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'example_app', 'workers', 'example_worker.py'
    )

    self.workers_path = os.path.join(self.test_dir, 'workers')
    os.makedirs(self.workers_path, exist_ok=True)
    self.worker_file = os.path.join(self.workers_path, 'example_worker.py')
    shutil.copy(src_worker, self.worker_file)

    self.manager = WorkerManager(self.workers_path)

  def tearDown(self):
    # Stop all workers — let exceptions surface so leaked workers don't mask test failures
    workers = self.manager.list_workers()
    for w in workers:
      if w['status'] == 'RUNNING':
        self.manager.stop_worker(w['worker_key'])

    self.manager.dispose()

    # Cleanup the entire test environment
    if os.path.exists(self.test_dir):
      shutil.rmtree(self.test_dir)

    # Verify no leaked processes
    current_pids = {p.pid for p in psutil.process_iter(attrs=['pid'])}
    leaked = current_pids - self._initial_pids

    # Filter out the current process PID
    leaked.discard(os.getpid())

    if leaked:
      # Some processes might be transient or unrelated to the test.
      # We check if any of them are actually Python processes running our scripts.
      real_leaks = []
      for pid in leaked:
        try:
          p = psutil.Process(pid)
          cmd = ' '.join(p.cmdline())
          if 'python' in cmd.lower() and self.workers_path in cmd:
            real_leaks.append(f'PID {pid}: {cmd}')
        except (psutil.NoSuchProcess, psutil.AccessDenied):
          continue

      if real_leaks:
        raise RuntimeError('Test leaked processes:\n' + '\n'.join(real_leaks))

  # ---------------------------------------------------------------------------
  # Polling helpers — use these instead of time.sleep() in tests
  # ---------------------------------------------------------------------------

  def wait_for(self, condition, timeout=10.0, interval=0.05, msg='Condition never met'):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
      if condition():
        return
      time.sleep(interval)
    raise AssertionError(msg)

  def wait_for_file(self, path, timeout=10.0):
    self.wait_for(lambda: os.path.exists(path), timeout=timeout, msg=f'File never appeared: {path}')

  def wait_for_log(self, log_path, text, timeout=10.0):
    def check():
      if not os.path.exists(log_path):
        return False
      with open(log_path) as f:
        return text in f.read()

    self.wait_for(check, timeout=timeout, msg=f'{text!r} not found in {log_path}')

  def wait_for_worker_status(self, manager, key, status, timeout=10.0):
    def check():
      workers = manager.list_workers()
      w = next((w for w in workers if w['worker_key'] == key), None)
      return w is not None and w['status'] == status

    self.wait_for(check, timeout=timeout, msg=f'Worker {key!r} never reached status {status!r}')

  def wait_for_worker_in_db(self, manager, key, timeout=10.0):
    def check():
      return any(w['worker_key'] == key for w in manager.list_workers())

    self.wait_for(check, timeout=timeout, msg=f'Worker {key!r} never appeared in DB')

  def wait_for_worker_pid(self, manager, key, timeout=10.0):
    def check():
      w = next((w for w in manager.list_workers() if w['worker_key'] == key), None)
      return w is not None and w['pid'] is not None

    self.wait_for(check, timeout=timeout, msg=f'Worker {key!r} never got a PID')

  def wait_for_pid_dead(self, pid, timeout=10.0):
    self.wait_for(lambda: not psutil.pid_exists(pid), timeout=timeout, msg=f'PID {pid} never died')
