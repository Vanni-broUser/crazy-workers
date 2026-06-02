import json
import os
import sys
import time
import unittest
from io import StringIO
from unittest.mock import patch

from tests.base import BaseTestCase


class TestInfiniteWorkerUnit(unittest.TestCase):
  def setUp(self):
    from example_app.workers import infinite_worker
    self.mod = infinite_worker

  def test_keyboard_interrupt_exits_cleanly(self):
    argv = ['infinite_worker.py', json.dumps({'interval': 1})]
    with (
      patch.object(sys, 'argv', argv),
      patch('sys.stdout', new_callable=StringIO) as out,
      patch('time.sleep', side_effect=[None, KeyboardInterrupt]),
    ):
      self.mod.main()
    self.assertIn('interrupt', out.getvalue())

  def test_default_params_no_argv(self):
    with (
      patch.object(sys, 'argv', ['infinite_worker.py']),
      patch('sys.stdout', new_callable=StringIO) as out,
      patch('time.sleep', side_effect=[None, KeyboardInterrupt]),
    ):
      self.mod.main()
    self.assertIn('Starting infinite worker', out.getvalue())

  def test_unexpected_exception_exits_with_error(self):
    argv = ['infinite_worker.py', json.dumps({'interval': 1})]
    with (
      patch.object(sys, 'argv', argv),
      patch('sys.stdout', new_callable=StringIO),
      patch('sys.stderr', new_callable=StringIO) as err,
      patch('time.sleep', side_effect=[RuntimeError('boom')]),
    ):
      with self.assertRaises(SystemExit) as ctx:
        self.mod.main()
    self.assertEqual(ctx.exception.code, 1)
    self.assertIn('boom', err.getvalue())

  def test_custom_message(self):
    argv = ['infinite_worker.py', json.dumps({'interval': 0, 'message': 'hello world'})]
    with (
      patch.object(sys, 'argv', argv),
      patch('sys.stdout', new_callable=StringIO) as out,
      patch('time.sleep', side_effect=[None, KeyboardInterrupt]),
    ):
      self.mod.main()
    self.assertIn('hello world', out.getvalue())


class TestInfiniteWorkerSmoke(BaseTestCase):
  def setUp(self):
    super().setUp()
    import shutil
    import os
    _src = os.path.join(
      os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))),
      'example_app', 'workers',
    )
    shutil.copy(os.path.join(_src, 'infinite_worker.py'), self.workers_path)

  def test_starts_and_stops(self):
    success, result = self.manager.start_worker(
      'infinite_worker', worker_key='smoke_infinite', parameters={'interval': 1}
    )
    self.assertTrue(success)
    time.sleep(0.5)
    self.manager.stop_worker('smoke_infinite')
