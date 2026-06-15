import os
import tempfile
import time
import unittest

from crazy_workers.testing import (
  wait_for,
  wait_for_file,
  wait_for_log,
  wait_for_pid_dead,
  wait_for_worker_in_db,
  wait_for_worker_pid,
  wait_for_worker_status,
)


class _FakeManager:
  """Minimal stand-in exposing list_workers() the way WorkerManager does."""

  def __init__(self, workers):
    self._workers = workers

  def list_workers(self):
    return self._workers


class TestWaitFor(unittest.TestCase):
  def test_returns_when_condition_already_true(self):
    wait_for(lambda: True, timeout=0.2)

  def test_becomes_true_after_a_few_polls(self):
    state = {'calls': 0}

    def condition():
      state['calls'] += 1
      return state['calls'] >= 3

    wait_for(condition, timeout=1.0, interval=0.01)
    self.assertGreaterEqual(state['calls'], 3)

  def test_raises_on_timeout(self):
    with self.assertRaises(AssertionError) as ctx:
      wait_for(lambda: False, timeout=0.05, interval=0.01, msg='nope')
    self.assertEqual(str(ctx.exception), 'nope')


class TestFileAndLogHelpers(unittest.TestCase):
  def setUp(self):
    self.dir = tempfile.mkdtemp()

  def test_wait_for_file(self):
    path = os.path.join(self.dir, 'present.txt')
    with open(path, 'w') as f:
      f.write('x')
    wait_for_file(path, timeout=0.2)

  def test_wait_for_file_times_out(self):
    with self.assertRaises(AssertionError):
      wait_for_file(os.path.join(self.dir, 'missing.txt'), timeout=0.05)

  def test_wait_for_log_finds_text(self):
    path = os.path.join(self.dir, 'worker.log')
    with open(path, 'w') as f:
      f.write('boot\nrecording started\n')
    wait_for_log(path, 'recording started', timeout=0.2)

  def test_wait_for_log_missing_file_times_out(self):
    with self.assertRaises(AssertionError):
      wait_for_log(os.path.join(self.dir, 'nope.log'), 'anything', timeout=0.05)

  def test_wait_for_log_text_absent_times_out(self):
    path = os.path.join(self.dir, 'worker.log')
    with open(path, 'w') as f:
      f.write('only boot here\n')
    with self.assertRaises(AssertionError):
      wait_for_log(path, 'recording started', timeout=0.05)


class TestWorkerHelpers(unittest.TestCase):
  def test_wait_for_worker_status(self):
    manager = _FakeManager([{'worker_key': '1', 'status': 'RUNNING', 'pid': 42}])
    wait_for_worker_status(manager, '1', 'RUNNING', timeout=0.2)

  def test_wait_for_worker_status_wrong_status_times_out(self):
    manager = _FakeManager([{'worker_key': '1', 'status': 'STOPPED', 'pid': 42}])
    with self.assertRaises(AssertionError):
      wait_for_worker_status(manager, '1', 'RUNNING', timeout=0.05)

  def test_wait_for_worker_in_db(self):
    manager = _FakeManager([{'worker_key': 'k', 'status': 'RUNNING', 'pid': 1}])
    wait_for_worker_in_db(manager, 'k', timeout=0.2)

  def test_wait_for_worker_in_db_absent_times_out(self):
    manager = _FakeManager([])
    with self.assertRaises(AssertionError):
      wait_for_worker_in_db(manager, 'k', timeout=0.05)

  def test_wait_for_worker_pid(self):
    manager = _FakeManager([{'worker_key': '1', 'status': 'RUNNING', 'pid': 99}])
    wait_for_worker_pid(manager, '1', timeout=0.2)

  def test_wait_for_worker_pid_none_times_out(self):
    manager = _FakeManager([{'worker_key': '1', 'status': 'STARTING', 'pid': None}])
    with self.assertRaises(AssertionError):
      wait_for_worker_pid(manager, '1', timeout=0.05)


class TestWaitForPidDead(unittest.TestCase):
  def test_already_dead_pid(self):
    # An astronomically high PID that is virtually guaranteed not to exist.
    wait_for_pid_dead(2**31 - 1, timeout=0.2)

  def test_live_pid_times_out(self):
    with self.assertRaises(AssertionError):
      wait_for_pid_dead(os.getpid(), timeout=0.05)

  def test_interval_is_respected(self):
    start = time.monotonic()
    with self.assertRaises(AssertionError):
      wait_for(lambda: False, timeout=0.15, interval=0.05)
    self.assertGreaterEqual(time.monotonic() - start, 0.15)


if __name__ == '__main__':
  unittest.main()
