import logging

from ...database.schema import Worker, WorkerStatus
from ..engine import is_worker_process


logger = logging.getLogger('crazy_workers')


def recover_workers(manager):
  if not manager.storage:
    return []

  with manager.storage.session_scope() as session:
    workers_to_restart = session.query(Worker).filter_by(status=WorkerStatus.RUNNING).all()
    to_process = [(w.worker_key, w.worker_type, w.parameters, w.pid) for w in workers_to_restart]

  restarted = []
  for key, w_type, params, pid in to_process:
    if not is_worker_process(pid, key):
      logger.info(f'Recovering worker {key}...')
      success, _ = manager.start_worker(w_type, key, params)
      if success:
        restarted.append(key)
  return restarted
