import os
import tempfile

from crazy_workers.database.schema import Worker, WorkerStatus
from crazy_workers.database.storage import Storage
from tests.base import BaseTestCase


class TestStorage(BaseTestCase):
  def setUp(self):
    super().setUp()
    self.temp_db = tempfile.NamedTemporaryFile(delete=False)
    self.temp_db.close()
    self.storage = Storage(self.temp_db.name)

  def tearDown(self):
    self.storage.dispose()
    if os.path.exists(self.temp_db.name):
      os.remove(self.temp_db.name)
    super().tearDown()

  def test_storage_initialization(self):
    self.assertTrue(os.path.exists(self.temp_db.name))
    # Check if tables were created by trying to query
    with self.storage.session_scope() as session:
      workers = session.query(Worker).all()
      self.assertEqual(len(workers), 0)

  def test_session_scope_commit(self):
    with self.storage.session_scope() as session:
      worker = Worker(worker_key='test', worker_type='type', status=WorkerStatus.STOPPED)
      session.add(worker)

    # Verify commit
    with self.storage.session_scope() as session:
      count = session.query(Worker).count()
      self.assertEqual(count, 1)

  def test_session_scope_rollback(self):
    try:
      with self.storage.session_scope() as session:
        worker = Worker(worker_key='test', worker_type='type', status=WorkerStatus.STOPPED)
        session.add(worker)
        raise ValueError('Simulated error')
    except ValueError:
      pass

    # Verify rollback
    with self.storage.session_scope() as session:
      count = session.query(Worker).count()
      self.assertEqual(count, 0)
