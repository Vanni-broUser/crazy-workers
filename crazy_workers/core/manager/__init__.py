import logging
import os

from ...database.storage import Storage
from ..backend import SubprocessBackend
from ..recovery import RecoveryLock
from .lister import list_workers
from .recoverer import recover_workers
from .starter import start_worker
from .stopper import stop_worker


logger = logging.getLogger('crazy_workers')


class WorkerManager:
  def __init__(
    self,
    workers_dir='workers',
    create_dir=True,
    backend=None,
    auto_boot=False,
    boot_provider=None,
    db_url=None,
    engine=None,
    worker_env=None,
    auto_recover=True,
    create_tables=True,
  ):
    self.workers_dir = workers_dir
    self._validate_workers_dir(create_dir)

    self.service_dir = os.path.join(self.workers_dir, '.service')
    self.logs_dir = os.path.join(self.service_dir, 'logs')
    self.db_path = os.path.join(self.service_dir, 'workers.db')

    self._initialize_storage(create_dir, db_url, engine, create_tables)
    # The backend is the only component that touches OS processes. The default
    # spawns real subprocesses; tests can swap in a fake one (see for_testing).
    self.backend = backend or SubprocessBackend()
    # Opt-in legacy behaviour: when True, starting a worker transparently
    # installs the per-user OS boot-restore hook (see crazy_workers.boot). The
    # default is now False — in the reconciler model, surviving a reboot is the
    # deployment's job (a systemd unit / container that runs the daemon), not a
    # per-worker hook. boot_provider is an injection seam for tests; None lets
    # the platform default be auto-detected.
    self.auto_boot = auto_boot
    self._boot_provider = boot_provider
    # Environment variables injected into every spawned worker — e.g. the host
    # backend's DATABASE_URL, so a worker can open its own connection to it.
    self.worker_env = worker_env or {}
    self.auto_recover = auto_recover
    self._active_processes = {}  # worker_key -> WorkerHandle

    # Recovery on construction: when a host backend (re)starts and builds its
    # manager, any worker left RUNNING with a dead PID is restored — no explicit
    # call needed. The CLI and the boot entrypoint disable this.
    if self.auto_recover:
      self.recover_workers()

  @classmethod
  def for_testing(cls, workers_dir='workers', mode='fake', create_dir=True):
    """Build a manager wired to a test backend instead of real OS processes.

    The state machine (SQLite storage, recovery, validation) stays real and
    runs in-process; only process spawning/termination is faked. The chosen
    backend is also exposed as `manager.test` for assertions and control
    (e.g. ``manager.test.started_types``, ``manager.test.crash(key)``).

    mode='fake' records orchestration decisions without launching anything.
    """
    from ...testing import make_test_backend

    backend = make_test_backend(mode)
    manager = cls(workers_dir, create_dir=create_dir, backend=backend, auto_boot=False, auto_recover=False)
    manager.test = backend
    return manager

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

  def _initialize_storage(self, create_dir, db_url, engine, create_tables):
    """Sets up service directories and storage if allowed or if they already exist."""
    if create_dir:
      os.makedirs(self.service_dir, exist_ok=True)
      os.makedirs(self.logs_dir, exist_ok=True)

    if engine is not None or db_url is not None:
      # External/shared database (e.g. the host backend's). crazy_workers' tables
      # are created there unless the host owns the schema (create_tables=False);
      # the local .service dir is still used for logs, the recovery lock and the
      # boot marker.
      self.storage = Storage(db_url=db_url, engine=engine, create_tables=create_tables)
    elif create_dir or os.path.exists(self.db_path):
      self.storage = Storage(self.db_path, create_tables=create_tables)
    else:
      self.storage = None

  def start_worker(self, worker_type, worker_key=None, parameters=None, env=None):
    return start_worker(self, worker_type, worker_key, parameters, env)

  def stop_worker(self, worker_key):
    return stop_worker(self, worker_key)

  def list_workers(self):
    return list_workers(self)

  def recover_workers(self):
    if not os.path.exists(self.service_dir):
      return []

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
