"""
Integration tests for nested worker scenarios — a parent worker that spawns
children via its own WorkerManager instance.
"""

import os
import psutil
import shutil
import time

from tests.base import BaseTestCase


_WORKERS_SRC = os.path.join(
  os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
  'example_app',
  'workers',
)


class TestNestedWorkers(BaseTestCase):
  def setUp(self):
    super().setUp()
    for name in ['nested_worker.py', 'infinite_worker.py']:
      shutil.copy(os.path.join(_WORKERS_SRC, name), self.workers_path)

  def test_children_registered_in_db(self):
    success, result = self.manager.start_worker(
      'nested_worker',
      worker_key='parent_test',
      parameters={'child_type': 'infinite_worker', 'num_children': 2, 'workers_dir': self.workers_path},
    )
    self.assertTrue(success, f'Parent failed to start: {result}')
    time.sleep(2)

    workers = self.manager.list_workers()
    keys = [w['worker_key'] for w in workers]
    self.assertIn('parent_test', keys)
    self.assertIn('child_0', keys)
    self.assertIn('child_1', keys)

    for child_key in ('child_0', 'child_1'):
      child = next(w for w in workers if w['worker_key'] == child_key)
      self.assertEqual(child['status'], 'RUNNING')
      self.assertIsNotNone(child['pid'])

    self.manager.stop_worker('parent_test')
    self.manager.stop_worker('child_0')
    self.manager.stop_worker('child_1')

  def test_children_survive_parent_stop(self):
    self.manager.start_worker(
      'nested_worker',
      worker_key='parent_survive',
      parameters={'child_type': 'infinite_worker', 'num_children': 1, 'workers_dir': self.workers_path},
    )
    time.sleep(2)

    workers = self.manager.list_workers()
    child = next((w for w in workers if w['worker_key'] == 'child_0'), None)
    self.assertIsNotNone(child, 'Child not found in DB')
    child_pid = child['pid']

    self.manager.stop_worker('parent_survive')
    time.sleep(1)

    self.assertTrue(psutil.pid_exists(child_pid), 'Child must survive parent termination')

    workers = self.manager.list_workers()
    child = next(w for w in workers if w['worker_key'] == 'child_0')
    self.assertEqual(child['status'], 'RUNNING')
    self.manager.stop_worker('child_0')
