import os

from crazy_workers import WorkerStatus
from crazy_workers.database.schema import Worker
from tests.base import BaseTestCase


class TestManagerRecoverer(BaseTestCase):
  def test_library_recover(self):
    with self.manager.storage.session_scope() as session:
      session.query(Worker).filter_by(worker_key='recover_test').delete()
      worker = Worker(
        worker_key='recover_test',
        worker_type='example_worker',
        parameters={'duration': 10},
        status=WorkerStatus.RUNNING,
        pid=99999,
      )
      session.add(worker)
      session.commit()

    restarted = self.manager.recover_workers()
    self.assertIn('recover_test', restarted)

    self.wait_for_worker_status(self.manager, 'recover_test', 'RUNNING')
    workers = self.manager.list_workers()
    worker = next(w for w in workers if w['worker_key'] == 'recover_test')
    self.assertEqual(worker['status'], 'RUNNING')
    self.assertNotEqual(worker['pid'], 99999)

  def test_library_stale_lock(self):
    lock_path = f'{self.manager.db_path}.recovery.lock'
    os.makedirs(os.path.dirname(lock_path), exist_ok=True)
    with open(lock_path, 'w') as f:
      f.write('999999')

    restarted = self.manager.recover_workers()
    self.assertEqual(restarted, [])
    self.assertFalse(os.path.exists(lock_path))

  def test_library_empty_lock(self):
    lock_path = f'{self.manager.db_path}.recovery.lock'
    os.makedirs(os.path.dirname(lock_path), exist_ok=True)
    with open(lock_path, 'w') as f:
      f.write('')

    restarted = self.manager.recover_workers()
    self.assertEqual(restarted, [])
    self.assertFalse(os.path.exists(lock_path))

  def test_recover_workers_no_storage(self):
    orig_storage = self.manager.storage
    self.manager.storage = None
    try:
      res = self.manager.recover_workers()
      self.assertEqual(res, [])
    finally:
      self.manager.storage = orig_storage
