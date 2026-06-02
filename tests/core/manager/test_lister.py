import os

from tests.base import BaseTestCase


class TestManagerLister(BaseTestCase):
  def test_library_timestamps(self):
    success, result = self.manager.start_worker('example_worker', worker_key='time_test')
    self.assertTrue(success)
    self.assertIsNotNone(result['last_started_at'])
    self.assertIsNone(result['last_stopped_at'])

    self.manager.stop_worker('time_test')
    workers = self.manager.list_workers()
    worker = next(w for w in workers if w['worker_key'] == 'time_test')
    self.assertIsNotNone(worker['last_started_at'])
    self.assertIsNotNone(worker['last_stopped_at'])

  def test_list_workers_updates_dead_process_status(self):
    helper_script = os.path.join(self.workers_path, 'short_lived.py')
    with open(helper_script, 'w') as f:
      f.write('import time\ntime.sleep(0.1)\n')

    success, _ = self.manager.start_worker('short_lived', worker_key='sync_test')
    self.assertTrue(success)

    self.wait_for_worker_status(self.manager, 'sync_test', 'STOPPED')
    workers = self.manager.list_workers()
    worker = next(w for w in workers if w['worker_key'] == 'sync_test')
    self.assertEqual(worker['status'], 'STOPPED')
    self.assertIsNone(worker['pid'])

  def test_list_workers_filesystem_discovery(self):
    new_worker = os.path.join(self.workers_path, 'brand_new.py')
    with open(new_worker, 'w') as f:
      f.write('pass')

    workers = self.manager.list_workers()
    worker = next(w for w in workers if w['worker_type'] == 'brand_new')
    self.assertIsNone(worker['worker_key'])
    self.assertEqual(worker['status'], 'NEVER_STARTED')

  def test_list_workers_no_storage(self):
    orig_storage = self.manager.storage
    self.manager.storage = None
    try:
      workers = self.manager.list_workers()
      worker = next(w for w in workers if w['worker_type'] == 'example_worker')
      self.assertIsNone(worker['worker_key'])
      self.assertEqual(worker['status'], 'NEVER_STARTED')
    finally:
      self.manager.storage = orig_storage
