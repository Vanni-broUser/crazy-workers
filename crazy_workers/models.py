from sqlalchemy import Column, Integer, String, JSON, Enum, DateTime, func
from sqlalchemy.orm import DeclarativeBase
import enum


class WorkerStatus(enum.Enum):
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
  created_at = Column(DateTime, server_default=func.now())
  updated_at = Column(DateTime, onupdate=func.now())

  def to_dict(self):
    return {
      'worker_key': self.worker_key,
      'worker_type': self.worker_type,
      'parameters': self.parameters,
      'pid': self.pid,
      'status': self.status.value,
    }
