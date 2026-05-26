from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker

from .models import Base


class Storage:
  def __init__(self, db_path):
    # sqlite:///path/to/db
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
    Base.metadata.create_all(self.engine)

  def get_session(self):
    return self.Session()

  def dispose(self):
    self.engine.dispose()
