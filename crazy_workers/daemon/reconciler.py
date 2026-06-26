import logging
import time
from datetime import datetime, timedelta, timezone

from ..database.schema import DesiredStatus, Worker, WorkerStatus


logger = logging.getLogger('crazy_workers')

_BACKOFF_BASE_SECONDS = 1
_BACKOFF_MAX_SECONDS = 60
# Cap the exponent so a long-crashed worker doesn't compute an astronomically
# large intermediate before min() clamps it.
_BACKOFF_MAX_EXPONENT = 16


class Reconciler:
  """Single-owner loop: drives actual worker state toward desired state.

  Owns every worker process for one workers_dir/DB. Clients never spawn; they
  only set desired_status in the shared DB and this loop makes it so.

  | desired  | alive | action                              |
  |----------|-------|-------------------------------------|
  | RUNNING  | no    | start (skipped while in backoff)    |
  | RUNNING  | yes   | noop (reconcile observed status)    |
  | STOPPED  | yes   | stop                                |
  | STOPPED  | no    | noop                                |
  """

  def __init__(self, manager, interval=2.0):
    self.manager = manager
    self.interval = interval
    self._stop = False

  def run_forever(self):
    logger.info('Reconciler started (interval=%ss)', self.interval)
    while not self._stop:
      try:
        self.reconcile_once()
      except Exception:
        logger.exception('Reconcile pass failed; continuing.')
      # Sleep in small slices so a SIGTERM-triggered stop is honoured promptly
      # instead of after a full interval.
      self._interruptible_sleep(self.interval)
    logger.info('Reconciler stopped.')

  def stop(self):
    self._stop = True

  def _interruptible_sleep(self, seconds):
    deadline = time.monotonic() + seconds
    while not self._stop and time.monotonic() < deadline:
      time.sleep(min(0.2, deadline - time.monotonic()))

  def reconcile_once(self):
    """One pass over every worker. Returns the actions taken (for tests/observability)."""
    actions = []
    for row in self._load_snapshot():
      action = self._reconcile_worker(row)
      if action:
        actions.append((row['worker_key'], action))
    return actions

  def _load_snapshot(self):
    # Read everything we need into plain dicts and release the session before
    # touching processes — start/stop open their own short-lived sessions.
    with self.manager.storage.session_scope() as session:
      return [
        {
          'worker_key': w.worker_key,
          'worker_type': w.worker_type,
          'parameters': w.parameters,
          'pid': w.pid,
          'desired': w.desired_status,
          'status': w.status,
          'restart_count': w.restart_count,
          'last_exit_at': w.last_exit_at,
        }
        for w in session.query(Worker).all()
      ]

  def _reconcile_worker(self, row):
    alive = self.manager.backend.is_alive(pid=row['pid'], worker_key=row['worker_key'])

    if row['desired'] == DesiredStatus.RUNNING and not alive:
      if self._in_backoff(row):
        return None
      logger.info('Reconcile: starting %s', row['worker_key'])
      self.manager.start_worker(row['worker_type'], row['worker_key'], row['parameters'])
      return 'start'
    if row['desired'] == DesiredStatus.STOPPED and alive:
      logger.info('Reconcile: stopping %s', row['worker_key'])
      self.manager.stop_worker(row['worker_key'])
      return 'stop'
    if row['desired'] == DesiredStatus.RUNNING and alive and row['status'] != WorkerStatus.RUNNING:
      # Process is up but the observed status drifted (e.g. left STARTING). Heal it.
      self._mark_running(row['worker_key'])
      return 'mark_running'
    return None

  def _in_backoff(self, row):
    if not row['last_exit_at'] or row['status'] != WorkerStatus.CRASHED:
      return False
    exponent = min(row['restart_count'], _BACKOFF_MAX_EXPONENT)
    delay = min(_BACKOFF_BASE_SECONDS * (2**exponent), _BACKOFF_MAX_SECONDS)
    last_exit = row['last_exit_at']
    # last_exit_at is stored as UTC wall-clock; coerce naive values read back
    # from the DB to aware UTC so the comparison never mixes naive and aware.
    if last_exit.tzinfo is None:
      last_exit = last_exit.replace(tzinfo=timezone.utc)
    return datetime.now(timezone.utc) < last_exit + timedelta(seconds=delay)

  def _mark_running(self, worker_key):
    with self.manager.storage.session_scope() as session:
      worker = session.query(Worker).filter_by(worker_key=worker_key).first()
      if worker:
        worker.status = WorkerStatus.RUNNING
