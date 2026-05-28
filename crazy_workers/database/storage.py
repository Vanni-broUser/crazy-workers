import logging
from contextlib import contextmanager
from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker

from .schema import Base

logger = logging.getLogger('crazy_workers')


class Storage:
  def __init__(self, db_path):
    # sqlite:///path/to/db
    self.db_path = db_path
    self.engine = create_engine(f'sqlite:///{db_path}', connect_args={'timeout': 30})

    @event.listens_for(self.engine, 'connect')
    def set_sqlite_pragma(dbapi_connection, connection_record):
      cursor = dbapi_connection.cursor()
      cursor.execute('PRAGMA journal_mode=WAL')
      cursor.close()

    @event.listens_for(self.engine, 'begin')
    def do_begin(conn):
      conn.exec_driver_sql('BEGIN IMMEDIATE')

    self.Session = sessionmaker(bind=self.engine)
    self._ensure_tables()

  def _ensure_tables(self):
    """Initializes the database schema."""
    self._create_tables()

  def _create_tables(self):
    logger.info(f'Creating tables for database at {self.db_path}')
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
    self.engine.dispose()
