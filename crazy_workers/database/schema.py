import enum
from datetime import datetime
from sqlalchemy import JSON, Column, DateTime, Enum, Integer, String, func
from sqlalchemy.orm import DeclarativeBase


class WorkerStatus(enum.Enum):
  """Observed status of a worker, owned by whoever runs the processes.

  In the reconciler model this is daemon-owned; in embedded mode the
  WorkerManager writes it directly.
  """

  NEVER_STARTED = 'NEVER_STARTED'
  STARTING = 'STARTING'
  RUNNING = 'RUNNING'
  STOPPED = 'STOPPED'
  CRASHED = 'CRASHED'


class DesiredStatus(enum.Enum):
  """What a client wants a worker to be doing. Client-owned.

  Clients (HTTP API, CLI, scripts) only ever write this; the daemon reconciles
  the observed ``status`` toward it.
  """

  RUNNING = 'RUNNING'
  STOPPED = 'STOPPED'


class Base(DeclarativeBase):
  pass


class Worker(Base):
  __tablename__ = 'workers'

  id = Column(Integer, primary_key=True)
  worker_key = Column(String(255), unique=True, nullable=False)
  worker_type = Column(String(255), nullable=False)  # Name of the .py file
  parameters = Column(JSON, nullable=False, default={})

  # Desired state — written by clients (control plane).
  desired_status = Column(Enum(DesiredStatus), nullable=False, default=DesiredStatus.STOPPED)

  # Observed state — written by whoever owns the processes (the daemon, or the
  # WorkerManager in embedded mode).
  pid = Column(Integer, nullable=True)
  status = Column(Enum(WorkerStatus), default=WorkerStatus.STOPPED)
  # Crash backoff bookkeeping: restart_count grows on each failed/crashed spawn
  # and resets on a successful start; last_exit_at timestamps the latest death.
  restart_count = Column(Integer, nullable=False, default=0)
  last_exit_at = Column(DateTime, nullable=True)
  last_started_at: datetime = Column(DateTime, nullable=True)
  last_stopped_at: datetime = Column(DateTime, nullable=True)
  created_at = Column(DateTime, server_default=func.now())
  updated_at = Column(DateTime, onupdate=func.now())

  def to_dict(self):
    return {
      'worker_key': self.worker_key,
      'worker_type': self.worker_type,
      'parameters': self.parameters,
      'desired_status': self.desired_status.value if self.desired_status else None,
      'pid': self.pid,
      'status': self.status.value,
      'restart_count': self.restart_count,
      'last_exit_at': self.last_exit_at.isoformat() if self.last_exit_at else None,
      'last_started_at': self.last_started_at.isoformat() if self.last_started_at else None,
      'last_stopped_at': self.last_stopped_at.isoformat() if self.last_stopped_at else None,
    }
