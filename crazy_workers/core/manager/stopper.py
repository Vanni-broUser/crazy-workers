import logging
from sqlalchemy import func

from ...database.schema import Worker, WorkerStatus
from ..engine import is_worker_process, terminate_process


logger = logging.getLogger('crazy_workers')


def stop_worker(manager, worker_key):
  if not manager.storage:
    return False, 'System not initialized (database missing)'

  # Collect everything we need from the DB, then release the session before
  # calling terminate_process (which can block for up to `timeout` seconds).
  with manager.storage.session_scope() as session:
    worker = session.query(Worker).filter_by(worker_key=worker_key).first()
    if not worker:
      return False, 'Worker not found'
    if worker.status != WorkerStatus.RUNNING:
      return False, 'Worker is not running'

    pid = worker.pid
    # PIDs of other managed workers — their processes must not be killed even
    # if they happen to be child processes of the worker being stopped.
    managed_pids = {
      w.pid
      for w in session.query(Worker)
      .filter(
        Worker.status == WorkerStatus.RUNNING,
        Worker.worker_key != worker_key,
        Worker.pid.isnot(None),
      )
      .all()
    }

  logger.info(f'Stopping worker {worker_key} (PID {pid})')
  process = manager._active_processes.get(worker_key)

  # Guard against PID reuse: confirm the PID still belongs to THIS worker before
  # signalling it. After a crash/restart — or in a fresh manager that never held
  # this worker's handle — the OS may have recycled the PID for an unrelated
  # process; terminating it blindly would take down the wrong process.
  if is_worker_process(pid, worker_key):
    try:
      terminate_process(pid, popen_process=process, exclude_pids=managed_pids)
    except Exception as e:
      logger.error(f'Error stopping worker {worker_key}: {e}')
      return False, str(e)
  else:
    logger.warning(
      f'Worker {worker_key} PID {pid} is no longer a live {worker_key!r} process '
      f'(already exited or PID reused). Marking stopped without signalling.'
    )

  if worker_key in manager._active_processes:
    del manager._active_processes[worker_key]

  with manager.storage.session_scope() as session:
    worker = session.query(Worker).filter_by(worker_key=worker_key).first()
    if worker:
      worker.status = WorkerStatus.STOPPED
      worker.pid = None
      worker.last_stopped_at = func.now()

  logger.info(f'Worker {worker_key} stopped.')
  return True, 'Worker stopped'
