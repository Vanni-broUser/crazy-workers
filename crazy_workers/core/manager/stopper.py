import logging
from sqlalchemy import func

from ...database.schema import Worker, WorkerStatus
from ..engine import terminate_process

logger = logging.getLogger('crazy_workers')


def stop_worker(manager, worker_key):
  if not manager.storage:
    return False, 'System not initialized (database missing)'

  with manager.storage.session_scope() as session:
    worker = session.query(Worker).filter_by(worker_key=worker_key).first()
    if not worker:
      return False, 'Worker not found'
    if worker.status != WorkerStatus.RUNNING:
      return False, 'Worker is not running'

    logger.info(f'Stopping worker {worker_key} (PID {worker.pid})')
    process = manager._active_processes.get(worker_key)

    try:
      terminate_process(worker.pid, popen_process=process)

      if worker_key in manager._active_processes:
        del manager._active_processes[worker_key]

      worker.status = WorkerStatus.STOPPED
      worker.pid = None
      worker.last_stopped_at = func.now()
      logger.info(f'Worker {worker_key} stopped.')
      return True, 'Worker stopped'
    except Exception as e:
      logger.error(f'Error stopping worker {worker_key}: {e}')
      return False, str(e)
