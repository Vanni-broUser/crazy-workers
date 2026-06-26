import os
import shutil
import tempfile
import unittest

from crazy_workers import WorkerClient


class TestWorkerClient(unittest.TestCase):
  """The control plane writes desired state only — it never spawns a process."""

  def setUp(self):
    self.tmp = tempfile.mkdtemp(prefix='cw_client_')
    self.url = f'sqlite:///{os.path.join(self.tmp, "workers.db")}'
    self.client = WorkerClient(db_url=self.url, create_tables=True)

  def tearDown(self):
    self.client.dispose()
    shutil.rmtree(self.tmp, ignore_errors=True)

  def test_request_start_upserts_desired_running(self):
    key = self.client.request_start('register', worker_key='42', parameters={'device_id': 42})
    self.assertEqual(key, '42')

    worker = self.client.get('42')
    self.assertEqual(worker['desired_status'], 'RUNNING')
    self.assertEqual(worker['worker_type'], 'register')
    self.assertEqual(worker['parameters'], {'device_id': 42})
    # Control plane only: nothing was actually started.
    self.assertEqual(worker['status'], 'STOPPED')
    self.assertIsNone(worker['pid'])

  def test_request_start_defaults_key_to_type(self):
    self.assertEqual(self.client.request_start('renamer'), 'renamer')

  def test_request_start_is_idempotent_upsert(self):
    self.client.request_start('register', worker_key='42', parameters={'a': 1})
    self.client.request_start('register', worker_key='42', parameters={'a': 2})

    rows = [w for w in self.client.list() if w['worker_key'] == '42']
    self.assertEqual(len(rows), 1)
    self.assertEqual(rows[0]['parameters'], {'a': 2})

  def test_request_stop_sets_desired_stopped(self):
    self.client.request_start('register', worker_key='42')
    self.assertTrue(self.client.request_stop('42'))
    self.assertEqual(self.client.get('42')['desired_status'], 'STOPPED')

  def test_request_stop_missing_returns_false(self):
    self.assertFalse(self.client.request_stop('nope'))

  def test_list_and_get(self):
    self.client.request_start('a')
    self.client.request_start('b')
    self.assertEqual({w['worker_key'] for w in self.client.list()}, {'a', 'b'})
    self.assertIsNone(self.client.get('missing'))

  def test_context_manager_disposes_but_data_persists(self):
    with WorkerClient(db_url=self.url, create_tables=False) as client:
      client.request_start('x')
    self.assertIsNotNone(self.client.get('x'))
