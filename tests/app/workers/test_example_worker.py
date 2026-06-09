import json
import logging
import os
import sys
import unittest
from unittest.mock import patch

from tests.base import BaseTestCase


class TestExampleWorkerUnit(unittest.TestCase):
  def setUp(self):
    logging.disable(logging.CRITICAL)
    from example_app.workers import example_worker

    self.mod = example_worker

  def tearDown(self):
    logging.disable(logging.NOTSET)

  def test_missing_params_returns_early(self):
    with patch.object(sys, 'argv', ['example_worker.py']):
      self.mod.main()

  def test_runs_for_duration(self):
    argv = ['example_worker.py', json.dumps({'duration': 0, 'worker_key': 'test_w'})]
    with patch.object(sys, 'argv', argv), patch('time.sleep'):
      self.mod.main()

  def test_signal_stops_worker(self):
    self.mod.signal_handler(15, None)
    self.assertFalse(self.mod.running)

  def test_worker_key_logged(self):
    argv = ['example_worker.py', json.dumps({'duration': 0, 'worker_key': 'my_worker'})]
    with patch.object(sys, 'argv', argv), patch('time.sleep'), patch('logging.info') as mock_log:
      self.mod.main()
    logged = ' '.join(str(c) for c in mock_log.call_args_list)
    self.assertIn('my_worker', logged)

  def test_stopped_by_signal_logs(self):
    def stop_on_sleep(*args):
      self.mod.running = False

    argv = ['example_worker.py', json.dumps({'duration': 9999, 'worker_key': 'sig_w'})]
    with (
      patch.object(sys, 'argv', argv),
      patch('time.sleep', side_effect=stop_on_sleep),
      patch('logging.info') as mock_log,
    ):
      self.mod.main()
    logged = ' '.join(str(c) for c in mock_log.call_args_list)
    self.assertIn('stopped by signal', logged)


class TestExampleWorkerSmoke(BaseTestCase):
  def _log(self, worker_key):
    return os.path.join(self.workers_path, '.service', 'logs', f'{worker_key}.log')

  def test_starts_logs_and_stops(self):
    success, result = self.manager.start_worker(
      'example_worker', worker_key='smoke_example', parameters={'duration': 5, 'worker_key': 'smoke_example'}
    )
    self.assertTrue(success)
    self.wait_for_log(self._log('smoke_example'), 'smoke_example')
    self.manager.stop_worker('smoke_example')
