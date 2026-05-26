from io import StringIO
import logging
import os
import psutil
import shutil
import sys
import time
import unittest
from unittest.mock import MagicMock, patch

# Suppress logging during tests to avoid confusing output
logging.getLogger('crazy_workers').setLevel(logging.CRITICAL)

# Add current dir to path to find crazy_workers and example_app
sys.path.append(os.path.dirname(__file__))

from crazy_workers import WorkerManager, WorkerStatus  # noqa: E402
from crazy_workers.cli import main as cli_main  # noqa: E402
from crazy_workers.models import Worker  # noqa: E402
from example_app.app import create_app  # noqa: E402


class WorkerLibraryTestCase(unittest.TestCase):
  def setUp(self):
    # Create a unique temporary workers directory for each test
    self.test_dir = f'test_env_{self._testMethodName}'
    os.makedirs(self.test_dir, exist_ok=True)
    
    # Copy example worker to the test dir
    src_worker = os.path.join(os.path.dirname(__file__), 'example_app', 'workers', 'example_worker.py')
    self.worker_file = os.path.join(self.test_dir, 'example_worker.py')
    shutil.copy(src_worker, self.worker_file)
    
    self.manager = WorkerManager(self.test_dir)

  def tearDown(self):
    # Stop all workers
    try:
      workers = self.manager.list_workers()
      for w in workers:
        if w['status'] == 'RUNNING':
          self.manager.stop_worker(w['worker_key'])
    except Exception:
      pass

    self.manager.dispose()
    
    # Cleanup the entire test environment
    if os.path.exists(self.test_dir):
      shutil.rmtree(self.test_dir)

  def test_library_start_and_stop(self):
    success, result = self.manager.start_worker(
      'example_worker', worker_key='test_key', parameters={'duration': 10}
    )
    self.assertTrue(success)
    self.assertEqual(result['status'], 'RUNNING')
    self.assertIsNotNone(result['pid'])
    # Verify PID actually exists in OS
    self.assertTrue(psutil.pid_exists(result['pid']))

    # Stop
    success, msg = self.manager.stop_worker('test_key')
    self.assertTrue(success)

    workers = self.manager.list_workers()
    worker = next(w for w in workers if w['worker_key'] == 'test_key')
    self.assertEqual(worker['status'], 'STOPPED')

  def test_library_defaults(self):
    # Test that worker_key and log_dir default to worker_type
    success, result = self.manager.start_worker('example_worker')
    self.assertTrue(success)
    self.assertEqual(result['worker_key'], 'example_worker')
    
    # Verify log file is in .service/logs
    log_path = os.path.join(self.test_dir, '.service', 'logs', 'example_worker.log')
    self.assertTrue(os.path.exists(log_path))

  def test_library_already_running(self):
    self.manager.start_worker('example_worker', worker_key='running_key')
    success, msg = self.manager.start_worker('example_worker', worker_key='running_key')
    self.assertFalse(success)
    self.assertEqual(msg, 'Worker already running')

  def test_library_parameter_change(self):
    # Start with param A
    self.manager.start_worker('example_worker', worker_key='param_test', parameters={'val': 'A'})
    self.manager.stop_worker('param_test')

    # Restart with param B
    success, result = self.manager.start_worker('example_worker', worker_key='param_test', parameters={'val': 'B'})
    self.assertTrue(success)
    self.assertEqual(result['parameters'], {'val': 'B'})

  def test_library_missing_worker_file(self):
    success, msg = self.manager.start_worker('non_existent')
    self.assertFalse(success)
    self.assertIn('not found', msg)

  def test_library_immediate_failure(self):
    # Mock a file that exists but fails to run
    bad_worker = os.path.join(self.test_dir, 'fail.py')
    with open(bad_worker, 'w') as f:
      f.write('import sys; sys.exit(1)')

    success, msg = self.manager.start_worker('fail')
    self.assertFalse(success)
    self.assertEqual(msg, 'Worker process failed to start')

  def test_library_stop_not_found(self):
    success, msg = self.manager.stop_worker('no_such_key')
    self.assertFalse(success)
    self.assertEqual(msg, 'Worker not found or not running')

  def test_library_is_process_running_exception(self):
    with patch('psutil.pid_exists', side_effect=Exception('fail')):
      self.assertFalse(self.manager._is_process_running(123))

  def test_library_stop_timeout(self):
    # Mock psutil.Process to simulate a timeout
    with patch('psutil.Process') as mock_process_class:
      mock_proc = MagicMock()
      mock_proc.wait.side_effect = psutil.TimeoutExpired(3)
      mock_process_class.return_value = mock_proc

      # Manual inject running worker
      session = self.manager.storage.get_session()
      worker = Worker(
        worker_key='timeout_test', worker_type='example_worker', parameters={}, status=WorkerStatus.RUNNING, pid=12345
      )
      session.add(worker)
      session.commit()
      session.close()

      with patch.object(self.manager, '_is_process_running', return_value=True):
        success, msg = self.manager.stop_worker('timeout_test')
        self.assertTrue(success)
        mock_proc.kill.assert_called_once()

  def test_library_stop_exception(self):
    with patch('psutil.Process', side_effect=Exception('Generic error')):
      # Manual inject running worker
      session = self.manager.storage.get_session()
      worker = Worker(
        worker_key='exc_test', worker_type='example_worker', parameters={}, status=WorkerStatus.RUNNING, pid=12345
      )
      session.add(worker)
      session.commit()
      session.close()

      with patch.object(self.manager, '_is_process_running', return_value=True):
        success, msg = self.manager.stop_worker('exc_test')
        self.assertFalse(success)
        self.assertEqual(msg, 'Generic error')

  def test_library_recover(self):
    # Manually inject a "running" worker into the DB
    session = self.manager.storage.get_session()
    worker = Worker(
      worker_key='recover_test',
      worker_type='example_worker',
      parameters={'duration': 10},
      status=WorkerStatus.RUNNING,
      pid=99999,
    )
    session.add(worker)
    session.commit()
    session.close()

    restarted = self.manager.recover_workers()
    self.assertIn('recover_test', restarted)

    workers = self.manager.list_workers()
    worker = next(w for w in workers if w['worker_key'] == 'recover_test')
    self.assertEqual(worker['status'], 'RUNNING')
    self.assertNotEqual(worker['pid'], 99999)

  def test_library_path_traversal(self):
    # Traversal in worker_type
    success, msg = self.manager.start_worker('../etc/passwd', 'some_key')
    self.assertFalse(success)
    self.assertEqual(msg, 'Invalid worker_type')
    
    # Traversal in worker_key
    success, msg = self.manager.start_worker('example_worker', '../etc/passwd')
    self.assertFalse(success)
    self.assertEqual(msg, 'Invalid worker_key')

  def test_library_stale_lock(self):
    lock_path = f'{self.manager.db_path}.recovery.lock'
    os.makedirs(os.path.dirname(lock_path), exist_ok=True)
    with open(lock_path, 'w') as f:
      f.write('999999')  # Non-existent PID

    restarted = self.manager.recover_workers()
    self.assertEqual(restarted, [])
    self.assertFalse(os.path.exists(lock_path))

  def test_library_empty_lock(self):
    lock_path = f'{self.manager.db_path}.recovery.lock'
    os.makedirs(os.path.dirname(lock_path), exist_ok=True)
    with open(lock_path, 'w') as f:
      f.write('')  # Empty lock file

    restarted = self.manager.recover_workers()
    self.assertEqual(restarted, [])
    self.assertFalse(os.path.exists(lock_path))

  def test_library_dispose_exception(self):
    self.manager._active_processes['fail'] = MagicMock()
    self.manager._active_processes['fail'].poll.side_effect = Exception('poll fail')
    self.manager.dispose()
    self.assertEqual(len(self.manager._active_processes), 0)


