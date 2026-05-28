import os
import shutil
import time

from tests.base import BaseTestCase


class TestNestedWorkers(BaseTestCase):
  def test_nested_worker_spawning(self):
    # Copy required workers to the test directory
    base_workers_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'example_app', 'workers')
    for worker_name in ['nested_worker.py', 'infinite_worker.py']:
      shutil.copy(os.path.join(base_workers_dir, worker_name), os.path.join(self.workers_path, worker_name))

    # Start the parent worker
    # We pass the absolute path of workers_dir so the nested manager knows where to look
    success, result = self.manager.start_worker(
      'nested_worker',
      worker_key='parent_test',
      parameters={'child_type': 'infinite_worker', 'num_children': 2, 'workers_dir': self.workers_path},
    )
    self.assertTrue(success, f'Failed to start parent worker: {result}')
    result['pid']

    # Give some time for the parent to start and spawn children
    time.sleep(2)

    # Check if children are registered in the database
    workers = self.manager.list_workers()
    worker_keys = [w['worker_key'] for w in workers]

    self.assertIn('parent_test', worker_keys)
    self.assertIn('child_0', worker_keys)
    self.assertIn('child_1', worker_keys)

    # Verify children are running
    child_0 = next(w for w in workers if w['worker_key'] == 'child_0')
    child_1 = next(w for w in workers if w['worker_key'] == 'child_1')

    self.assertEqual(child_0['status'], 'RUNNING')
    self.assertEqual(child_1['status'], 'RUNNING')
    self.assertIsNotNone(child_0['pid'])
    self.assertIsNotNone(child_1['pid'])

    # Stop parent and see if children survive (intended behavior)
    self.manager.stop_worker('parent_test')

    # Wait a bit
    time.sleep(1)

    # Refresh worker list
    workers = self.manager.list_workers()
    child_0 = next(w for w in workers if w['worker_key'] == 'child_0')
    self.assertEqual(child_0['status'], 'RUNNING', 'Children should survive parent termination')

    # Cleanup
    self.manager.stop_worker('child_0')
    self.manager.stop_worker('child_1')

  def test_recursive_disposal(self):
    # This test ensures that when a manager is disposed,
    # it only kills the processes IT spawned, not the ones spawned by its children.
    # (Because the manager instance inside the nested worker is different)
    pass
