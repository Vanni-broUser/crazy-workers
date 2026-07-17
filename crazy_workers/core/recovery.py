import logging
import os
import psutil


logger = logging.getLogger('crazy_workers')

# Tolerance (seconds) when comparing process create times: psutil may report
# slightly different values across queries on some platforms, and filesystem
# mtimes can be coarser than the clock. A real PID collision is minutes or
# days apart, never within a second.
_CREATE_TIME_TOLERANCE = 1.0


class RecoveryLock:
  """File lock that survives crashes but never outlives its owner.

  The lock stores ``pid:create_time`` of the owning process. A bare
  ``pid_exists`` check is not enough to decide the owner is still alive: PIDs
  are recycled, and in containers the check is systematically wrong — the lock
  file lives in the container's writable layer (which survives a restart)
  while the PID namespace starts over, so the old PID (typically 1) always
  "exists" in the new container and a plain PID check deadlocks the daemon
  forever. PID + create time identifies the owning process uniquely: same PID
  with a different create time is a collision, not an owner.
  """

  def __init__(self, path):
    self.path = path

  def acquire(self):
    try:
      fd = os.open(self.path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
      with os.fdopen(fd, 'w') as f:
        f.write(self._identity())
      return True
    except FileExistsError:
      return self._handle_existing_lock()

  def release(self):
    try:
      os.remove(self.path)
    except OSError:
      pass

  def _identity(self) -> str:
    pid = os.getpid()
    try:
      create_time = psutil.Process(pid).create_time()
    except psutil.Error:
      # Best effort: a PID-only lock still gets the legacy mtime heuristic.
      return str(pid)
    return f'{pid}:{create_time}'

  def _handle_existing_lock(self):
    try:
      with open(self.path, 'r') as f:
        content = f.read().strip()
    except OSError:
      return False

    if not content:
      logger.warning('Found empty recovery lock. Breaking lock.')
      return self._break_and_reacquire()

    pid_str, _, create_time_str = content.partition(':')
    try:
      old_pid = int(pid_str)
      old_create_time = float(create_time_str) if create_time_str else None
    except ValueError:
      logger.warning(f'Found invalid recovery lock content: "{content}". Breaking lock.')
      return self._break_and_reacquire()

    try:
      alive = psutil.pid_exists(old_pid)
    except OSError:
      return False

    if not alive:
      logger.warning(f'Found stale recovery lock from dead PID {old_pid}. Breaking lock.')
      return self._break_and_reacquire()

    if not self._same_process(old_pid, old_create_time):
      logger.warning(f'Found recovery lock from recycled PID {old_pid} (different process). Breaking lock.')
      return self._break_and_reacquire()

    return False

  def _same_process(self, old_pid: int, old_create_time: float | None) -> bool:
    """Whether the live process `old_pid` is the one that wrote the lock.

    With a stored create time the comparison is exact. For legacy PID-only
    locks we fall back to the file mtime: the writer necessarily existed
    before it wrote the lock, so a process created after the lock's mtime
    cannot be its author.
    """
    try:
      create_time = psutil.Process(old_pid).create_time()
    except psutil.NoSuchProcess:
      return False  # died between pid_exists and here: stale
    except psutil.Error:
      return True  # can't inspect it: be conservative, assume it's the owner

    if old_create_time is not None:
      return abs(create_time - old_create_time) <= _CREATE_TIME_TOLERANCE

    try:
      lock_mtime = os.path.getmtime(self.path)
    except OSError:
      return True
    return create_time <= lock_mtime + _CREATE_TIME_TOLERANCE

  def _break_and_reacquire(self):
    try:
      os.remove(self.path)
    except OSError:
      return False
    # Re-acquire once — if another process grabbed the lock in the meantime, give up.
    try:
      fd = os.open(self.path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
      with os.fdopen(fd, 'w') as f:
        f.write(self._identity())
      return True
    except FileExistsError:
      return False
