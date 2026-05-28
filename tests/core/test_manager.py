import os
import time
from unittest.mock import MagicMock, patch
import psutil

from crazy_workers import WorkerStatus
from crazy_workers.database.schema import Worker
from tests.base import BaseTestCase


class TestWorkerManager(BaseTestCase):
  def test_library_start_and_stop(self):
    # ... rest of method unchanged
    success, result = self.manager.start_worker('example_worker', worker_key='test_key', parameters={'duration': 10})
    self.assertTrue(success)
    self.assertEqual(result['status'], 'RUNNING')
    self.assertIsNotNone(result['pid'])

    # Robust check: PID exists and matches our script
    pid = result['pid']
    self.assertTrue(psutil.pid_exists(pid))
    proc = psutil.Process(pid)
    self.assertTrue(proc.is_running())
    cmdline = ' '.join(proc.cmdline())
    self.assertIn('example_worker.py', cmdline)

    # Stop
    success, msg = self.manager.stop_worker('test_key')
    self.assertTrue(success)

    # Wait for process to actually terminate
    try:
      proc.wait(timeout=5)
    except psutil.TimeoutExpired:
      pass
    self.assertFalse(proc.is_running())

    workers = self.manager.list_workers()
    worker = next(w for w in workers if w['worker_key'] == 'test_key')
    self.assertEqual(worker['status'], 'STOPPED')

  def test_library_process_robust_verification(self):
    """Verifies that the process is not just 'active' by PID but actually working."""
    params = {'duration': 5, 'worker_key': 'robust_test'}
    success, result = self.manager.start_worker('example_worker', worker_key='robust_test', parameters=params)
    self.assertTrue(success)

    # Give it a moment to write to logs
    time.sleep(1)

    log_path = os.path.join(self.workers_path, '.service', 'logs', 'robust_test.log')
    self.assertTrue(os.path.exists(log_path))

    with open(log_path, 'r') as f:
      logs = f.read()

    self.assertIn('Worker robust_test starting', logs)
    self.assertIn('Will run for 5 seconds', logs)

    # Check process state via psutil
    proc = psutil.Process(result['pid'])
    self.assertTrue(proc.is_running())
    self.assertNotEqual(proc.status(), psutil.STATUS_ZOMBIE)

    self.manager.stop_worker('robust_test')

  def test_library_defaults(self):
    success, result = self.manager.start_worker('example_worker')
    self.assertTrue(success)
    self.assertEqual(result['worker_key'], 'example_worker')

    log_path = os.path.join(self.workers_path, '.service', 'logs', 'example_worker.log')
    self.assertTrue(os.path.exists(log_path))

  def test_library_already_running(self):
    self.manager.start_worker('example_worker', worker_key='running_key')
    success, msg = self.manager.start_worker('example_worker', worker_key='running_key')
    self.assertFalse(success)
    self.assertEqual(msg, 'Worker already running')

  def test_library_parameter_change(self):
    self.manager.start_worker('example_worker', worker_key='param_test', parameters={'val': 'A'})
    self.manager.stop_worker('param_test')

    success, result = self.manager.start_worker('example_worker', worker_key='param_test', parameters={'val': 'B'})
    self.assertTrue(success)
    self.assertEqual(result['parameters'], {'val': 'B'})

  def test_library_missing_worker_file(self):
    success, msg = self.manager.start_worker('non_existent')
    self.assertFalse(success)
    self.assertIn('not found', msg)

  def test_library_immediate_failure(self):
    bad_worker = os.path.join(self.workers_path, 'fail.py')
    with open(bad_worker, 'w') as f:
      f.write('import sys; sys.exit(1)')

    success, msg = self.manager.start_worker('fail')
    self.assertFalse(success)
    self.assertEqual(msg, 'Worker process failed to start')

  def test_library_stop_not_found(self):
    success, msg = self.manager.stop_worker('no_such_key')
    self.assertFalse(success)
    self.assertEqual(msg, 'Worker not found')

  def test_library_stop_not_running(self):
    self.manager.start_worker('example_worker', worker_key='not_running_key')
    self.manager.stop_worker('not_running_key')
    success, msg = self.manager.stop_worker('not_running_key')
    self.assertFalse(success)
    self.assertEqual(msg, 'Worker is not running')

  def test_library_is_process_running_exception(self):
    with patch('crazy_workers.core.engine.psutil.Process', side_effect=Exception('fail')):
      self.assertFalse(self.manager._is_process_running(123))

  def test_library_stop_timeout(self):
    with patch('crazy_workers.core.engine.psutil.Process') as mock_process_class:
      mock_proc = MagicMock()
      mock_proc.wait.side_effect = psutil.TimeoutExpired(3)
      mock_process_class.return_value = mock_proc

      session = self.manager.storage.get_session()
      worker = Worker(
        worker_key='timeout_test', worker_type='example_worker', parameters={}, status=WorkerStatus.RUNNING, pid=12345
      )
      session.add(worker)
      session.commit()
      session.close()

      with patch('crazy_workers.core.engine.is_process_running', return_value=True):
        success, msg = self.manager.stop_worker('timeout_test')
        self.assertTrue(success)
        mock_proc.kill.assert_called_once()

  def test_library_stop_exception(self):
    with patch('crazy_workers.core.engine.psutil.Process', side_effect=Exception('Generic error')):
      session = self.manager.storage.get_session()
      worker = Worker(
        worker_key='exc_test', worker_type='example_worker', parameters={}, status=WorkerStatus.RUNNING, pid=12345
      )
      session.add(worker)
      session.commit()
      session.close()

      with patch('crazy_workers.core.engine.is_process_running', return_value=True):
        success, msg = self.manager.stop_worker('exc_test')
        self.assertFalse(success)
        self.assertEqual(msg, 'Generic error')

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

  def test_library_recover(self):
    # Ensure no existing worker with same key
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

    workers = self.manager.list_workers()
    worker = next(w for w in workers if w['worker_key'] == 'recover_test')
    self.assertEqual(worker['status'], 'RUNNING')
    self.assertNotEqual(worker['pid'], 99999)

  def test_library_path_traversal(self):
    success, msg = self.manager.start_worker('../etc/passwd', 'some_key')
    self.assertFalse(success)
    self.assertEqual(msg, 'Invalid worker_type or worker_key')

    success, msg = self.manager.start_worker('example_worker', '../etc/passwd')
    self.assertFalse(success)
    self.assertEqual(msg, 'Invalid worker_type or worker_key')

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

  def test_library_dispose_exception(self):
    self.manager._active_processes['fail'] = MagicMock()
    self.manager._active_processes['fail'].poll.side_effect = Exception('poll fail')
    self.manager.dispose()
    self.assertEqual(len(self.manager._active_processes), 0)

  def test_manager_no_create_dir(self):
    test_dir = 'temp_no_create'
    if os.path.exists(test_dir):
      import shutil

      shutil.rmtree(test_dir)

    from crazy_workers import WorkerManager

    with self.assertRaises(ValueError):
      WorkerManager(test_dir, create_dir=False)

  def test_manager_no_create_service_dir(self):
    test_dir = 'temp_workers_exists'
    os.makedirs(test_dir, exist_ok=True)
    try:
      from crazy_workers import WorkerManager

      manager = WorkerManager(test_dir, create_dir=False)
      self.assertFalse(os.path.exists(os.path.join(test_dir, '.service')))

      # Test protected methods
      self.assertEqual(manager.list_workers(), [])
      success, msg = manager.start_worker('test')
      self.assertFalse(success)
      self.assertIn('database missing', msg)

      manager.dispose()
    finally:
      import shutil

      shutil.rmtree(test_dir)

  def test_list_workers_updates_dead_process_status(self):
    # 1. Start a very short-lived worker
    helper_script = os.path.join(self.workers_path, 'short_lived.py')
    with open(helper_script, 'w') as f:
      f.write('import time\ntime.sleep(0.1)\n')

    success, _ = self.manager.start_worker('short_lived', worker_key='sync_test')
    self.assertTrue(success)

    # 2. Wait for it to definitely exit
    time.sleep(1.0)

    # 3. Call list_workers
    workers = self.manager.list_workers()

    # 4. Verify status is updated
    worker = next(w for w in workers if w['worker_key'] == 'sync_test')
    self.assertEqual(worker['status'], 'STOPPED')
    self.assertIsNone(worker['pid'])

  def test_list_workers_filesystem_discovery(self):
    # Create a new .py file that is NOT in DB
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
      # Should still find example_worker.py from filesystem
      worker = next(w for w in workers if w['worker_type'] == 'example_worker')
      self.assertIsNone(worker['worker_key'])
      self.assertEqual(worker['status'], 'NEVER_STARTED')
    finally:
      self.manager.storage = orig_storage

  def test_start_multiple_same_type_different_keys(self):
    success1, res1 = self.manager.start_worker('example_worker', worker_key='key1')
    success2, res2 = self.manager.start_worker('example_worker', worker_key='key2')

    self.assertTrue(success1)
    self.assertTrue(success2)
    self.assertEqual(res1['worker_type'], 'example_worker')
    self.assertEqual(res2['worker_type'], 'example_worker')
    self.assertEqual(res1['worker_key'], 'key1')
    self.assertEqual(res2['worker_key'], 'key2')
    self.assertNotEqual(res1['pid'], res2['pid'])

    self.manager.stop_worker('key1')
    self.manager.stop_worker('key2')

  def test_start_worker_no_storage(self):
    orig_storage = self.manager.storage
    self.manager.storage = None
    try:
      success, msg = self.manager.start_worker('example_worker')
      self.assertFalse(success)
      self.assertEqual(msg, 'System not initialized (database missing)')
    finally:
      self.manager.storage = orig_storage

  def test_recover_workers_no_storage(self):
    orig_storage = self.manager.storage
    self.manager.storage = None
    try:
      res = self.manager.recover_workers()
      self.assertEqual(res, [])
    finally:
      self.manager.storage = orig_storage

  def test_spawn_worker_process_log_error(self):
    # Mock logs_dir to a non-writable path to trigger the exception in log file opening
    with patch.object(self.manager, 'logs_dir', '/non/existent/path/for/logs'):
      success, result = self.manager.start_worker('example_worker', worker_key='log_err_test')
      self.assertTrue(success)
      # Should still start but with DEVNULL logs
      self.assertEqual(result['status'], 'RUNNING')
