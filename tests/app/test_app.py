import os
import pytest
import shutil
import tempfile
from unittest.mock import patch


flask = pytest.importorskip('flask')

from sqlalchemy import create_engine, text  # noqa: E402

from crazy_workers.testing import polling  # noqa: E402
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

  def test_missing_fields_return_400(self):
    self.assertEqual(self.client.post('/workers/start', json={}).status_code, 400)
    self.assertEqual(self.client.post('/workers/stop', json={}).status_code, 400)

  def test_errors_return_400(self):
    self.assertEqual(
      self.client.post('/workers/start', json={'worker_key': 'err', 'worker_type': 'missing'}).status_code, 400
    )
    self.assertEqual(self.client.post('/workers/stop', json={'worker_key': 'no_key'}).status_code, 400)


class TestEventsRoute(BaseTestCase):
  def setUp(self):
    super().setUp()
    self.db_dir = tempfile.mkdtemp()
    self.addCleanup(shutil.rmtree, self.db_dir, ignore_errors=True)
    self.db_url = f'sqlite:///{os.path.join(self.db_dir, "app.db")}'
    with patch('example_app.app.WorkerManager') as mock_manager_class:
      mock_manager_class.return_value = self.manager
      self.app, _ = create_app(config_override={'DATABASE_URL': self.db_url})
      self.client = self.app.test_client()

  def test_events_empty_when_table_missing(self):
    response = self.client.get('/events')
    self.assertEqual(response.status_code, 200)
    self.assertEqual(response.get_json(), [])

  def test_events_returns_rows(self):
    engine = create_engine(self.db_url)
    with engine.begin() as conn:
      conn.execute(text('CREATE TABLE worker_events (worker_key TEXT, note TEXT, created_at TEXT)'))
      conn.execute(text("INSERT INTO worker_events VALUES ('w', 'hello', '2024')"))
    engine.dispose()

    response = self.client.get('/events')
    self.assertEqual(response.status_code, 200)
    data = response.get_json()
    self.assertEqual(len(data), 1)
    self.assertEqual(data[0]['note'], 'hello')


class TestExampleAppEndToEnd(BaseTestCase):
  """Full chain with a real worker process: the app shares its DB engine with
  crazy_workers and injects DATABASE_URL into the db_writer worker, which opens
  its own connection and writes rows the app then reads via /events."""

  def setUp(self):
    super().setUp()
    src = os.path.join(
      os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
      'example_app',
      'workers',
      'db_writer.py',
    )
    shutil.copy(src, os.path.join(self.workers_path, 'db_writer.py'))
    # Keep the app DB outside test_dir so an open handle never blocks its cleanup.
    self.db_dir = tempfile.mkdtemp()
    self.addCleanup(shutil.rmtree, self.db_dir, ignore_errors=True)
    self.db_url = f'sqlite:///{os.path.join(self.db_dir, "app.db")}'
    self.app, self.e2e_manager = create_app(
      config_override={'DATABASE_URL': self.db_url, 'WORKERS_DIR': self.workers_path}
    )
    self.client = self.app.test_client()

  def tearDown(self):
    # Kill the worker process (releases its handles), then drop the shared engine
    # so test_dir cleanup is not blocked on Windows.
    self.e2e_manager.stop_worker('w1')
    self.e2e_manager.storage.engine.dispose()
    self.e2e_manager.dispose()
    super().tearDown()

  def test_worker_writes_to_backend_db_via_injected_url(self):
    response = self.client.post(
      '/workers/start',
      json={
        'worker_key': 'w1',
        'worker_type': 'db_writer',
        'parameters': {'worker_key': 'w1', 'iterations': 2, 'interval': 0},
      },
    )
    self.assertEqual(response.status_code, 200)

    polling.wait_for(
      lambda: len(self.client.get('/events').get_json()) >= 2,
      msg='db_writer never wrote events to the shared database',
    )
    events = self.client.get('/events').get_json()
    self.assertTrue(any(e['worker_key'] == 'w1' for e in events))