class ExampleAppTestCase(unittest.TestCase):
  def setUp(self):
    self.test_dir = f'test_app_env_{self._testMethodName}'
    os.makedirs(self.test_dir, exist_ok=True)
    
    # Copy example worker
    src_worker = os.path.join(os.path.dirname(__file__), 'example_app', 'workers', 'example_worker.py')
    os.makedirs(os.path.join(self.test_dir, 'workers'), exist_ok=True)
    shutil.copy(src_worker, os.path.join(self.test_dir, 'workers', 'example_worker.py'))

    with patch('example_app.app.WorkerManager') as mock_manager_class:
      # Redirect the app's manager to our test dir
      self.manager = WorkerManager(os.path.join(self.test_dir, 'workers'))
      mock_manager_class.return_value = self.manager
      self.app, _ = create_app()
      self.app.config['TESTING'] = True
      self.client = self.app.test_client()

  def tearDown(self):
    try:
      workers = self.manager.list_workers()
      for w in workers:
        if w['status'] == 'RUNNING':
          self.manager.stop_worker(w['worker_key'])
    except Exception:
      pass

    self.manager.dispose()
    if os.path.exists(self.test_dir):
      shutil.rmtree(self.test_dir)

  def test_app_api(self):
    # Start
    response = self.client.post(
      '/workers/start',
      json={
        'worker_key': 'app_test',
        'worker_type': 'example_worker',
        'parameters': {'duration': 5},
      },
    )
    self.assertEqual(response.status_code, 200)

    # List
    response = self.client.get('/workers')
    self.assertEqual(response.status_code, 200)
    data = response.get_json()
    self.assertTrue(any(w['worker_key'] == 'app_test' for w in data))

    # Stop
    response = self.client.post('/workers/stop', json={'worker_key': 'app_test'})
    self.assertEqual(response.status_code, 200)

  def test_app_api_missing_data(self):
    response = self.client.post('/workers/start', json={})
    self.assertEqual(response.status_code, 400)

    response = self.client.post('/workers/stop', json={})
    self.assertEqual(response.status_code, 400)

  def test_app_api_errors(self):
    # Start error (missing worker file)
    response = self.client.post('/workers/start', json={'worker_key': 'err', 'worker_type': 'missing'})
    self.assertEqual(response.status_code, 400)

    # Stop error (not found)
    response = self.client.post('/workers/stop', json={'worker_key': 'no_key'})
    self.assertEqual(response.status_code, 400)


