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

  def test_start_list_stop(self):
    response = self.client.post(
      '/workers/start',
      json={'worker_key': 'app_test', 'worker_type': 'example_worker', 'parameters': {'duration': 5}},
    )
    self.assertEqual(response.status_code, 200)

    response = self.client.get('/workers')
    self.assertEqual(response.status_code, 200)
    self.assertTrue(any(w['worker_key'] == 'app_test' for w in response.get_json()))

    response = self.client.post('/workers/stop', json={'worker_key': 'app_test'})
    self.assertEqual(response.status_code, 200)

  def test_params_endpoint(self):
    params = {'a': 1}
    self.manager.start_worker('example_worker', worker_key='p_test', parameters=params)

    response = self.client.get('/workers/params/p_test')
    self.assertEqual(response.status_code, 200)
    self.assertEqual(response.get_json(), params)

    response = self.client.get('/workers/params/missing')
    self.assertEqual(response.status_code, 404)

    self.manager.stop_worker('p_test')

  def test_automatic_restore_on_startup(self):
    from crazy_workers import WorkerStatus
    from crazy_workers.database.schema import Worker

    with self.manager.storage.session_scope() as session:
      session.query(Worker).delete()
      session.add(
        Worker(
          worker_key='startup_restore',
          worker_type='example_worker',
          parameters={},
          status=WorkerStatus.RUNNING,
          pid=99999,
        )
      )

    with patch('example_app.app.WorkerManager') as mock_manager_class:
      mock_manager_class.return_value = self.manager
      create_app()

    self.wait_for_worker_status(self.manager, 'startup_restore', 'RUNNING')
    workers = self.manager.list_workers()
    worker = next(w for w in workers if w['worker_key'] == 'startup_restore')
    self.assertEqual(worker['status'], 'RUNNING')
    self.assertNotEqual(worker['pid'], 99999)
    self.manager.stop_worker('startup_restore')

  def test_missing_fields_return_400(self):
    self.assertEqual(self.client.post('/workers/start', json={}).status_code, 400)
    self.assertEqual(self.client.post('/workers/stop', json={}).status_code, 400)

  def test_errors_return_400(self):
    self.assertEqual(
      self.client.post('/workers/start', json={'worker_key': 'err', 'worker_type': 'missing'}).status_code, 400
    )
    self.assertEqual(self.client.post('/workers/stop', json={'worker_key': 'no_key'}).status_code, 400)
