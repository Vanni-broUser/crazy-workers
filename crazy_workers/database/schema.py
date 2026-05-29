import enum
from datetime import datetime
from sqlalchemy import JSON, Column, DateTime, Enum, Integer, String, func
from sqlalchemy.orm import DeclarativeBase


class WorkerStatus(enum.Enum):
  NEVER_STARTED = 'NEVER_STARTED'
  STARTING = 'STARTING'
  RUNNING = 'RUNNING'
  STOPPED = 'STOPPED'
  CRASHED = 'CRASHED'


class Base(DeclarativeBase):
  pass


class Worker(Base):
  __tablename__ = 'workers'

  id = Column(Integer, primary_key=True)
  worker_key = Column(String(255), unique=True, nullable=False)
  worker_type = Column(String(255), nullable=False)  # Name of the .py file
  parameters = Column(JSON, nullable=False, default={})
  pid = Column(Integer, nullable=True)
  status = Column(Enum(WorkerStatus), default=WorkerStatus.STOPPED)
  last_started_at: datetime = Column(DateTime, nullable=True)
  last_stopped_at: datetime = Column(DateTime, nullable=True)
  created_at = Column(DateTime, server_default=func.now())
  updated_at = Column(DateTime, onupdate=func.now())

  def to_dict(self):
    return {
      'worker_key': self.worker_key,
      'worker_type': self.worker_type,
      'parameters': self.parameters,
      'pid': self.pid,
      'status': self.status.value,
      'last_started_at': self.last_started_at.isoformat() if self.last_started_at else None,
      'last_stopped_at': self.last_stopped_at.isoformat() if self.last_stopped_at else None,
    }
