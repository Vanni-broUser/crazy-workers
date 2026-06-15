"""Polling helpers for tests that drive *real* worker processes.

The FakeBackend (see backends.py) removes the need for polling in
orchestration tests — there is nothing asynchronous to wait for. But the few
genuine end-to-end tests that launch real processes still need to wait for
something to happen (a log line, a status transition, a PID to die) without
resorting to fixed ``time.sleep`` calls, which are the main source of
flakiness.

These are plain functions, usable from any test framework (pytest, unittest,
plain scripts):

    from crazy_workers.testing import wait_for_log, wait_for_worker_status

    wait_for_worker_status(manager, '1', 'RUNNING')
    wait_for_log(log_path, 'recording started')

Each helper raises ``AssertionError`` on timeout so it reads naturally inside
a test and produces a useful failure message.
"""

import os
import psutil
import time


def wait_for(condition, timeout=10.0, interval=0.05, msg='Condition never met'):
  """Poll ``condition`` until it returns truthy or ``timeout`` seconds elapse.

  Raises AssertionError with ``msg`` on timeout.
  """
  deadline = time.monotonic() + timeout
  while time.monotonic() < deadline:
    if condition():
      return
    time.sleep(interval)
  raise AssertionError(msg)


def wait_for_file(path, timeout=10.0):
  """Wait until ``path`` exists on disk."""
  wait_for(lambda: os.path.exists(path), timeout=timeout, msg=f'File never appeared: {path}')


def wait_for_log(log_path, text, timeout=10.0):
  """Wait until ``text`` appears in the file at ``log_path``."""

  def check():
    if not os.path.exists(log_path):
      return False
    with open(log_path) as f:
      return text in f.read()

  wait_for(check, timeout=timeout, msg=f'{text!r} not found in {log_path}')


def wait_for_worker_status(manager, key, status, timeout=10.0):
  """Wait until the worker ``key`` reaches ``status`` in the manager's view."""

  def check():
    w = next((w for w in manager.list_workers() if w['worker_key'] == key), None)
    return w is not None and w['status'] == status

  wait_for(check, timeout=timeout, msg=f'Worker {key!r} never reached status {status!r}')


def wait_for_worker_in_db(manager, key, timeout=10.0):
  """Wait until the worker ``key`` shows up in the manager's listing at all."""
  wait_for(
    lambda: any(w['worker_key'] == key for w in manager.list_workers()),
    timeout=timeout,
    msg=f'Worker {key!r} never appeared in DB',
  )


def wait_for_worker_pid(manager, key, timeout=10.0):
  """Wait until the worker ``key`` has been assigned a PID."""

  def check():
    w = next((w for w in manager.list_workers() if w['worker_key'] == key), None)
    return w is not None and w['pid'] is not None

  wait_for(check, timeout=timeout, msg=f'Worker {key!r} never got a PID')


def wait_for_pid_dead(pid, timeout=10.0):
  """Wait until the OS process ``pid`` no longer exists."""
  wait_for(lambda: not psutil.pid_exists(pid), timeout=timeout, msg=f'PID {pid} never died')