class CliTestCase(unittest.TestCase):
  def setUp(self):
    self.test_dir = f'test_cli_env_{self._testMethodName}'
    os.makedirs(self.test_dir, exist_ok=True)
    
    # Copy example worker
    src_worker = os.path.join(os.path.dirname(__file__), 'example_app', 'workers', 'example_worker.py')
    os.makedirs(os.path.join(self.test_dir, 'workers'), exist_ok=True)
    shutil.copy(src_worker, os.path.join(self.test_dir, 'workers', 'example_worker.py'))
    
    self.workers_path = os.path.join(self.test_dir, 'workers')
    self.manager = WorkerManager(self.workers_path)

  def tearDown(self):
    try:
      workers = self.manager.list_workers()
      for w in workers:
        if w['status'] == 'RUNNING':
          self.manager.stop_worker(w['worker_key'])
    except Exception:
      pass

    self.manager.dispose()
    if os.path.exists(self.test_dir):
      shutil.rmtree(self.test_dir)

  def test_cli_list(self):
    # Start a worker first
    self.manager.start_worker('example_worker', worker_key='cli_test')

    argv = ['crazy-workers', '--workers-dir', self.workers_path, 'list']
    with patch('sys.argv', argv):
      with patch('sys.stdout', new=StringIO()) as fake_out:
        cli_main()
        output = fake_out.getvalue()
        self.assertIn('cli_test', output)
        self.assertIn('RUNNING', output)

  def test_cli_stop(self):
    self.manager.start_worker('example_worker', worker_key='stop_test')

    argv = ['crazy-workers', '--workers-dir', self.workers_path, 'stop', 'stop_test']
    with patch('sys.argv', argv):
      with patch('sys.stdout', new=StringIO()) as fake_out:
        cli_main()
        output = fake_out.getvalue()
        self.assertIn('Success', output)

    workers = self.manager.list_workers()
    worker = next(w for w in workers if w['worker_key'] == 'stop_test')
    self.assertEqual(worker['status'], 'STOPPED')

  def test_cli_stop_error(self):
    argv = ['crazy-workers', '--workers-dir', self.workers_path, 'stop', 'non_existent']
    with patch('sys.argv', argv):
      with patch('sys.stderr', new=StringIO()) as fake_err:
        with self.assertRaises(SystemExit) as cm:
          cli_main()
        self.assertEqual(cm.exception.code, 1)
        self.assertIn('Error', fake_err.getvalue())


if __name__ == '__main__':
  unittest.main()
