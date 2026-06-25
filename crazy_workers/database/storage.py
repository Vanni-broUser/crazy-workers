import logging
from contextlib import contextmanager
from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker

from .schema import Base


logger = logging.getLogger('crazy_workers')


class Storage:
  """Persistence for worker state.

  Three ways to point it at a database, in priority order:

  - ``engine``: reuse an existing SQLAlchemy engine (e.g. the host backend's),
    so crazy_workers' tables are created **inside the project's own database**.
    A shared engine is NOT disposed by crazy_workers — its owner manages it.
  - ``db_url``: any SQLAlchemy URL (e.g. ``postgresql://user:pass@host/db``).
  - ``db_path``: a SQLite file path — the default, self-contained mode.

  ``create_tables`` controls whether crazy_workers creates its own tables on
  init. Leave it ``True`` for the self-contained modes. Set it ``False`` when
  the host owns the schema (e.g. it manages crazy_workers' ``workers`` table
  through its own migrations): crazy_workers then issues no DDL, and the caller
  is responsible for the table existing before the storage is used.
  """

  def __init__(self, db_path=None, *, db_url=None, engine=None, create_tables=True):
    self.db_path = db_path

    if engine is not None:
      self.engine = engine
      self._owns_engine = False
    else:
      url = db_url if db_url else f'sqlite:///{db_path}'
      connect_args = {'timeout': 30} if url.startswith('sqlite') else {}
      self.engine = create_engine(url, connect_args=connect_args)
      self._owns_engine = True

    if self.engine.dialect.name == 'sqlite':
      self._install_sqlite_tuning()

    self.Session = sessionmaker(bind=self.engine)
    if create_tables:
      self._ensure_tables()

  def _install_sqlite_tuning(self):
    @event.listens_for(self.engine, 'connect')
    def set_sqlite_pragma(dbapi_connection, connection_record):
      cursor = dbapi_connection.cursor()
      cursor.execute('PRAGMA journal_mode=WAL')
      cursor.close()

    @event.listens_for(self.engine, 'begin')
    def do_begin(conn):
      conn.exec_driver_sql('BEGIN IMMEDIATE')

  def _ensure_tables(self):
    """Create crazy_workers' own tables if missing (leaves other tables alone)."""
    Base.metadata.create_all(self.engine)

  def get_session(self):
    return self.Session()

  @contextmanager
  def session_scope(self):
    """Provides a transactional scope around a series of operations."""
    session = self.get_session()
    try:
      yield session
      session.commit()
    except Exception:
      session.rollback()
      raise
    finally:
      session.close()

  def dispose(self):
    # A shared engine belongs to its owner; only dispose one we created.
    if self._owns_engine:
      self.engine.dispose()
