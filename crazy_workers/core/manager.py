import json
import logging
import os
import subprocess
import sys
import time
from sqlalchemy.exc import IntegrityError

from ..persistence.models import Worker, WorkerStatus
from ..persistence.storage import Storage
from .engine import is_process_running, terminate_process
from .recovery import RecoveryLock

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
    if not self.storage:
      return False, 'System not initialized (database missing)'

    worker_key = worker_key or worker_type
    if not self._validate_inputs(worker_type, worker_key):
      return False, 'Invalid worker_type or worker_key'

    parameters = parameters or {}
    with self.storage.session_scope() as session:
      worker = session.query(Worker).filter_by(worker_key=worker_key).first()

      if self._check_already_running(worker, session):
        return False, 'Worker already running'

      worker = self._prepare_worker_record(worker, worker_type, worker_key, parameters, session)
      if not worker:
        return False, 'Worker state conflict (concurrent start)'

      worker_path = self._get_worker_script_path(worker_type)
      if not worker_path:
        worker.status = WorkerStatus.STOPPED
        return False, f'Worker file {worker_type}.py not found'

      return self._spawn_worker_process(worker, worker_path, parameters, env, session)

  def _validate_inputs(self, worker_type, worker_key):
    for name, val in [('worker_type', worker_type), ('worker_key', worker_key)]:
      if '..' in val or os.path.isabs(val) or '/' in val or '\\' in val:
        logger.error(f'Invalid {name}: {val}. Potential path traversal attempt.')
        return False
    return True

  def _check_already_running(self, worker, session):
    if worker and worker.status == WorkerStatus.RUNNING:
      if self._is_process_running(worker.pid):
        logger.info(f'Worker {worker.worker_key} already running with PID {worker.pid}')
        return True
      else:
        logger.warning(f'Worker {worker.worker_key} found in RUNNING state but PID {worker.pid} is dead. Cleaning up.')
        worker.status = WorkerStatus.CRASHED
        session.commit()
    return False

  def _prepare_worker_record(self, worker, worker_type, worker_key, parameters, session):
    if not worker:
      worker = Worker(worker_key=worker_key, worker_type=worker_type, parameters=parameters)
      session.add(worker)
    else:
      worker.worker_type = worker_type
      worker.parameters = parameters
      worker.status = WorkerStatus.STARTING

    try:
      session.commit()
      return worker
    except IntegrityError:
      session.rollback()
      logger.error(f'Concurrent start attempt for worker {worker_key}')
      return None

  def _get_worker_script_path(self, worker_type):
    worker_filename = f'{worker_type}.py'
    worker_path = os.path.join(self.workers_dir, worker_filename)
    if not os.path.exists(worker_path):
      logger.error(f'Worker file {worker_filename} not found in {self.workers_dir}')
      return None
    return worker_path

  def _spawn_worker_process(self, worker, worker_path, parameters, env, session):
    child_env = os.environ.copy()
    if env:
      child_env.update(env)

    log_file_path = os.path.join(self.logs_dir, f'{worker.worker_key}.log')
    log_file = None
    try:
      log_file = open(log_file_path, 'a')
      stdout_dest = log_file
      stderr_dest = log_file
      logger.info(f'Worker {worker.worker_key} logging to {log_file_path}')
    except Exception as e:
      logger.error(f'Failed to open log file for worker {worker.worker_key}: {e}')
      stdout_dest = subprocess.DEVNULL
      stderr_dest = subprocess.DEVNULL

    try:
      process = subprocess.Popen(
        [sys.executable, worker_path, json.dumps(parameters)],
        stdout=stdout_dest,
        stderr=stderr_dest,
        text=True,
        env=child_env,
      )

      time.sleep(0.05)
      if process.poll() is not None:
        logger.error(f'Worker {worker.worker_key} failed to start immediately (exit code: {process.returncode})')
        worker.status = WorkerStatus.CRASHED
        worker.pid = None
        session.commit()
        return False, 'Worker process failed to start'

      worker.pid = process.pid
      worker.status = WorkerStatus.RUNNING
      session.commit()

      self._active_processes[worker.worker_key] = process
      logger.info(f'Worker {worker.worker_key} started with PID {worker.pid}')
      return True, worker.to_dict()
    finally:
      if log_file:
        log_file.close()

  def stop_worker(self, worker_key):
    if not self.storage:
      return False, 'System not initialized (database missing)'

    with self.storage.session_scope() as session:
      worker = session.query(Worker).filter_by(worker_key=worker_key).first()
      if not worker or worker.status != WorkerStatus.RUNNING:
        return False, 'Worker not found or not running'

      logger.info(f'Stopping worker {worker_key} (PID {worker.pid})')
      process = self._active_processes.get(worker_key)

      try:
        terminate_process(worker.pid, popen_process=process)

        if worker_key in self._active_processes:
          del self._active_processes[worker_key]

        worker.status = WorkerStatus.STOPPED
        worker.pid = None
        logger.info(f'Worker {worker_key} stopped.')
        return True, 'Worker stopped'
      except Exception as e:
        logger.error(f'Error stopping worker {worker_key}: {e}')
        return False, str(e)

  def list_workers(self):
    if not self.storage:
      return []

    with self.storage.session_scope() as session:
      workers = session.query(Worker).all()
      for worker in workers:
        if worker.status == WorkerStatus.RUNNING:
          if not self._is_process_running(worker.pid):
            logger.warning(
              f'Worker {worker.worker_key} found in RUNNING state but PID {worker.pid} is dead. Updating status.'
            )
            worker.status = WorkerStatus.STOPPED
            worker.pid = None
      return [w.to_dict() for w in workers]

  def recover_workers(self):
    lock_path = f'{self.db_path}.recovery.lock'
    lock = RecoveryLock(lock_path)

    if lock.acquire():
      try:
        logger.info('Starting worker recovery process.')
        return self._do_recover()
      finally:
        lock.release()
    else:
      logger.debug('Recovery lock held by another process. Skipping.')
      return []

  def _do_recover(self):
    if not self.storage:
      return []

    with self.storage.session_scope() as session:
      workers_to_restart = session.query(Worker).filter_by(status=WorkerStatus.RUNNING).all()
      to_process = [(w.worker_key, w.worker_type, w.parameters, w.pid) for w in workers_to_restart]

    restarted = []
    for key, w_type, params, pid in to_process:
      if not is_process_running(pid):
        logger.info(f'Recovering worker {key}...')
        success, _ = self.start_worker(w_type, key, params)
        if success:
          restarted.append(key)
    return restarted

  def dispose(self):
    for worker_key in list(self._active_processes.keys()):
      process = self._active_processes.get(worker_key)
      if process:
        try:
          if process.poll() is None:
            process.terminate()
            process.wait(timeout=2)
        except Exception:
          try:
            process.kill()
            process.wait()
          except Exception:
            pass
    self._active_processes.clear()
    if self.storage:
      self.storage.dispose()
