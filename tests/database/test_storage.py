import os
import shutil
import tempfile
import unittest
from sqlalchemy import create_engine, inspect, text
from unittest.mock import MagicMock, patch

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

  def test_two_storages_share_engine_without_double_begin(self):
    # A WorkerClient and a WorkerManager may wrap the same shared sqlite engine;
    # the 'begin' -> BEGIN IMMEDIATE tuning must be installed only once, or a
    # transaction would try to BEGIN twice ("transaction within a transaction").
    engine = create_engine(f'sqlite:///{os.path.join(self.tmp, "shared_twice.db")}')
    first = Storage(engine=engine, create_tables=True)
    second = Storage(engine=engine, create_tables=False)

    with second.session_scope() as session:
      session.add(Worker(worker_key='k', worker_type='t', status=WorkerStatus.STOPPED))
    with first.session_scope() as session:
      self.assertEqual(session.query(Worker).count(), 1)

    first.dispose()
    second.dispose()
    engine.dispose()

  def test_create_tables_false_issues_no_ddl(self):
    # When the host owns the schema (e.g. via migrations), crazy_workers must
    # not create its tables — it leaves the engine's database untouched.
    engine = create_engine(f'sqlite:///{os.path.join(self.tmp, "host_owned.db")}')
    storage = Storage(engine=engine, create_tables=False)

    self.assertNotIn('workers', inspect(engine).get_table_names())

    storage.dispose()
    engine.dispose()


class TestStorageSessionTimezone(unittest.TestCase):
  """Guards the fix for the crash-backoff timezone poisoning.

  The reconciler stores aware-UTC timestamps in a naive DateTime column and reads
  them back as UTC. A Postgres session whose TimeZone is not UTC (e.g. a container
  running TZ=Europe/Rome) would offset the round-trip and park crashed workers in
  a multi-hour backoff, so every Postgres session must be pinned to UTC.
  """

  def test_postgres_url_pins_session_to_utc(self):
    with patch('crazy_workers.database.storage.create_engine') as mock_create_engine:
      mock_create_engine.return_value = MagicMock()
      Storage(db_url='postgresql://u:p@h:5432/db', create_tables=False)

    options = mock_create_engine.call_args.kwargs['connect_args'].get('options', '')
    self.assertIn('timezone', options.lower())
    self.assertIn('utc', options.lower())

  def test_sqlite_url_keeps_timeout_and_sets_no_timezone(self):
    with patch('crazy_workers.database.storage.create_engine') as mock_create_engine:
      # dialect.name must not equal 'sqlite' or the mock hits the sqlite tuning path.
      mock_create_engine.return_value = MagicMock()
      Storage(db_url='sqlite:///x.db', create_tables=False)

    connect_args = mock_create_engine.call_args.kwargs['connect_args']
    self.assertEqual(connect_args, {'timeout': 30})

  def test_connect_args_for_helper(self):
    self.assertEqual(Storage._connect_args_for('sqlite:///a.db'), {'timeout': 30})
    self.assertEqual(Storage._connect_args_for('postgresql://u@h/d'), {'options': '-c timezone=utc'})
    self.assertEqual(Storage._connect_args_for('mysql://u@h/d'), {})


class TestSchemaTimezoneAware(unittest.TestCase):
  """The datetime columns must be timezone-aware (TIMESTAMPTZ on Postgres).

  A naive column stores wall-clock in the session's TimeZone; read back as UTC it
  is offset by the local UTC offset, which is what poisoned the crash backoff.
  Aware columns store the instant with its offset, so the round-trip is correct
  regardless of session or container TZ.
  """

  def test_datetime_columns_are_timezone_aware(self):
    for name in ('last_exit_at', 'last_started_at', 'last_stopped_at', 'created_at', 'updated_at'):
      self.assertTrue(Worker.__table__.c[name].type.timezone, f'{name} must be timezone-aware')
