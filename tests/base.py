import os
import shutil
import unittest
import warnings
import psutil

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
    # Stop all workers
    try:
      workers = self.manager.list_workers()
      for w in workers:
        if w['status'] == 'RUNNING':
          self.manager.stop_worker(w['worker_key'])
    except Exception:
      pass

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
          if 'python' in cmd.lower() and ('example_worker' in cmd or 'workers' in cmd):
            real_leaks.append(f'PID {pid}: {cmd}')
        except (psutil.NoSuchProcess, psutil.AccessDenied):
          continue

      if real_leaks:
        raise RuntimeError('Test leaked processes:\n' + '\n'.join(real_leaks))
