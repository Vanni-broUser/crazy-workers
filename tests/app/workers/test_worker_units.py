"""
Unit tests for example_app workers — import and call main() directly
with mocked I/O and blocking calls so coverage tracks every line.
"""

import json
import logging
import sys
import unittest
from io import StringIO
from unittest.mock import MagicMock, mock_open, patch


class TestBatchWorker(unittest.TestCase):
  def _run(self, params=None):
    argv = ['batch_worker.py', json.dumps(params)] if params is not None else ['batch_worker.py']
    with patch.object(sys, 'argv', argv), patch('time.sleep'), patch('sys.stdout', new_callable=StringIO) as out:
      from example_app.workers import batch_worker

      batch_worker.main()
      return out.getvalue()

  def test_default_params(self):
    output = self._run()
    self.assertIn('task1', output)
    self.assertIn('task2', output)
    self.assertIn('task3', output)
    self.assertIn('completed', output)

  def test_custom_items(self):
    output = self._run({'items': ['x', 'y'], 'delay': 0})
    self.assertIn('Processing: x', output)
    self.assertIn('Processing: y', output)
    self.assertIn('2/2', output)

  def test_progress_format(self):
    output = self._run({'items': ['a', 'b', 'c'], 'delay': 0})
    self.assertIn('1/3', output)
    self.assertIn('3/3', output)

  def test_empty_items(self):
    output = self._run({'items': [], 'delay': 0})
    self.assertIn('0 items', output)
    self.assertIn('completed', output)


class TestSimulatorWorker(unittest.TestCase):
  def _run(self, params=None, expect_exit=False):
    argv = ['simulator_worker.py', json.dumps(params)] if params is not None else ['simulator_worker.py']
    with patch.object(sys, 'argv', argv), patch('time.sleep'), patch('sys.stdout', new_callable=StringIO) as out:
      from example_app.workers import simulator_worker

      if expect_exit:
        with self.assertRaises(SystemExit) as ctx:
          simulator_worker.main()
        return out.getvalue(), ctx.exception.code
      else:
        simulator_worker.main()
        return out.getvalue(), 0

  def test_default_params(self):
    output, code = self._run()
    self.assertIn('10 steps', output)
    self.assertIn('completed', output)
    self.assertEqual(code, 0)

  def test_custom_steps(self):
    output, code = self._run({'steps': 3})
    self.assertIn('3/3', output)
    self.assertIn('completed', output)

  def test_fail_at(self):
    output, code = self._run({'steps': 5, 'fail_at': 3}, expect_exit=True)
    self.assertIn('simulating failure', output)
    self.assertEqual(code, 1)

  def test_fail_at_first_step(self):
    output, code = self._run({'steps': 5, 'fail_at': 1}, expect_exit=True)
    self.assertEqual(code, 1)

  def test_no_failure_when_fail_at_exceeds_steps(self):
    output, code = self._run({'steps': 3, 'fail_at': 99})
    self.assertIn('completed', output)


class TestInfiniteWorker(unittest.TestCase):
  def _module(self):
    from example_app.workers import infinite_worker

    return infinite_worker

  def test_keyboard_interrupt_exits_cleanly(self):
    mod = self._module()
    argv = ['infinite_worker.py', json.dumps({'interval': 1})]
    with (
      patch.object(sys, 'argv', argv),
      patch('sys.stdout', new_callable=StringIO) as out,
      patch('time.sleep', side_effect=[None, KeyboardInterrupt]),
    ):
      mod.main()
    self.assertIn('interrupt', out.getvalue())

  def test_default_params_no_argv(self):
    mod = self._module()
    with (
      patch.object(sys, 'argv', ['infinite_worker.py']),
      patch('sys.stdout', new_callable=StringIO) as out,
      patch('time.sleep', side_effect=[None, KeyboardInterrupt]),
    ):
      mod.main()
    self.assertIn('Starting infinite worker', out.getvalue())

  def test_unexpected_exception_exits_with_error(self):
    mod = self._module()
    argv = ['infinite_worker.py', json.dumps({'interval': 1})]
    with (
      patch.object(sys, 'argv', argv),
      patch('sys.stdout', new_callable=StringIO),
      patch('sys.stderr', new_callable=StringIO) as err,
      patch('time.sleep', side_effect=[RuntimeError('boom')]),
    ):
      with self.assertRaises(SystemExit) as ctx:
        mod.main()
    self.assertEqual(ctx.exception.code, 1)
    self.assertIn('boom', err.getvalue())

  def test_custom_message(self):
    mod = self._module()
    argv = ['infinite_worker.py', json.dumps({'interval': 0, 'message': 'hello world'})]
    with (
      patch.object(sys, 'argv', argv),
      patch('sys.stdout', new_callable=StringIO) as out,
      patch('time.sleep', side_effect=[None, KeyboardInterrupt]),
    ):
      mod.main()
    self.assertIn('hello world', out.getvalue())


