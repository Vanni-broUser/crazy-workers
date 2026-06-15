"""Test backends for consumer projects.

A FakeBackend lets a project that uses crazy_workers exercise its orchestration
logic — pairing of related workers, recovery, stop semantics — without spawning
a single OS process. The worker state machine (SQLite storage, recovery,
validation) still runs for real; only the process boundary is faked.
"""

from ..core.backend import ProcessBackend, WorkerHandle


class FakeBackend(ProcessBackend):
  """A ProcessBackend that records spawns instead of launching processes.

  Beyond the ProcessBackend interface it exposes a small assertion/control API,
  reached by consumers via ``WorkerManager.for_testing(...).test``:

      manager.test.started_types     -> ['register', 'renamer']
      manager.test.is_running('1')   -> True
      manager.test.crash('1')        -> simulate an unexpected death
      manager.test.start_count('1')  -> how many times key was (re)started
  """

  def __init__(self):
    self._pid_seq = 1000
    self.spawns = []  # chronological list of dicts: worker_key, worker_type, parameters, env, pid
    self._alive_pids = set()  # pids currently "running"
    self._pid_to_key = {}  # pid -> worker_key (for PID-reuse-safe liveness)
    self._current_pid = {}  # worker_key -> its latest pid
    self._start_count = {}  # worker_key -> number of spawns

  # --- ProcessBackend interface ---------------------------------------------

  def spawn(self, *, worker_key, worker_type, worker_path, parameters, env, log_path):
    self._pid_seq += 1
    pid = self._pid_seq

    self.spawns.append(
      {'worker_key': worker_key, 'worker_type': worker_type, 'parameters': parameters, 'env': env, 'pid': pid}
    )
    self._alive_pids.add(pid)
    self._pid_to_key[pid] = worker_key
    self._current_pid[worker_key] = pid
    self._start_count[worker_key] = self._start_count.get(worker_key, 0) + 1
    return WorkerHandle(pid)

  def is_alive(self, *, pid, worker_key):
    return pid in self._alive_pids and self._pid_to_key.get(pid) == worker_key

  def terminate(self, *, pid, worker_key, handle=None, exclude_pids=None):
    self._alive_pids.discard(pid)

  # --- assertion / control API ----------------------------------------------

  @property
  def started_keys(self):
    """worker_key of every spawn, in order (a restart appears twice)."""
    return [s['worker_key'] for s in self.spawns]

  @property
  def started_types(self):
    """worker_type of every spawn, in order."""
    return [s['worker_type'] for s in self.spawns]

  @property
  def running_keys(self):
    """worker_key of every worker whose latest process is still alive."""
    return [key for key, pid in self._current_pid.items() if pid in self._alive_pids]

  def is_running(self, worker_key):
    pid = self._current_pid.get(worker_key)
    return pid is not None and pid in self._alive_pids

  def start_count(self, worker_key):
    return self._start_count.get(worker_key, 0)

  def parameters_for(self, worker_key):
    """Parameters of the most recent spawn for worker_key, or None."""
    for spawn in reversed(self.spawns):
      if spawn['worker_key'] == worker_key:
        return spawn['parameters']
    return None

  def crash(self, worker_key):
    """Simulate the worker's process dying unexpectedly (without a stop)."""
    pid = self._current_pid.get(worker_key)
    if pid is not None:
      self._alive_pids.discard(pid)
