"""Process backends: the seam between the worker state machine and the OS.

WorkerManager never spawns or signals processes directly — it goes through a
ProcessBackend. SubprocessBackend is the default and launches real OS
processes. Alternative backends (e.g. for testing) live in
crazy_workers.testing and let consumer projects exercise their orchestration
logic without launching anything.
"""

import json
import logging
import os
import subprocess
import sys

from .engine import is_worker_process, terminate_process, worker_key_token


logger = logging.getLogger('crazy_workers')

# How long to wait after spawning before declaring the worker started. This is
# only an *immediate-failure* guard: it catches scripts that die on launch
# (bad import, syntax error, missing module). Keep it small so spawn stays
# responsive.
_STARTUP_GRACE_SECONDS = 0.05


class WorkerHandle:
  """Opaque reference to a launched worker, returned by ProcessBackend.spawn.

  `process` is backend-specific (a Popen for SubprocessBackend, None for
  backends that do not run real processes).
  """

  def __init__(self, pid, process=None):
    self.pid = pid
    self.process = process


class ProcessBackend:
  """Interface every backend implements. See SubprocessBackend for semantics."""

  def spawn(self, *, worker_key, worker_type, worker_path, parameters, env, log_path):
    """Launch a worker. Return a WorkerHandle, or None if it died immediately."""
    raise NotImplementedError

  def is_alive(self, *, pid, worker_key):
    """True only if `pid` is alive AND still belongs to `worker_key` (PID-reuse safe)."""
    raise NotImplementedError

  def terminate(self, *, pid, worker_key, handle=None, exclude_pids=None):
    """Stop the worker process, sparing any independently-managed children."""
    raise NotImplementedError


class SubprocessBackend(ProcessBackend):
  """Default backend: each worker runs as an independent OS process."""

  def spawn(self, *, worker_key, worker_type, worker_path, parameters, env, log_path):
    child_env = os.environ.copy()
    if env:
      child_env.update(env)

    log_fh = self._open_log(worker_key, log_path)
    # log_fh ownership is transferred to Popen; Popen duplicates it via os.dup2,
    # so we close our copy right after spawning.
    dest = log_fh if log_fh else subprocess.DEVNULL

    process = subprocess.Popen(
      [
        sys.executable,
        '-u',
        '-m',
        'crazy_workers._bootstrap',
        worker_key_token(worker_key),
        worker_path,
        json.dumps(parameters),
      ],
      stdout=dest,
      stderr=dest,
      text=True,
      env=child_env,
    )
    if log_fh:
      log_fh.close()

    if self._died_immediately(process, worker_key):
      return None

    logger.info(f'Worker {worker_key} started with PID {process.pid}')
    return WorkerHandle(process.pid, process)

  def is_alive(self, *, pid, worker_key):
    return is_worker_process(pid, worker_key)

  def terminate(self, *, pid, worker_key, handle=None, exclude_pids=None):
    popen = handle.process if handle else None
    terminate_process(pid, popen_process=popen, exclude_pids=exclude_pids)

  def _open_log(self, worker_key, log_path):
    try:
      fh = open(log_path, 'a')
      logger.info(f'Worker {worker_key} logging to {log_path}')
      return fh
    except Exception as e:
      logger.error(f'Failed to open log file for worker {worker_key}: {e}')
      return None

  def _died_immediately(self, process, worker_key):
    try:
      process.wait(timeout=_STARTUP_GRACE_SECONDS)
      logger.error(f'Worker {worker_key} failed to start immediately (exit code: {process.returncode})')
      return True
    except subprocess.TimeoutExpired:
      # Expected case: still running after the grace period.
      return False
