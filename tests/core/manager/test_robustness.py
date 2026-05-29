import os
import psutil
import time

from tests.base import BaseTestCase


class TestManagerRobustness(BaseTestCase):
  def test_library_process_robust_verification(self):
    params = {'duration': 5, 'worker_key': 'robust_test'}
    success, result = self.manager.start_worker('example_worker', worker_key='robust_test', parameters=params)
    self.assertTrue(success)

    time.sleep(1)
    log_path = os.path.join(self.workers_path, '.service', 'logs', 'robust_test.log')
    self.assertTrue(os.path.exists(log_path))

    with open(log_path, 'r') as f:
      logs = f.read()

    self.assertIn('Worker robust_test starting', logs)
    self.assertIn('Will run for 5 seconds', logs)

    proc = psutil.Process(result['pid'])
    self.assertTrue(proc.is_running())
    self.assertNotEqual(proc.status(), psutil.STATUS_ZOMBIE)

    self.manager.stop_worker('robust_test')

  def test_library_is_process_running_exception(self):
    from unittest.mock import patch

    with patch('crazy_workers.core.engine.psutil.Process', side_effect=Exception('fail')):
      self.assertFalse(self.manager._is_process_running(123))
