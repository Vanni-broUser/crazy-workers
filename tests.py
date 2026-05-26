import unittest
import os
import sys
from unittest.mock import patch, MagicMock
import psutil

# Add current dir to path to find crazy_workers and example_app
sys.path.append(os.path.dirname(__file__))

from crazy_workers import WorkerManager, WorkerStatus
from example_app.app import create_app


class WorkerLibraryTestCase(unittest.TestCase):
  def setUp(self):
    self.db_path = f'test_workers_{self._testMethodName}.db'
    self.workers_dir = os.path.join(os.path.dirname(__file__), 'example_app', 'workers')
    self.manager = WorkerManager(self.db_path, self.workers_dir)

  def tearDown(self):
    # Stop all workers
    workers = self.manager.list_workers()
    for w in workers:
      if w['status'] == 'RUNNING':
        self.manager.stop_worker(w['worker_key'])

    self.manager.dispose()
    if os.path.exists(self.db_path):
      try:
        os.remove(self.db_path)
      except PermissionError:
        import time

        time.sleep(0.1)
        try:
          os.remove(self.db_path)
        except PermissionError:
          pass

  def test_library_start_and_stop(self):
    success, result = self.manager.start_worker(
      'test_key', 'example_worker', {'duration': 10, 'worker_key': 'test_key'}
    )
    self.assertTrue(success)
    self.assertEqual(result['status'], 'RUNNING')
    self.assertIsNotNone(result['pid'])

    # Stop
    success, msg = self.manager.stop_worker('test_key')
    self.assertTrue(success)

    workers = self.manager.list_workers()
    worker = next(w for w in workers if w['worker_key'] == 'test_key')
    self.assertEqual(worker['status'], 'STOPPED')

  def test_library_already_running(self):
    self.manager.start_worker('running_key', 'example_worker', {})
    success, msg = self.manager.start_worker('running_key', 'example_worker', {})
    self.assertFalse(success)
    self.assertEqual(msg, 'Worker already running')

  def test_library_missing_worker_file(self):
    success, msg = self.manager.start_worker('missing_file', 'non_existent', {})
    self.assertFalse(success)
    self.assertIn('not found', msg)

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
      from crazy_workers.models import Worker

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
      from crazy_workers.models import Worker

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
    from crazy_workers.models import Worker

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


class ExampleAppTestCase(unittest.TestCase):
  def setUp(self):
    self.app, _ = create_app()
    self.app.config['TESTING'] = True
    self.client = self.app.test_client()
    self.instance_path = self.app.instance_path
    self.db_path = os.path.join(self.instance_path, f'workers_internal_{self._testMethodName}.db')

    workers_dir = os.path.join(os.path.dirname(__file__), 'example_app', 'workers')
    self.manager = WorkerManager(self.db_path, workers_dir)

  def tearDown(self):
    workers = self.manager.list_workers()
    for w in workers:
      if w['status'] == 'RUNNING':
        self.manager.stop_worker(w['worker_key'])

    self.manager.dispose()
    if os.path.exists(self.db_path):
      try:
        os.remove(self.db_path)
      except PermissionError:
        import time

        time.sleep(0.1)
        try:
          os.remove(self.db_path)
        except PermissionError:
          pass

  def test_app_api(self):
    with patch('example_app.app.WorkerManager', return_value=self.manager):
      self.app, _ = create_app()
      self.client = self.app.test_client()

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
    with patch('example_app.app.WorkerManager', return_value=self.manager):
      self.app, _ = create_app()
      self.client = self.app.test_client()

      response = self.client.post('/workers/start', json={})
      self.assertEqual(response.status_code, 400)

      response = self.client.post('/workers/stop', json={})
      self.assertEqual(response.status_code, 400)

  def test_app_api_errors(self):
    with patch('example_app.app.WorkerManager', return_value=self.manager):
      self.app, _ = create_app()
      self.client = self.app.test_client()

      # Start error
      response = self.client.post('/workers/start', json={'worker_key': 'err', 'worker_type': 'missing'})
      self.assertEqual(response.status_code, 400)

      # Stop error
      response = self.client.post('/workers/stop', json={'worker_key': 'no_key'})
      self.assertEqual(response.status_code, 400)


if __name__ == '__main__':
  unittest.main()
