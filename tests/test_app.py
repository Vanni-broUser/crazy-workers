import pytest
from unittest.mock import patch


flask = pytest.importorskip('flask')

from example_app.app import create_app  # noqa: E402
from tests.base import BaseTestCase  # noqa: E402


class TestExampleApp(BaseTestCase):
  def setUp(self):
    super().setUp()
    with patch('example_app.app.WorkerManager') as mock_manager_class:
      mock_manager_class.return_value = self.manager
      self.app, _ = create_app()
      self.app.config['TESTING'] = True
      self.client = self.app.test_client()

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

  def test_app_params_and_restore(self):
    # Setup worker with params
    params = {'a': 1}
    self.manager.start_worker('example_worker', worker_key='p_test', parameters=params)

    # Test Params endpoint
    response = self.client.get('/workers/params/p_test')
    self.assertEqual(response.status_code, 200)
    self.assertEqual(response.get_json(), params)

    # Test Params Not Found
    response = self.client.get('/workers/params/missing')
    self.assertEqual(response.status_code, 404)

    self.manager.stop_worker('p_test')

  def test_app_automatic_restore_on_startup(self):
    # 1. Setup a "dead" worker in DB that needs restoration
    from crazy_workers import WorkerStatus
    from crazy_workers.database.schema import Worker

    with self.manager.storage.session_scope() as session:
      session.query(Worker).delete()
      worker = Worker(
        worker_key='startup_restore',
        worker_type='example_worker',
        parameters={},
        status=WorkerStatus.RUNNING,
        pid=99999,
      )
      session.add(worker)

    # 2. Re-create the app (this should trigger recover_workers)
    with patch('example_app.app.WorkerManager') as mock_manager_class:
      mock_manager_class.return_value = self.manager
      # When create_app is called, it calls manager.recover_workers()
      create_app()

    # 3. Verify it's running
    workers = self.manager.list_workers()
    worker = next(w for w in workers if w['worker_key'] == 'startup_restore')
    self.assertEqual(worker['status'], 'RUNNING')
    self.assertNotEqual(worker['pid'], 99999)

    self.manager.stop_worker('startup_restore')

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
