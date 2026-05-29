import json
import logging
import os
import subprocess
import sys
import time
from sqlalchemy import func
from sqlalchemy.exc import IntegrityError

from ...database.schema import Worker, WorkerStatus


logger = logging.getLogger('crazy_workers')


def start_worker(manager, worker_type, worker_key=None, parameters=None, env=None):
  if not manager.storage:
    return False, 'System not initialized (database missing)'

  worker_key = worker_key or worker_type
  if not _validate_inputs(worker_type, worker_key):
    return False, 'Invalid worker_type or worker_key'

  parameters = parameters or {}
  with manager.storage.session_scope() as session:
    worker = session.query(Worker).filter_by(worker_key=worker_key).first()

    if _check_already_running(manager, worker, session):
      return False, 'Worker already running'

    worker = _prepare_worker_record(worker, worker_type, worker_key, parameters, session)
    if not worker:
      return False, 'Worker state conflict (concurrent start)'

    worker_path = _get_worker_script_path(manager, worker_type)
    if not worker_path:
      worker.status = WorkerStatus.STOPPED
      return False, f'Worker file {worker_type}.py not found'

    return _spawn_worker_process(manager, worker, worker_path, parameters, env, session)


def _validate_inputs(worker_type, worker_key):
  for name, val in [('worker_type', worker_type), ('worker_key', worker_key)]:
    if '..' in val or os.path.isabs(val) or '/' in val or '\\' in val:
      logger.error(f'Invalid {name}: {val}. Potential path traversal attempt.')
      return False
  return True


def _check_already_running(manager, worker, session):
  if worker and worker.status == WorkerStatus.RUNNING:
    if manager._is_process_running(worker.pid):
      logger.info(f'Worker {worker.worker_key} already running with PID {worker.pid}')
      return True
    else:
      logger.warning(f'Worker {worker.worker_key} found in RUNNING state but PID {worker.pid} is dead. Cleaning up.')
      worker.status = WorkerStatus.CRASHED
      session.commit()
  return False


def _prepare_worker_record(worker, worker_type, worker_key, parameters, session):
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


def _get_worker_script_path(manager, worker_type):
  worker_filename = f'{worker_type}.py'
  worker_path = os.path.join(manager.workers_dir, worker_filename)
  if not os.path.exists(worker_path):
    logger.error(f'Worker file {worker_filename} not found in {manager.workers_dir}')
    return None
  return worker_path


def _spawn_worker_process(manager, worker, worker_path, parameters, env, session):
  child_env = os.environ.copy()
  if env:
    child_env.update(env)

  log_file_path = os.path.join(manager.logs_dir, f'{worker.worker_key}.log')
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
    worker.last_started_at = func.now()
    session.commit()

    manager._active_processes[worker.worker_key] = process
    logger.info(f'Worker {worker.worker_key} started with PID {worker.pid}')
    return True, worker.to_dict()
  finally:
    if log_file:
      log_file.close()
