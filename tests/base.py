import os
import shutil
import unittest

from crazy_workers import WorkerManager


class BaseTestCase(unittest.TestCase):
  def setUp(self):
    # Create a unique temporary workers directory for each test
    self.test_dir = f'test_env_{self._testMethodName}'
    os.makedirs(self.test_dir, exist_ok=True)

    # Copy example worker to the test dir
    src_worker = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'example_app', 'workers', 'example_worker.py')
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
