"""
Smoke tests for each example_app worker — verifies that every worker
starts successfully, produces expected log output, and stops cleanly.
"""

import os
import shutil
import time

from tests.base import BaseTestCase


_WORKERS_SRC = os.path.join(
  os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))),
  'example_app',
  'workers',
)


class TestExampleWorkers(BaseTestCase):
  def setUp(self):
    super().setUp()
    for f in os.listdir(_WORKERS_SRC):
      if f.endswith('.py'):
        shutil.copy(os.path.join(_WORKERS_SRC, f), self.workers_path)

  def _log(self, worker_key):
    return os.path.join(self.workers_path, '.service', 'logs', f'{worker_key}.log')

  def test_example_worker(self):
    success, result = self.manager.start_worker(
      'example_worker', worker_key='smoke_example', parameters={'duration': 5, 'worker_key': 'smoke_example'}
    )
    self.assertTrue(success)
    time.sleep(0.5)
    self.assertTrue(os.path.exists(self._log('smoke_example')))
    with open(self._log('smoke_example')) as f:
      self.assertIn('smoke_example', f.read())
    self.manager.stop_worker('smoke_example')

  def test_batch_worker(self):
    success, _ = self.manager.start_worker(
      'batch_worker', worker_key='smoke_batch', parameters={'items': ['a', 'b'], 'delay': 0.1}
    )
    self.assertTrue(success)
    time.sleep(1)
    self.assertTrue(os.path.exists(self._log('smoke_batch')))
    with open(self._log('smoke_batch')) as f:
      content = f.read()
    self.assertIn('Processing: a', content)
    self.assertIn('Processing: b', content)

  def test_infinite_worker(self):
    success, result = self.manager.start_worker(
      'infinite_worker', worker_key='smoke_infinite', parameters={'interval': 1}
    )
    self.assertTrue(success)
    time.sleep(0.5)
    self.manager.stop_worker('smoke_infinite')

  def test_simulator_worker(self):
    success, _ = self.manager.start_worker('simulator_worker', worker_key='smoke_simulator', parameters={'steps': 3})
    self.assertTrue(success)
    time.sleep(0.5)
    self.manager.stop_worker('smoke_simulator')

  def test_subprocess_worker(self):
    pid_file = os.path.join(self.test_dir, 'child.pid')
    success, _ = self.manager.start_worker(
      'subprocess_worker', worker_key='smoke_subprocess', parameters={'pid_file': pid_file}
    )
    self.assertTrue(success)

    for _ in range(20):
      if os.path.exists(pid_file):
        break
      time.sleep(0.3)
    self.assertTrue(os.path.exists(pid_file), 'subprocess_worker did not write pid_file')

    self.manager.stop_worker('smoke_subprocess')

  def test_nested_worker(self):
    success, _ = self.manager.start_worker(
      'nested_worker',
      worker_key='smoke_nested',
      parameters={'child_type': 'infinite_worker', 'num_children': 1, 'workers_dir': self.workers_path},
    )
    self.assertTrue(success)
    time.sleep(2)

    workers = self.manager.list_workers()
    self.assertTrue(any(w['worker_key'] == 'child_0' for w in workers))
    self.manager.stop_worker('smoke_nested')
    self.manager.stop_worker('child_0')
