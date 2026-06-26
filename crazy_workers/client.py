"""Control-plane client: writes desired state only, never spawns processes.

Used by anything that is NOT the daemon (HTTP API, CLI, scripts). It shares the
daemon's database; the daemon reconciles desired -> actual. A client touches the
``workers`` table and nothing else — no OS processes, no boot hooks, no recovery.

Three ways to point it at a database, mirroring :class:`Storage`:

- ``engine``: reuse an existing SQLAlchemy engine (e.g. the host backend's).
- ``db_url``: any SQLAlchemy URL.
- neither: the caller must pass one — unlike WorkerManager, the client has no
  workers_dir and therefore no implicit SQLite location.
"""

from .database.schema import DesiredStatus, Worker
from .database.storage import Storage


class WorkerClient:
  def __init__(self, db_url=None, engine=None, create_tables=False):
    self.storage = Storage(db_url=db_url, engine=engine, create_tables=create_tables)

  def request_start(self, worker_type, worker_key=None, parameters=None):
    """Declare that ``worker_key`` should be RUNNING (upserting its spec).

    Returns the resolved worker_key. The worker is not started here; the daemon
    notices the desired state and starts it.
    """
    worker_key = worker_key or worker_type
    with self.storage.session_scope() as session:
      worker = session.query(Worker).filter_by(worker_key=worker_key).first()
      if not worker:
        worker = Worker(worker_key=worker_key, worker_type=worker_type)
        session.add(worker)
      worker.worker_type = worker_type
      worker.parameters = parameters or {}
      worker.desired_status = DesiredStatus.RUNNING
    return worker_key

  def request_stop(self, worker_key):
    """Declare that ``worker_key`` should be STOPPED.

    Returns False if no such worker exists. The actual stop (and last_stopped_at)
    is performed by the daemon when it reconciles.
    """
    with self.storage.session_scope() as session:
      worker = session.query(Worker).filter_by(worker_key=worker_key).first()
      if not worker:
        return False
      worker.desired_status = DesiredStatus.STOPPED
    return True

  def list(self):
    with self.storage.session_scope() as session:
      return [w.to_dict() for w in session.query(Worker).all()]

  def get(self, worker_key):
    with self.storage.session_scope() as session:
      worker = session.query(Worker).filter_by(worker_key=worker_key).first()
      return worker.to_dict() if worker else None

  def dispose(self):
    self.storage.dispose()

  def __enter__(self):
    return self

  def __exit__(self, exc_type, exc_val, exc_tb):
    self.dispose()
