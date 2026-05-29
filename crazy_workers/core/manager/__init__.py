import logging
import os

from ...database.storage import Storage
from ..engine import is_process_running
from ..recovery import RecoveryLock
from .lister import list_workers
from .recoverer import recover_workers
from .starter import start_worker
from .stopper import stop_worker


logger = logging.getLogger('crazy_workers')


class WorkerManager:
  def __init__(self, workers_dir='workers', create_dir=True):
    self.workers_dir = workers_dir
    self._validate_workers_dir(create_dir)

    self.service_dir = os.path.join(self.workers_dir, '.service')
    self.logs_dir = os.path.join(self.service_dir, 'logs')
    self.db_path = os.path.join(self.service_dir, 'workers.db')

    self._initialize_storage(create_dir)
    self._active_processes = {}  # worker_key -> Popen object

  def __enter__(self):
    return self

  def __exit__(self, exc_type, exc_val, exc_tb):
    self.dispose()

  def _validate_workers_dir(self, create_dir):
    """Checks if the workers directory exists and creates it if allowed."""
    if not os.path.isdir(self.workers_dir):
      if create_dir:
        os.makedirs(self.workers_dir, exist_ok=True)
      else:
        raise ValueError(f'Workers directory "{self.workers_dir}" does not exist.')

  def _initialize_storage(self, create_dir):
    """Sets up service directories and storage if allowed or if they already exist."""
    if create_dir:
      os.makedirs(self.service_dir, exist_ok=True)
      os.makedirs(self.logs_dir, exist_ok=True)
      self.storage = Storage(self.db_path)
    else:
      # If not allowed to create, only initialize storage if the DB already exists
      if os.path.exists(self.db_path):
        self.storage = Storage(self.db_path)
      else:
        self.storage = None

  def _is_process_running(self, pid):
    """Internal wrapper for process check."""
    return is_process_running(pid)

  def start_worker(self, worker_type, worker_key=None, parameters=None, env=None):
    return start_worker(self, worker_type, worker_key, parameters, env)

  def stop_worker(self, worker_key):
    return stop_worker(self, worker_key)

  def list_workers(self):
    return list_workers(self)

  def recover_workers(self):
    lock_path = f'{self.db_path}.recovery.lock'
    lock = RecoveryLock(lock_path)

    if lock.acquire():
      try:
        logger.info('Starting worker recovery process.')
        return recover_workers(self)
      finally:
        lock.release()
    else:
      logger.debug('Recovery lock held by another process. Skipping.')
      return []

  def dispose(self):
    """Clean up resources like database connections. Does NOT kill background processes."""
    self._active_processes.clear()
    if self.storage:
      self.storage.dispose()
