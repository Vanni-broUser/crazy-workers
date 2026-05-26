import json
import logging
import os
import subprocess
import sys
import time
from sqlalchemy.exc import IntegrityError

from .models import Worker, WorkerStatus
from .process import is_process_running, terminate_process
from .recovery import RecoveryLock
from .storage import Storage

logger = logging.getLogger('crazy_workers')


class WorkerManager:
  def __init__(self, workers_dir='workers'):
    self.workers_dir = workers_dir
    self.service_dir = os.path.join(workers_dir, '.service')
    os.makedirs(self.service_dir, exist_ok=True)

    self.db_path = os.path.join(self.service_dir, 'workers.db')
    self.storage = Storage(self.db_path)
    self.logs_dir = os.path.join(self.service_dir, 'logs')
    os.makedirs(self.logs_dir, exist_ok=True)

    self._active_processes = {}  # worker_key -> Popen object

  def _is_process_running(self, pid):
    """Internal wrapper for process check."""
    return is_process_running(pid)

  def start_worker(self, worker_type, worker_key=None, parameters=None, env=None):
    worker_key = worker_key or worker_type

    if not self._validate_inputs(worker_type, worker_key):
      return False, 'Invalid worker_type or worker_key'

    parameters = parameters or {}
    session = self.storage.get_session()
    try:
      worker = session.query(Worker).filter_by(worker_key=worker_key).first()

      if self._check_already_running(worker, session):
        return False, 'Worker already running'

      worker = self._prepare_worker_record(worker, worker_type, worker_key, parameters, session)
      if not worker:
        return False, 'Worker state conflict (concurrent start)'

      worker_path = self._get_worker_script_path(worker_type)
      if not worker_path:
        worker.status = WorkerStatus.STOPPED
        session.commit()
        return False, f'Worker file {worker_type}.py not found'

      success, result = self._spawn_worker_process(worker, worker_path, parameters, env, session)
      return success, result
    finally:
      session.close()

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
    session = self.storage.get_session()
    try:
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
        session.commit()
        logger.info(f'Worker {worker_key} stopped.')
        return True, 'Worker stopped'
      except Exception as e:
        logger.error(f'Error stopping worker {worker_key}: {e}')
        return False, str(e)
    finally:
      session.close()

  def list_workers(self):
    session = self.storage.get_session()
    try:
      workers = session.query(Worker).all()
      return [w.to_dict() for w in workers]
    finally:
      session.close()

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
    session = self.storage.get_session()
    try:
      workers_to_restart = session.query(Worker).filter_by(status=WorkerStatus.RUNNING).all()
      to_process = [(w.worker_key, w.worker_type, w.parameters, w.pid) for w in workers_to_restart]
    finally:
      session.close()

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
    self.storage.dispose()
