import json
import logging
import os
import re
import subprocess
import sys
from sqlalchemy import func
from sqlalchemy.exc import IntegrityError

from ...database.schema import Worker, WorkerStatus
from ..engine import is_worker_process, worker_key_token


logger = logging.getLogger('crazy_workers')

# Worker types and keys become filesystem paths (the <type>.py script and the
# <key>.log file). Restrict them to a safe identifier charset rather than trying
# to blocklist every dangerous sequence — a blocklist missed, for example,
# Windows drive-relative names like 'c:evil', which os.path.join treats as
# absolute and silently escapes the target directory.
_SAFE_NAME = re.compile(r'[A-Za-z0-9_-]+')


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
    if not isinstance(val, str) or not _SAFE_NAME.fullmatch(val):
      logger.error(f'Invalid {name}: {val!r}. Only letters, digits, underscores and hyphens are allowed.')
      return False
  return True


def _check_already_running(manager, worker, session):
  if worker and worker.status == WorkerStatus.RUNNING:
    if is_worker_process(worker.pid, worker.worker_key):
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

  # Defence in depth: confirm the resolved path stays inside workers_dir, even
  # if the name validation is ever loosened or workers_dir contains symlinks.
  workers_root = os.path.realpath(manager.workers_dir)
  resolved = os.path.realpath(worker_path)
  try:
    inside = os.path.commonpath([workers_root, resolved]) == workers_root
  except ValueError:
    # Different drives on Windows → definitely outside workers_dir.
    inside = False
  if not inside:
    logger.error(f'Resolved worker path {resolved} escapes workers directory {workers_root}')
    return None

  if not os.path.exists(worker_path):
    logger.error(f'Worker file {worker_filename} not found in {manager.workers_dir}')
    return None
  return worker_path


def _spawn_worker_process(manager, worker, worker_path, parameters, env, session):
  child_env = os.environ.copy()
  if env:
    child_env.update(env)

  log_file_path = os.path.join(manager.logs_dir, f'{worker.worker_key}.log')
  try:
    log_fh = open(log_file_path, 'a')
    logger.info(f'Worker {worker.worker_key} logging to {log_file_path}')
  except Exception as e:
    logger.error(f'Failed to open log file for worker {worker.worker_key}: {e}')
    log_fh = None

  # log_fh ownership is transferred to Popen; do NOT close it here.
  stdout_dest = log_fh if log_fh else subprocess.DEVNULL
  stderr_dest = log_fh if log_fh else subprocess.DEVNULL

  process = subprocess.Popen(
    [
      sys.executable,
      '-u',
      '-m',
      'crazy_workers._bootstrap',
      worker_key_token(worker.worker_key),
      worker_path,
      json.dumps(parameters),
    ],
    stdout=stdout_dest,
    stderr=stderr_dest,
    text=True,
    env=child_env,
  )

  # Close our copy of the handle — Popen duplicated it via os.dup2 internally.
  if log_fh:
    log_fh.close()

  try:
    process.wait(timeout=0.05)
    # If we reach here, it means the process exited immediately
    logger.error(f'Worker {worker.worker_key} failed to start immediately (exit code: {process.returncode})')
    worker.status = WorkerStatus.CRASHED
    worker.pid = None
    session.commit()
    return False, 'Worker process failed to start'
  except subprocess.TimeoutExpired:
    # This is the expected case: the process is still running after the timeout
    pass

  worker.pid = process.pid
  worker.status = WorkerStatus.RUNNING
  worker.last_started_at = func.now()
  session.commit()

  manager._active_processes[worker.worker_key] = process
  logger.info(f'Worker {worker.worker_key} started with PID {worker.pid}')
  return True, worker.to_dict()
