import os
import psutil
from unittest.mock import patch

from tests.base import BaseTestCase


class TestManagerStarter(BaseTestCase):
  def test_library_start_and_stop(self):
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

  @patch('crazy_workers.core.manager.starter.subprocess.Popen')
  def test_library_immediate_failure(self, mock_popen):
    # Setup a mock process that appears to have exited with code 1
    mock_proc = mock_popen.return_value
    mock_proc.poll.return_value = 1
    mock_proc.returncode = 1
    mock_proc.pid = 9999

    # We don't need a real file if we mock Popen, but start_worker checks for file existence
    bad_worker = os.path.join(self.workers_path, 'fail.py')
    with open(bad_worker, 'w') as f:
      f.write('pass')

    success, msg = self.manager.start_worker('fail')
    self.assertFalse(success)
    self.assertEqual(msg, 'Worker process failed to start')

    # Verify the mock was called correctly
    mock_popen.assert_called_once()

  def test_library_path_traversal(self):
    success, msg = self.manager.start_worker('../etc/passwd', 'some_key')
    self.assertFalse(success)
    self.assertEqual(msg, 'Invalid worker_type or worker_key')

    success, msg = self.manager.start_worker('example_worker', '../etc/passwd')
    self.assertFalse(success)
    self.assertEqual(msg, 'Invalid worker_type or worker_key')

  def test_start_multiple_same_type_different_keys(self):
    success1, res1 = self.manager.start_worker('example_worker', worker_key='key1')
    success2, res2 = self.manager.start_worker('example_worker', worker_key='key2')

    self.assertTrue(success1)
    self.assertTrue(success2)
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

  def test_spawn_worker_process_log_error(self):
    with patch.object(self.manager, 'logs_dir', '/non/existent/path/for/logs'):
      success, result = self.manager.start_worker('example_worker', worker_key='log_err_test')
      self.assertTrue(success)
      self.assertEqual(result['status'], 'RUNNING')

  def test_concurrent_start_same_key(self):
    # _prepare_worker_record returns None when it catches an IntegrityError internally.
    # Verify that start_worker surfaces the correct error message in that case.
    success1, _ = self.manager.start_worker('example_worker', worker_key='concurrent_key')
    self.assertTrue(success1)

    with patch('crazy_workers.core.manager.starter._prepare_worker_record', return_value=None):
      success2, msg2 = self.manager.start_worker('example_worker', worker_key='concurrent_key2')
      self.assertFalse(success2)
      self.assertEqual(msg2, 'Worker state conflict (concurrent start)')
