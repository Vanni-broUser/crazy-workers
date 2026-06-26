import os
import shutil
import tempfile
import unittest
from datetime import datetime, timedelta, timezone

from crazy_workers import WorkerClient, WorkerManager
from crazy_workers.daemon.reconciler import Reconciler
from crazy_workers.database.schema import Worker, WorkerStatus


class _ReconcilerTestBase(unittest.TestCase):
  def setUp(self):
    self.tmp = tempfile.mkdtemp(prefix='cw_reconciler_')
    self.workers_dir = os.path.join(self.tmp, 'workers')
    os.makedirs(self.workers_dir)
    # start_worker requires the script to exist, even though FakeBackend never runs it.
    with open(os.path.join(self.workers_dir, 'example_worker.py'), 'w') as f:
      f.write('pass\n')

    self.manager = WorkerManager.for_testing(self.workers_dir)
    self.backend = self.manager.test
    self.client = WorkerClient(db_url=f'sqlite:///{self.manager.db_path}', create_tables=False)
    self.reconciler = Reconciler(self.manager, interval=0.01)

  def tearDown(self):
    self.client.dispose()
    self.manager.dispose()
    shutil.rmtree(self.tmp, ignore_errors=True)

  def _set(self, worker_key, **fields):
    with self.manager.storage.session_scope() as session:
      worker = session.query(Worker).filter_by(worker_key=worker_key).first()
      for key, value in fields.items():
        setattr(worker, key, value)

  def _status(self, worker_key):
    return self.client.get(worker_key)['status']


class TestReconcileTable(_ReconcilerTestBase):
  def test_running_and_dead_starts(self):
    self.client.request_start('example_worker', worker_key='w1')
    actions = self.reconciler.reconcile_once()

    self.assertIn(('w1', 'start'), actions)
    self.assertTrue(self.backend.is_running('w1'))
    self.assertEqual(self._status('w1'), 'RUNNING')

  def test_running_and_alive_noop(self):
    self.client.request_start('example_worker', worker_key='w1')
    self.reconciler.reconcile_once()  # starts it
    actions = self.reconciler.reconcile_once()  # already alive

    self.assertEqual(actions, [])
    self.assertEqual(self.backend.start_count('w1'), 1)

  def test_stopped_and_alive_stops(self):
    self.client.request_start('example_worker', worker_key='w1')
    self.reconciler.reconcile_once()
    self.assertTrue(self.backend.is_running('w1'))

    self.client.request_stop('w1')
    actions = self.reconciler.reconcile_once()

    self.assertIn(('w1', 'stop'), actions)
    self.assertFalse(self.backend.is_running('w1'))

  def test_stopped_and_dead_noop(self):
    # Worker exists but was never started and is not desired.
    self.client.request_start('example_worker', worker_key='w1')
    self.client.request_stop('w1')
    actions = self.reconciler.reconcile_once()

    self.assertEqual(actions, [])
    self.assertEqual(self.backend.start_count('w1'), 0)

  def test_mark_running_heals_status_drift(self):
    self.client.request_start('example_worker', worker_key='w1')
    self.reconciler.reconcile_once()  # RUNNING + alive
    self._set('w1', status=WorkerStatus.STARTING)  # observed status drifts

    actions = self.reconciler.reconcile_once()

    self.assertIn(('w1', 'mark_running'), actions)
    self.assertEqual(self._status('w1'), 'RUNNING')

  def test_in_process_end_to_end(self):
    self.client.request_start('example_worker', worker_key='w1')
    self.reconciler.reconcile_once()
    self.assertTrue(self.backend.is_running('w1'))

    self.client.request_stop('w1')
    self.reconciler.reconcile_once()
    self.assertFalse(self.backend.is_running('w1'))


class TestReconcileRecovery(_ReconcilerTestBase):
  def test_crashed_running_worker_is_restarted(self):
    # Recovery is just a special case of reconciliation: desired RUNNING + dead PID.
    self.client.request_start('example_worker', worker_key='w1')
    self.reconciler.reconcile_once()
    self.backend.crash('w1')  # process dies unexpectedly; DB still says RUNNING

    self.reconciler.reconcile_once()

    self.assertTrue(self.backend.is_running('w1'))
    self.assertEqual(self.backend.start_count('w1'), 2)

  def test_alive_worker_is_readopted_not_restarted(self):
    self.client.request_start('example_worker', worker_key='w1')
    self.reconciler.reconcile_once()

    # A second pass sees it alive (by pid/token) and leaves it alone.
    self.reconciler.reconcile_once()
    self.assertEqual(self.backend.start_count('w1'), 1)


class TestReconcileBackoff(_ReconcilerTestBase):
  def test_recent_crash_is_in_backoff(self):
    self.client.request_start('example_worker', worker_key='w1')
    self._set(
      'w1',
      status=WorkerStatus.CRASHED,
      restart_count=5,
      last_exit_at=datetime.now(timezone.utc),
      pid=None,
    )
    self.reconciler.reconcile_once()
    self.assertEqual(self.backend.start_count('w1'), 0)

  def test_naive_last_exit_at_is_treated_as_utc(self):
    self.client.request_start('example_worker', worker_key='w1')
    self._set(
      'w1',
      status=WorkerStatus.CRASHED,
      restart_count=5,
      last_exit_at=datetime.utcnow(),  # naive, as a DB round-trip would return
      pid=None,
    )
    self.reconciler.reconcile_once()
    self.assertEqual(self.backend.start_count('w1'), 0)

  def test_expired_backoff_restarts(self):
    self.client.request_start('example_worker', worker_key='w1')
    self._set(
      'w1',
      status=WorkerStatus.CRASHED,
      restart_count=1,
      last_exit_at=datetime.now(timezone.utc) - timedelta(seconds=120),
      pid=None,
    )
    self.reconciler.reconcile_once()
    self.assertEqual(self.backend.start_count('w1'), 1)


class TestReconcilerLoop(_ReconcilerTestBase):
  def test_run_forever_runs_until_stopped(self):
    calls = []

    def fake_once():
      calls.append(1)
      if len(calls) >= 2:
        self.reconciler.stop()

    self.reconciler.reconcile_once = fake_once
    self.reconciler.run_forever()
    self.assertGreaterEqual(len(calls), 2)

  def test_run_forever_survives_reconcile_error(self):
    calls = []

    def boom():
      calls.append(1)
      if len(calls) == 1:
        raise RuntimeError('transient')
      self.reconciler.stop()

    self.reconciler.reconcile_once = boom
    self.reconciler.run_forever()  # must not propagate
    self.assertEqual(len(calls), 2)