class TestExampleWorker(unittest.TestCase):
  def setUp(self):
    logging.disable(logging.CRITICAL)
    from example_app.workers import example_worker
    self.mod = example_worker
    self.mod.running = True

  def tearDown(self):
    logging.disable(logging.NOTSET)
    self.mod.running = True

  def _module(self):
    return self.mod

  def test_missing_params_returns_early(self):
    mod = self._module()
    with patch.object(sys, 'argv', ['example_worker.py']):
      mod.main()  # should return without error

  def test_runs_for_duration(self):
    mod = self._module()
    argv = ['example_worker.py', json.dumps({'duration': 0, 'worker_key': 'test_w'})]
    with patch.object(sys, 'argv', argv), patch('time.sleep'):
      mod.main()

  def test_signal_stops_worker(self):
    mod = self._module()
    mod.signal_handler(15, None)
    self.assertFalse(mod.running)

  def test_worker_key_logged(self):
    mod = self._module()
    argv = ['example_worker.py', json.dumps({'duration': 0, 'worker_key': 'my_worker'})]
    with patch.object(sys, 'argv', argv), patch('time.sleep'), patch('logging.info') as mock_log:
      mod.main()
    logged = ' '.join(str(c) for c in mock_log.call_args_list)
    self.assertIn('my_worker', logged)

  def test_stopped_by_signal_logs(self):
    mod = self._module()
    mod.running = False
    argv = ['example_worker.py', json.dumps({'duration': 9999, 'worker_key': 'sig_w'})]
    with patch.object(sys, 'argv', argv), patch('time.sleep'), patch('logging.info') as mock_log:
      mod.main()
    logged = ' '.join(str(c) for c in mock_log.call_args_list)
    self.assertIn('stopped by signal', logged)


class TestNestedWorker(unittest.TestCase):
  def _module(self):
    from example_app.workers import nested_worker

    return nested_worker

  def _make_manager(self, success=True):
    mgr = MagicMock()
    mgr.start_worker.return_value = (success, {})
    return mgr

  def test_spawns_children(self):
    mod = self._module()
    mgr = self._make_manager(success=True)
    argv = ['nested_worker.py', json.dumps({'child_type': 'fake', 'num_children': 2, 'workers_dir': '/tmp'})]
    with (
      patch.object(sys, 'argv', argv),
      patch('time.sleep'),
      patch('sys.stdout', new_callable=StringIO) as out,
      patch('example_app.workers.nested_worker.WorkerManager', return_value=mgr),
    ):
      mod.main()
    self.assertEqual(mgr.start_worker.call_count, 2)
    output = out.getvalue()
    self.assertIn('child_0', output)
    self.assertIn('child_1', output)

  def test_failed_child_logged(self):
    mod = self._module()
    mgr = self._make_manager(success=False)
    argv = ['nested_worker.py', json.dumps({'child_type': 'fake', 'num_children': 1, 'workers_dir': '/tmp'})]
    with (
      patch.object(sys, 'argv', argv),
      patch('time.sleep'),
      patch('sys.stdout', new_callable=StringIO) as out,
      patch('example_app.workers.nested_worker.WorkerManager', return_value=mgr),
    ):
      mod.main()
    self.assertIn('Failed', out.getvalue())

  def test_default_params(self):
    mod = self._module()
    mgr = self._make_manager()
    with (
      patch.object(sys, 'argv', ['nested_worker.py']),
      patch('time.sleep'),
      patch('sys.stdout', new_callable=StringIO),
      patch('example_app.workers.nested_worker.WorkerManager', return_value=mgr),
    ):
      mod.main()
    self.assertEqual(mgr.start_worker.call_count, 2)

  def test_dispose_called_on_exit(self):
    mod = self._module()
    mgr = self._make_manager()
    with (
      patch.object(sys, 'argv', ['nested_worker.py']),
      patch('time.sleep'),
      patch('sys.stdout', new_callable=StringIO),
      patch('example_app.workers.nested_worker.WorkerManager', return_value=mgr),
    ):
      mod.main()
    mgr.dispose.assert_called_once()


class TestSubprocessWorker(unittest.TestCase):
  def _module(self):
    from example_app.workers import subprocess_worker

    return subprocess_worker

  def _make_child(self, pid=1234):
    child = MagicMock()
    child.pid = pid
    return child

  def test_starts_child_process(self):
    mod = self._module()
    child = self._make_child()
    with (
      patch.object(sys, 'argv', ['subprocess_worker.py']),
      patch('subprocess.Popen', return_value=child) as mock_popen,
      patch('time.sleep', side_effect=KeyboardInterrupt),
    ):
      mod.main()
    mock_popen.assert_called_once()

  def test_writes_pid_file(self):
    mod = self._module()
    child = self._make_child(pid=9999)
    argv = ['subprocess_worker.py', json.dumps({'pid_file': '/tmp/test.pid'})]
    m = mock_open()
    with (
      patch.object(sys, 'argv', argv),
      patch('subprocess.Popen', return_value=child),
      patch('builtins.open', m),
      patch('time.sleep', side_effect=KeyboardInterrupt),
    ):
      mod.main()
    m.assert_called_once_with('/tmp/test.pid', 'w')
    m().write.assert_called_once_with('9999')

  def test_no_pid_file_skips_write(self):
    mod = self._module()
    child = self._make_child()
    with (
      patch.object(sys, 'argv', ['subprocess_worker.py']),
      patch('subprocess.Popen', return_value=child),
      patch('builtins.open', mock_open()) as m,
      patch('time.sleep', side_effect=KeyboardInterrupt),
    ):
      mod.main()
    m.assert_not_called()

  def test_child_terminated_on_exit(self):
    mod = self._module()
    child = self._make_child()
    with (
      patch.object(sys, 'argv', ['subprocess_worker.py']),
      patch('subprocess.Popen', return_value=child),
      patch('time.sleep', side_effect=KeyboardInterrupt),
    ):
      mod.main()
    child.terminate.assert_called_once()
    child.wait.assert_called_once_with(timeout=3)

  def test_child_terminate_exception_suppressed(self):
    mod = self._module()
    child = self._make_child()
    child.terminate.side_effect = OSError('already dead')
    with (
      patch.object(sys, 'argv', ['subprocess_worker.py']),
      patch('subprocess.Popen', return_value=child),
      patch('time.sleep', side_effect=KeyboardInterrupt),
    ):
      mod.main()  # should not raise despite terminate() failing
    child.terminate.assert_called_once()
