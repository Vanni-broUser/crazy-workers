import json
import os
import sys
import time
import unittest
from io import StringIO
from unittest.mock import patch

from tests.base import BaseTestCase


class TestSimulatorWorkerUnit(unittest.TestCase):
  def _run(self, params=None, expect_exit=False):
    argv = ['simulator_worker.py', json.dumps(params)] if params is not None else ['simulator_worker.py']
    with patch.object(sys, 'argv', argv), patch('time.sleep'), patch('sys.stdout', new_callable=StringIO) as out:
      from example_app.workers import simulator_worker

      if expect_exit:
        with self.assertRaises(SystemExit) as ctx:
          simulator_worker.main()
        return out.getvalue(), ctx.exception.code
      else:
        simulator_worker.main()
        return out.getvalue(), 0

  def test_default_params(self):
    output, code = self._run()
    self.assertIn('10 steps', output)
    self.assertIn('completed', output)
    self.assertEqual(code, 0)

  def test_custom_steps(self):
    output, code = self._run({'steps': 3})
    self.assertIn('3/3', output)
    self.assertIn('completed', output)

  def test_fail_at(self):
    output, code = self._run({'steps': 5, 'fail_at': 3}, expect_exit=True)
    self.assertIn('simulating failure', output)
    self.assertEqual(code, 1)

  def test_fail_at_first_step(self):
    _, code = self._run({'steps': 5, 'fail_at': 1}, expect_exit=True)
    self.assertEqual(code, 1)

  def test_no_failure_when_fail_at_exceeds_steps(self):
    output, code = self._run({'steps': 3, 'fail_at': 99})
    self.assertIn('completed', output)


class TestSimulatorWorkerSmoke(BaseTestCase):
  def setUp(self):
    super().setUp()
    import shutil
    _src = os.path.join(
      os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))),
      'example_app', 'workers',
    )
    shutil.copy(os.path.join(_src, 'simulator_worker.py'), self.workers_path)

  def test_runs_steps_and_stops(self):
    success, _ = self.manager.start_worker('simulator_worker', worker_key='smoke_simulator', parameters={'steps': 3})
    self.assertTrue(success)
    time.sleep(0.5)
    self.manager.stop_worker('smoke_simulator')
