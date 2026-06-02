import json
import os
import shutil
import sys
import time
import unittest
from io import StringIO
from unittest.mock import patch

from tests.base import BaseTestCase

_WORKERS_SRC = os.path.join(
  os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))),
  'example_app',
  'workers',
)


class TestBatchWorkerUnit(unittest.TestCase):
  def _run(self, params=None):
    argv = ['batch_worker.py', json.dumps(params)] if params is not None else ['batch_worker.py']
    with patch.object(sys, 'argv', argv), patch('time.sleep'), patch('sys.stdout', new_callable=StringIO) as out:
      from example_app.workers import batch_worker

      batch_worker.main()
      return out.getvalue()

  def test_default_params(self):
    output = self._run()
    self.assertIn('task1', output)
    self.assertIn('task2', output)
    self.assertIn('task3', output)
    self.assertIn('completed', output)

  def test_custom_items(self):
    output = self._run({'items': ['x', 'y'], 'delay': 0})
    self.assertIn('Processing: x', output)
    self.assertIn('Processing: y', output)
    self.assertIn('2/2', output)

  def test_progress_format(self):
    output = self._run({'items': ['a', 'b', 'c'], 'delay': 0})
    self.assertIn('1/3', output)
    self.assertIn('3/3', output)

  def test_empty_items(self):
    output = self._run({'items': [], 'delay': 0})
    self.assertIn('0 items', output)
    self.assertIn('completed', output)


class TestBatchWorkerSmoke(BaseTestCase):
  def setUp(self):
    super().setUp()
    shutil.copy(os.path.join(_WORKERS_SRC, 'batch_worker.py'), self.workers_path)

  def _log(self, worker_key):
    return os.path.join(self.workers_path, '.service', 'logs', f'{worker_key}.log')

  def test_processes_items_and_logs(self):
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
