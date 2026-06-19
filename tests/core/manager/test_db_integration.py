import os
import shutil
import tempfile
import unittest
from sqlalchemy import create_engine, inspect, text

from crazy_workers import WorkerManager
from crazy_workers.database.schema import Worker, WorkerStatus
from crazy_workers.testing import FakeBackend


_EXAMPLE_WORKER = os.path.join(
  os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))),
  'example_app',
  'workers',
  'example_worker.py',
)


class DbIntegrationBase(unittest.TestCase):
  def setUp(self):
    self.tmp = tempfile.mkdtemp()
    self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)
    self.wdir = os.path.join(self.tmp, 'workers')
    os.makedirs(self.wdir)
    shutil.copy(_EXAMPLE_WORKER, os.path.join(self.wdir, 'example_worker.py'))

  def _seed_dead_running_worker(self, key):
    seeder = WorkerManager(self.wdir, backend=FakeBackend(), auto_boot=False, auto_recover=False)
    with seeder.storage.session_scope() as session:
      session.add(
        Worker(worker_key=key, worker_type='example_worker', parameters={}, status=WorkerStatus.RUNNING, pid=99999)
      )
    seeder.dispose()


class TestWorkerEnvInjection(DbIntegrationBase):
  def test_worker_env_injected_into_spawn(self):
    fake = FakeBackend()
    mgr = WorkerManager(
      self.wdir, backend=fake, auto_boot=False, auto_recover=False, worker_env={'DATABASE_URL': 'sqlite:///x.db'}
    )
    mgr.start_worker('example_worker', worker_key='wenv')
    self.assertEqual(fake.spawns[-1]['env']['DATABASE_URL'], 'sqlite:///x.db')
    mgr.dispose()

  def test_per_call_env_overrides_worker_env(self):
    fake = FakeBackend()
    mgr = WorkerManager(self.wdir, backend=fake, auto_boot=False, auto_recover=False, worker_env={'A': '1', 'B': '1'})
    mgr.start_worker('example_worker', worker_key='wenv', env={'B': '2'})
    env = fake.spawns[-1]['env']
    self.assertEqual(env['A'], '1')
    self.assertEqual(env['B'], '2')
    mgr.dispose()


class TestAutoRecoverOnInit(DbIntegrationBase):
  def test_recovers_dead_running_worker_on_construction(self):
    self._seed_dead_running_worker('rec')
    fake = FakeBackend()
    mgr = WorkerManager(self.wdir, backend=fake, auto_boot=False, auto_recover=True)
    self.assertIn('rec', fake.started_keys)
    mgr.dispose()

  def test_auto_recover_false_does_not_recover(self):
    self._seed_dead_running_worker('rec2')
    fake = FakeBackend()
    mgr = WorkerManager(self.wdir, backend=fake, auto_boot=False, auto_recover=False)
    self.assertNotIn('rec2', fake.started_keys)
    mgr.dispose()


class TestSharedEnginePassthrough(DbIntegrationBase):
  def test_tables_created_in_shared_engine_and_not_disposed(self):
    engine = create_engine(f'sqlite:///{os.path.join(self.tmp, "host.db")}')
    mgr = WorkerManager(self.wdir, engine=engine, backend=FakeBackend(), auto_boot=False, auto_recover=False)
    self.assertIn('workers', inspect(engine).get_table_names())

    mgr.dispose()  # a shared engine must survive the manager
    with engine.connect() as conn:
      self.assertEqual(conn.execute(text('SELECT 1')).scalar(), 1)
    engine.dispose()
