"""
Integration tests for cross-module interactions within WorkerManager:
Storage, engine, starter, stopper, and recoverer working together.
"""

import os

from crazy_workers import WorkerManager, WorkerStatus
from crazy_workers.database.schema import Worker
from tests.base import BaseTestCase


class TestContextManager(BaseTestCase):
  def test_context_manager_calls_dispose_on_exit(self):
    from unittest.mock import patch

    with patch.object(self.manager, 'dispose', wraps=self.manager.dispose) as spy:
      with self.manager:
        success, _ = self.manager.start_worker('example_worker', worker_key='ctx_test')
        self.assertTrue(success)
        self.manager.stop_worker('ctx_test')
      spy.assert_called_once()

  def test_context_manager_calls_dispose_on_exception(self):
    from unittest.mock import patch

    with patch.object(self.manager, 'dispose', wraps=self.manager.dispose) as spy:
      try:
        with self.manager:
          raise RuntimeError('intentional')
      except RuntimeError:
        pass
      spy.assert_called_once()

  def test_context_manager_clears_active_processes_on_exit(self):
    self.manager.start_worker('example_worker', worker_key='ctx_ap', parameters={'duration': 30})
    self.assertIn('ctx_ap', self.manager._active_processes)

    with self.manager:
      pass  # __exit__ calls dispose()

    self.assertEqual(len(self.manager._active_processes), 0)


class TestDeadPidHandling(BaseTestCase):
  def test_dead_pid_marked_crashed_on_restart(self):
    """A RUNNING record with a dead PID should be marked CRASHED and restarted."""
    with self.manager.storage.session_scope() as session:
      session.query(Worker).delete()
      session.add(
        Worker(
          worker_key='ghost',
          worker_type='example_worker',
          parameters={'duration': 10},
          status=WorkerStatus.RUNNING,
          pid=999999,  # dead PID
        )
      )

    success, result = self.manager.start_worker('example_worker', worker_key='ghost', parameters={'duration': 10})
    self.assertTrue(success, f'Expected restart, got: {result}')
    self.assertEqual(result['status'], 'RUNNING')
    self.assertNotEqual(result['pid'], 999999)

    workers = self.manager.list_workers()
    worker = next(w for w in workers if w['worker_key'] == 'ghost')
    self.assertEqual(worker['status'], 'RUNNING')

  def test_dead_pid_does_not_block_new_start(self):
    """A second start_worker call for a dead worker should succeed, not return 'already running'."""
    success, _ = self.manager.start_worker('example_worker', worker_key='dead_test', parameters={'duration': 5})
    self.assertTrue(success)

    pid = self.manager.list_workers()[0]['pid']
    import psutil

    psutil.Process(pid).kill()
    self.wait_for_pid_dead(pid)

    success2, result2 = self.manager.start_worker('example_worker', worker_key='dead_test', parameters={'duration': 5})
    self.assertTrue(success2, f'Second start should succeed: {result2}')
    self.assertNotEqual(result2['pid'], pid)


class TestDbPersistenceAcrossInstances(BaseTestCase):
  def test_worker_visible_to_new_manager_instance(self):
    """Workers started by manager A must be visible and stoppable by manager B."""
    success, result = self.manager.start_worker(
      'example_worker', worker_key='persist_test', parameters={'duration': 30}
    )
    self.assertTrue(success)
    pid = result['pid']

    # Create a second manager pointing at the same directory
    manager_b = WorkerManager(self.workers_path, create_dir=False)
    try:
      workers = manager_b.list_workers()
      worker = next((w for w in workers if w['worker_key'] == 'persist_test'), None)
      self.assertIsNotNone(worker, 'Worker not visible from second manager instance')
      self.assertEqual(worker['status'], 'RUNNING')
      self.assertEqual(worker['pid'], pid)

      success, _ = manager_b.stop_worker('persist_test')
      self.assertTrue(success)
    finally:
      manager_b.dispose()

  def test_stopped_state_persists_after_dispose_and_reopen(self):
    """STOPPED status written by manager A must be readable after reopening the DB."""
    self.manager.start_worker('example_worker', worker_key='state_persist', parameters={'duration': 30})
    self.manager.stop_worker('state_persist')

    manager_b = WorkerManager(self.workers_path, create_dir=False)
    try:
      workers = manager_b.list_workers()
      worker = next(w for w in workers if w['worker_key'] == 'state_persist')
      self.assertEqual(worker['status'], 'STOPPED')
      self.assertIsNone(worker['pid'])
    finally:
      manager_b.dispose()


class TestLogAccumulationAcrossRestarts(BaseTestCase):
  def test_logs_accumulate_across_stop_and_restart(self):
    """Log file must preserve entries from previous runs (append mode)."""
    log_path = os.path.join(self.workers_path, '.service', 'logs', 'log_accum.log')

    self.manager.start_worker(
      'example_worker', worker_key='log_accum', parameters={'duration': 5, 'worker_key': 'log_accum'}
    )
    self.wait_for_log(log_path, 'log_accum')
    self.manager.stop_worker('log_accum')

    size_after_first_run = os.path.getsize(log_path)
    self.assertGreater(size_after_first_run, 0)

    self.manager.start_worker(
      'example_worker', worker_key='log_accum', parameters={'duration': 5, 'worker_key': 'log_accum'}
    )
    # Wait for second run to append new content beyond what the first run left
    self.wait_for(
      lambda: os.path.getsize(log_path) > size_after_first_run,
      msg='Log file did not grow after second run',
    )
    self.manager.stop_worker('log_accum')


class TestActiveProcessesConsistency(BaseTestCase):
  def test_active_processes_cleared_on_stop(self):
    self.manager.start_worker('example_worker', worker_key='ap_test', parameters={'duration': 30})
    self.assertIn('ap_test', self.manager._active_processes)

    self.manager.stop_worker('ap_test')
    self.assertNotIn('ap_test', self.manager._active_processes)

  def test_active_processes_handles_multiple_start_stop_cycles(self):
    for i in range(3):
      key = f'cycle_{i}'
      self.manager.start_worker('example_worker', worker_key=key, parameters={'duration': 30})
      self.assertIn(key, self.manager._active_processes)

    self.assertEqual(len(self.manager._active_processes), 3)

    for i in range(3):
      self.manager.stop_worker(f'cycle_{i}')

    self.assertEqual(len(self.manager._active_processes), 0)

  def test_active_processes_not_populated_for_recovered_workers(self):
    """Workers recovered via recover_workers() are spawned fresh — _active_processes should track them."""
    with self.manager.storage.session_scope() as session:
      session.query(Worker).delete()
      session.add(
        Worker(
          worker_key='recovered_ap',
          worker_type='example_worker',
          parameters={'duration': 30},
          status=WorkerStatus.RUNNING,
          pid=999999,
        )
      )

    self.manager.recover_workers()
    # After recovery the worker is restarted via start_worker, so it enters _active_processes
    self.assertIn('recovered_ap', self.manager._active_processes)
