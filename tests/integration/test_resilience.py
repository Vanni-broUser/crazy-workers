"""
Integration tests that exercise the full stack with real processes.
These tests are slower by design — they kill, recover, and inspect live workers.
"""

import os
import psutil
import shutil

from crazy_workers import WorkerManager
from tests.base import BaseTestCase


_WORKERS_SRC = os.path.join(
  os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
  'example_app',
  'workers',
)


class TestResilience(BaseTestCase):
  def setUp(self):
    super().setUp()
    for f in os.listdir(_WORKERS_SRC):
      if f.endswith('.py'):
        shutil.copy(os.path.join(_WORKERS_SRC, f), self.workers_path)

  def test_manual_kill_and_recovery(self):
    success, result = self.manager.start_worker('infinite_worker', worker_key='resilience_test')
    self.assertTrue(success)
    pid = result['pid']
    self.assertTrue(psutil.pid_exists(pid))

    proc = psutil.Process(pid)
    proc.kill()
    proc.wait()
    self.assertFalse(psutil.pid_exists(pid))

    self.manager.dispose()
    fresh = WorkerManager(self.workers_path)
    restarted = fresh.recover_workers()
    self.assertIn('resilience_test', restarted)

    workers = fresh.list_workers()
    worker = next(w for w in workers if w['worker_key'] == 'resilience_test')
    self.assertEqual(worker['status'], 'RUNNING')
    self.assertNotEqual(worker['pid'], pid)
    self.assertTrue(psutil.pid_exists(worker['pid']))
    fresh.dispose()

  def test_log_file_capture(self):
    worker_key = 'log_test'
    self.manager.start_worker(
      'batch_worker', worker_key=worker_key, parameters={'items': ['test_item_123'], 'delay': 0.1}
    )
    log_path = os.path.join(self.workers_path, '.service', 'logs', f'{worker_key}.log')
    self.wait_for_log(log_path, 'Processing: test_item_123')

  def test_path_traversal_attempts(self):
    forbidden = [
      '../outside',
      '../../etc/passwd',
      'C:\\Windows\\System32\\cmd.exe',
      'sub/../../../secret',
      '..\\..\\test',
      'c:evil',  # Windows drive-relative: os.path.join would silently escape the dir
      'evil.py',  # dots are not part of the safe identifier charset
    ]
    for key in forbidden:
      success, message = self.manager.start_worker('example_worker', worker_key=key)
      self.assertFalse(success, f'Should have rejected key: {key}')
      self.assertIn('Invalid', message)

  def test_process_robust_verification(self):
    success, result = self.manager.start_worker(
      'example_worker', worker_key='robust_test', parameters={'duration': 5, 'worker_key': 'robust_test'}
    )
    self.assertTrue(success)
    log_path = os.path.join(self.workers_path, '.service', 'logs', 'robust_test.log')
    self.wait_for_log(log_path, 'Worker robust_test starting')
    self.wait_for_log(log_path, 'Will run for 5 seconds')

    proc = psutil.Process(result['pid'])
    self.assertTrue(proc.is_running())
    self.assertNotEqual(proc.status(), psutil.STATUS_ZOMBIE)
    self.manager.stop_worker('robust_test')
