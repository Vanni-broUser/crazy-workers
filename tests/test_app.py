from unittest.mock import patch

from example_app.app import create_app
from tests.base import BaseTestCase


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
