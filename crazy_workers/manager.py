import json
import logging
import os
import psutil
from sqlalchemy.exc import IntegrityError
import subprocess
import sys
import time

from .models import Worker, WorkerStatus
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
    if pid is None:
      return False
    try:
      return psutil.pid_exists(pid)
    except Exception:
      return False

  def start_worker(self, worker_type, worker_key=None, parameters=None, env=None):
    worker_key = worker_key or worker_type
    
    # Security: Prevent path traversal for both type and key
    for name, val in [('worker_type', worker_type), ('worker_key', worker_key)]:
      if '..' in val or os.path.isabs(val) or '/' in val or '\\' in val:
        logger.error(f'Invalid {name}: {val}. Potential path traversal attempt.')
        return False, f'Invalid {name}'

    parameters = parameters or {}
    session = self.storage.get_session()
    try:
      worker = session.query(Worker).filter_by(worker_key=worker_key).first()

      if worker and worker.status == WorkerStatus.RUNNING:
        if self._is_process_running(worker.pid):
          logger.info(f'Worker {worker_key} already running with PID {worker.pid}')
          return False, 'Worker already running'
        else:
          logger.warning(f'Worker {worker_key} found in RUNNING state but PID {worker.pid} is dead. Cleaning up.')
          worker.status = WorkerStatus.CRASHED
          session.commit()

      if not worker:
        worker = Worker(worker_key=worker_key, worker_type=worker_type, parameters=parameters)
        session.add(worker)
      else:
        worker.worker_type = worker_type
        worker.parameters = parameters
        worker.status = WorkerStatus.STARTING

      try:
        session.commit()
      except IntegrityError:
        session.rollback()
        logger.error(f'Concurrent start attempt for worker {worker_key}')
        return False, 'Worker state conflict (concurrent start)'

      worker_filename = f'{worker_type}.py'
      worker_path = os.path.join(self.workers_dir, worker_filename)
      if not os.path.exists(worker_path):
        logger.error(f'Worker file {worker_filename} not found in {self.workers_dir}')
        worker.status = WorkerStatus.STOPPED
        session.commit()
        return False, f'Worker file {worker_filename} not found'

      # Prepare environment
      child_env = os.environ.copy()
      if env:
        child_env.update(env)

      # Logging setup
      log_file_path = os.path.join(self.logs_dir, f'{worker_key}.log')
      try:
        log_file = open(log_file_path, 'a')
        stdout_dest = log_file
        stderr_dest = log_file
        logger.info(f'Worker {worker_key} logging to {log_file_path}')
      except Exception as e:
        logger.error(f'Failed to open log file for worker {worker_key}: {e}')
        stdout_dest = subprocess.DEVNULL
        stderr_dest = subprocess.DEVNULL
        log_file = None

      logger.info(f'Starting worker {worker_key} ({worker_type})')
      try:
        process = subprocess.Popen(
          [sys.executable, worker_path, json.dumps(parameters)],
          stdout=stdout_dest,
          stderr=stderr_dest,
          text=True,
          env=child_env,
        )

        # Small grace period to detect immediate crashes
        time.sleep(0.05)
        if process.poll() is not None:
          logger.error(f'Worker {worker_key} failed to start immediately (exit code: {process.returncode})')
          worker.status = WorkerStatus.CRASHED
          worker.pid = None
          session.commit()
          return False, 'Worker process failed to start'

        worker.pid = process.pid
        worker.status = WorkerStatus.RUNNING
        session.commit()

        # Track the process to manage its lifecycle and avoid ResourceWarnings
        self._active_processes[worker_key] = process
        logger.info(f'Worker {worker_key} started with PID {worker.pid}')
      finally:
        if log_file:
          log_file.close()

      return True, worker.to_dict()
    finally:
      session.close()

  def stop_worker(self, worker_key):
    session = self.storage.get_session()
    try:
      worker = session.query(Worker).filter_by(worker_key=worker_key).first()
      if not worker or worker.status != WorkerStatus.RUNNING:
        return False, 'Worker not found or not running'

      pid = worker.pid
      logger.info(f'Stopping worker {worker_key} (PID {pid})')

      # Use the tracked Popen object if available for cleaner cleanup
      process = self._active_processes.get(worker_key)

      try:
        if self._is_process_running(pid):
          proc = psutil.Process(pid)
          proc.terminate()
          try:
            if process:
              process.wait(timeout=5)
            else:
              proc.wait(timeout=5)
          except (psutil.TimeoutExpired, subprocess.TimeoutExpired):
            logger.warning(f'Worker {worker_key} (PID {pid}) did not terminate, killing it.')
            if process:
              process.kill()
              process.wait()
            else:
              proc.kill()

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

    # Try to acquire lock
    if self._acquire_recovery_lock(lock_path):
      try:
        logger.info('Starting worker recovery process.')
        return self._do_recover()
      finally:
        self._release_recovery_lock(lock_path)
    else:
      logger.debug('Recovery lock held by another process. Skipping.')
      return []

  def _acquire_recovery_lock(self, path):
    try:
      fd = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
      with os.fdopen(fd, 'w') as f:
        f.write(str(os.getpid()))
      return True
    except FileExistsError:
      # Check if lock is stale
      try:
        with open(path, 'r') as f:
          old_pid_str = f.read().strip()

        if not old_pid_str:
          logger.warning('Found empty recovery lock. Breaking lock.')
          try:
            os.remove(path)
          except OSError:
            pass
          return self._acquire_recovery_lock(path)

        try:
          old_pid = int(old_pid_str)
        except ValueError:
          logger.warning(f'Found invalid recovery lock content: "{old_pid_str}". Breaking lock.')
          try:
            os.remove(path)
          except OSError:
            pass
          return self._acquire_recovery_lock(path)

        if not psutil.pid_exists(old_pid):
          logger.warning(f'Found stale recovery lock from dead PID {old_pid}. Breaking lock.')
          try:
            os.remove(path)
          except OSError:
            pass
          return self._acquire_recovery_lock(path)
      except Exception:
        pass
      return False

  def _release_recovery_lock(self, path):
    try:
      os.remove(path)
    except OSError:
      pass

  def _do_recover(self):
    session = self.storage.get_session()
    try:
      workers_to_restart = session.query(Worker).filter_by(status=WorkerStatus.RUNNING).all()
      restarted = []
      to_process = [(w.worker_key, w.worker_type, w.parameters, w.pid) for w in workers_to_restart]
    finally:
      session.close()

    for key, w_type, params, pid in to_process:
      if not self._is_process_running(pid):
        logger.info(f'Recovering worker {key}...')
        success, _ = self.start_worker(w_type, key, params)
        if success:
          restarted.append(key)
    return restarted

  def dispose(self):
    # Ensure all tracked Popen objects are cleaned up to avoid ResourceWarnings
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
