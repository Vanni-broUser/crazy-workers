import os
import shutil
import tempfile
import unittest
from sqlalchemy import create_engine, inspect, text

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


class TestStorageBackends(unittest.TestCase):
  def setUp(self):
    self.tmp = tempfile.mkdtemp()
    self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)

  def test_storage_from_db_url(self):
    url = f'sqlite:///{os.path.join(self.tmp, "url.db")}'
    storage = Storage(db_url=url)
    with storage.session_scope() as session:
      session.add(Worker(worker_key='k', worker_type='t', status=WorkerStatus.STOPPED))
    with storage.session_scope() as session:
      self.assertEqual(session.query(Worker).count(), 1)
    storage.dispose()

  def test_storage_reuses_shared_engine_and_does_not_dispose_it(self):
    engine = create_engine(f'sqlite:///{os.path.join(self.tmp, "shared.db")}')
    storage = Storage(engine=engine)

    # crazy_workers tables are created inside the shared engine's database.
    with storage.session_scope() as session:
      session.add(Worker(worker_key='k', worker_type='t', status=WorkerStatus.STOPPED))

    storage.dispose()  # must NOT dispose an engine it does not own
    with engine.connect() as conn:
      count = conn.execute(text('SELECT COUNT(*) FROM workers')).scalar()
    self.assertEqual(count, 1)
    engine.dispose()

  def test_create_tables_false_issues_no_ddl(self):
    # When the host owns the schema (e.g. via migrations), crazy_workers must
    # not create its tables — it leaves the engine's database untouched.
    engine = create_engine(f'sqlite:///{os.path.join(self.tmp, "host_owned.db")}')
    storage = Storage(engine=engine, create_tables=False)

    self.assertNotIn('workers', inspect(engine).get_table_names())

    storage.dispose()
    engine.dispose()
