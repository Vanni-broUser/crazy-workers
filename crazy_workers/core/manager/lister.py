import logging
import os

from ...persistence.models import WorkerStatus

logger = logging.getLogger('crazy_workers')


def list_workers(manager):
  """Logic for listing workers, discovered and registered."""
  # 1. Get all .py files from workers_dir
  try:
    available_types = {f[:-3] for f in os.listdir(manager.workers_dir) if f.endswith('.py')}
  except Exception:
    available_types = set()

  if not manager.storage:
    # If no storage, return virtual workers for all found files
    return [
      {
        'worker_key': None,
        'worker_type': t,
        'parameters': {},
        'pid': None,
        'status': WorkerStatus.NEVER_STARTED.value,
        'last_started_at': None,
        'last_stopped_at': None,
      }
      for t in sorted(available_types)
    ]

  with manager.storage.session_scope() as session:
    from ...persistence.models import Worker

    # 2. Get registered workers from DB
    db_workers = session.query(Worker).all()
    results = []

    for worker in db_workers:
      # Update status if dead
      if worker.status == WorkerStatus.RUNNING:
        if not manager._is_process_running(worker.pid):
          logger.warning(
            f'Worker {worker.worker_key} found in RUNNING state but PID {worker.pid} is dead. Updating status.'
          )
          worker.status = WorkerStatus.STOPPED
          worker.pid = None
      results.append(worker.to_dict())

    # 3. Add virtual workers for files not in DB (using filename as key)
    # Note: A file might be in DB multiple times with different keys,
    # but here we only want to show types that have NEVER been started at all.
    registered_types = {w['worker_type'] for w in results}
    for w_type in sorted(available_types):
      if w_type not in registered_types:
        results.append(
          {
            'worker_key': None,
            'worker_type': w_type,
            'parameters': {},
            'pid': None,
            'status': WorkerStatus.NEVER_STARTED.value,
            'last_started_at': None,
            'last_stopped_at': None,
          }
        )

    return results
