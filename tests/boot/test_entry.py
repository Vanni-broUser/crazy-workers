import os
import unittest

from crazy_workers.boot import entry
from tests.base import BaseTestCase


class TestBootEntryArgs(unittest.TestCase):
  def test_requires_workers_dir(self):
    with self.assertRaises(SystemExit):
      entry.main([])


class TestBootEntryRecovers(BaseTestCase):
  def test_main_restores_dead_running_worker(self):
    from crazy_workers import WorkerStatus
    from crazy_workers.database.schema import Worker

    os.makedirs(self.manager.service_dir, exist_ok=True)
    with self.manager.storage.session_scope() as session:
      session.query(Worker).delete()
      session.add(
        Worker(worker_key='rec', worker_type='example_worker', parameters={}, status=WorkerStatus.RUNNING, pid=99999)
      )

    count = entry.main(['--workers-dir', self.workers_path])
    self.assertEqual(count, 1)

    self.wait_for_worker_status(self.manager, 'rec', 'RUNNING')
    self.manager.stop_worker('rec')
