import os
import shutil
import tempfile
import unittest

from crazy_workers import WorkerManager
from crazy_workers.core.backend import ProcessBackend
from crazy_workers.testing import FakeBackend, make_test_backend


class TestProcessBackendContract(unittest.TestCase):
  def test_base_methods_must_be_implemented(self):
    backend = ProcessBackend()
    with self.assertRaises(NotImplementedError):
      backend.spawn(worker_key='k', worker_type='t', worker_path='t.py', parameters={}, env=None, log_path='x')
    with self.assertRaises(NotImplementedError):
      backend.is_alive(pid=1, worker_key='k')
    with self.assertRaises(NotImplementedError):
      backend.terminate(pid=1, worker_key='k')


class TestFakeBackend(unittest.TestCase):
  def setUp(self):
    self.backend = FakeBackend()

  def _spawn(self, key, wtype):
    return self.backend.spawn(
      worker_key=key, worker_type=wtype, worker_path=f'{wtype}.py', parameters={'k': key}, env=None, log_path='x.log'
    )

  def test_spawn_returns_handle_and_records(self):
    handle = self._spawn('1', 'register')
    self.assertIsNotNone(handle.pid)
    self.assertEqual(self.backend.started_types, ['register'])
    self.assertEqual(self.backend.started_keys, ['1'])
    self.assertTrue(self.backend.is_running('1'))

  def test_is_alive_is_pid_reuse_safe(self):
    handle = self._spawn('1', 'register')
    self.assertTrue(self.backend.is_alive(pid=handle.pid, worker_key='1'))
    # stesso pid ma chiave diversa -> non e' il nostro worker
    self.assertFalse(self.backend.is_alive(pid=handle.pid, worker_key='other'))

  def test_terminate_marks_dead(self):
    handle = self._spawn('1', 'register')
    self.backend.terminate(pid=handle.pid, worker_key='1')
    self.assertFalse(self.backend.is_running('1'))
    self.assertFalse(self.backend.is_alive(pid=handle.pid, worker_key='1'))

  def test_crash_then_restart_tracks_state(self):
    first = self._spawn('1', 'register')
    self.backend.crash('1')
    self.assertFalse(self.backend.is_running('1'))
    # un vecchio pid resta morto anche dopo un nuovo spawn della stessa chiave
    second = self._spawn('1', 'register')
    self.assertFalse(self.backend.is_alive(pid=first.pid, worker_key='1'))
    self.assertTrue(self.backend.is_alive(pid=second.pid, worker_key='1'))
    self.assertEqual(self.backend.start_count('1'), 2)

  def test_running_keys_and_parameters_for(self):
    self._spawn('1', 'register')
    self._spawn('2', 'renamer')
    self.backend.crash('1')
    self.assertEqual(set(self.backend.running_keys), {'2'})
    self.assertEqual(self.backend.parameters_for('2'), {'k': '2'})
    self.assertIsNone(self.backend.parameters_for('nope'))

  def test_make_test_backend_unknown_mode(self):
    with self.assertRaises(ValueError):
      make_test_backend('nonexistent')


class TestForTesting(unittest.TestCase):
  def setUp(self):
    self.dir = tempfile.mkdtemp()
    self.workers = os.path.join(self.dir, 'workers')
    os.makedirs(self.workers)
    for name in ('register.py', 'renamer.py'):
      with open(os.path.join(self.workers, name), 'w') as f:
        f.write('# dummy worker\n')
    self.manager = WorkerManager.for_testing(self.workers)

  def tearDown(self):
    self.manager.dispose()
    shutil.rmtree(self.dir, ignore_errors=True)

  def test_orchestration_without_processes(self):
    ok, result = self.manager.start_worker('register', worker_key='1')
    self.assertTrue(ok)
    self.assertEqual(result['status'], 'RUNNING')
    self.manager.start_worker('renamer', worker_key='renamer_1')

    self.assertEqual(self.manager.test.started_types, ['register', 'renamer'])
    self.assertTrue(self.manager.test.is_running('1'))
    self.assertTrue(self.manager.test.is_running('renamer_1'))

  def test_stop_marks_not_running(self):
    self.manager.start_worker('register', worker_key='1')
    ok, _ = self.manager.stop_worker('1')
    self.assertTrue(ok)
    self.assertFalse(self.manager.test.is_running('1'))

  def test_recovery_restarts_crashed_worker(self):
    self.manager.start_worker('register', worker_key='1')
    self.manager.test.crash('1')

    restarted = self.manager.recover_workers()
    self.assertIn('1', restarted)
    self.assertEqual(self.manager.test.start_count('1'), 2)
    self.assertTrue(self.manager.test.is_running('1'))

  def test_already_running_is_detected(self):
    self.manager.start_worker('register', worker_key='1')
    ok, msg = self.manager.start_worker('register', worker_key='1')
    self.assertFalse(ok)
    self.assertEqual(msg, 'Worker already running')
