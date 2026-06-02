import os
import psutil
import shutil
import sys
import unittest
from unittest.mock import MagicMock, patch

from tests.base import BaseTestCase


_WORKERS_SRC = os.path.join(
  os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))),
  'example_app',
  'workers',
)


class TestNestedWorkerUnit(unittest.TestCase):
  def setUp(self):
    from example_app.workers import nested_worker

    self.mod = nested_worker

  def _make_manager(self, success=True):
    mgr = MagicMock()
    mgr.start_worker.return_value = (success, {})
    return mgr

  def test_spawns_children(self):
    mgr = self._make_manager(success=True)
    argv = ['nested_worker.py', '{"child_type": "fake", "num_children": 2, "workers_dir": "/tmp"}']
    with (
      patch.object(sys, 'argv', argv),
      patch('time.sleep'),
      patch('example_app.workers.nested_worker.WorkerManager', return_value=mgr),
      self.assertLogs(level='INFO') as log,
    ):
      self.mod.main()
    self.assertEqual(mgr.start_worker.call_count, 2)
    joined = '\n'.join(log.output)
    self.assertIn('child_0', joined)
    self.assertIn('child_1', joined)

  def test_failed_child_logged(self):
    mgr = self._make_manager(success=False)
    argv = ['nested_worker.py', '{"child_type": "fake", "num_children": 1, "workers_dir": "/tmp"}']
    with (
      patch.object(sys, 'argv', argv),
      patch('time.sleep'),
      patch('example_app.workers.nested_worker.WorkerManager', return_value=mgr),
      self.assertLogs(level='WARNING') as log,
    ):
      self.mod.main()
    self.assertTrue(any('Failed' in line for line in log.output))

  def test_default_params(self):
    mgr = self._make_manager()
    with (
      patch.object(sys, 'argv', ['nested_worker.py']),
      patch('time.sleep'),
      patch('example_app.workers.nested_worker.WorkerManager', return_value=mgr),
      self.assertLogs(level='INFO'),
    ):
      self.mod.main()
    self.assertEqual(mgr.start_worker.call_count, 2)

  def test_dispose_called_on_exit(self):
    mgr = self._make_manager()
    with (
      patch.object(sys, 'argv', ['nested_worker.py']),
      patch('time.sleep'),
      patch('example_app.workers.nested_worker.WorkerManager', return_value=mgr),
      self.assertLogs(level='INFO'),
    ):
      self.mod.main()
    mgr.dispose.assert_called_once()


class TestNestedWorkerSmoke(BaseTestCase):
  def setUp(self):
    super().setUp()
    for name in ['nested_worker.py', 'infinite_worker.py']:
      shutil.copy(os.path.join(_WORKERS_SRC, name), self.workers_path)

  def test_starts_and_children_registered(self):
    success, _ = self.manager.start_worker(
      'nested_worker',
      worker_key='smoke_nested',
      parameters={'child_type': 'infinite_worker', 'num_children': 1, 'workers_dir': self.workers_path},
    )
    self.assertTrue(success)
    self.wait_for_worker_in_db(self.manager, 'child_0')
    workers = self.manager.list_workers()
    self.assertTrue(any(w['worker_key'] == 'child_0' for w in workers))
    self.manager.stop_worker('smoke_nested')
    self.manager.stop_worker('child_0')


class TestNestedWorkerIntegration(BaseTestCase):
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
    self.wait_for_worker_in_db(self.manager, 'child_0')
    self.wait_for_worker_in_db(self.manager, 'child_1')

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
    self.wait_for_worker_in_db(self.manager, 'child_0')

    workers = self.manager.list_workers()
    child = next((w for w in workers if w['worker_key'] == 'child_0'), None)
    self.assertIsNotNone(child, 'Child not found in DB')
    child_pid = child['pid']

    self.manager.stop_worker('parent_survive')

    self.assertTrue(psutil.pid_exists(child_pid), 'Child must survive parent termination')
    workers = self.manager.list_workers()
    child = next(w for w in workers if w['worker_key'] == 'child_0')
    self.assertEqual(child['status'], 'RUNNING')
    self.manager.stop_worker('child_0')
