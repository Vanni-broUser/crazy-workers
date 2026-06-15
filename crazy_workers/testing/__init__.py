"""Testing utilities for projects that build on crazy_workers.

Two complementary tools:

1. A FakeBackend, for fast/deterministic *orchestration* tests that never
   launch a real process:

       from crazy_workers import WorkerManager

       manager = WorkerManager.for_testing('workers')   # uses FakeBackend
       ...
       assert manager.test.started_types == ['register', 'renamer']

2. Polling helpers, for the few genuine end-to-end tests that *do* launch real
   processes and must wait for something to happen — without fixed sleeps:

       from crazy_workers.testing import wait_for_log, wait_for_worker_status

       wait_for_worker_status(manager, '1', 'RUNNING')
"""

from .backends import FakeBackend
from .polling import (
  wait_for,
  wait_for_file,
  wait_for_log,
  wait_for_pid_dead,
  wait_for_worker_in_db,
  wait_for_worker_pid,
  wait_for_worker_status,
)


def make_test_backend(mode='fake'):
  """Factory used by WorkerManager.for_testing to pick a test backend."""
  if mode == 'fake':
    return FakeBackend()
  raise ValueError(f'Unknown test backend mode: {mode!r}')


__all__ = [
  'FakeBackend',
  'make_test_backend',
  'wait_for',
  'wait_for_file',
  'wait_for_log',
  'wait_for_pid_dead',
  'wait_for_worker_in_db',
  'wait_for_worker_pid',
  'wait_for_worker_status',
]
