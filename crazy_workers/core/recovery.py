import logging
import os
import psutil


logger = logging.getLogger('crazy_workers')


class RecoveryLock:
  def __init__(self, path):
    self.path = path

  def acquire(self):
    try:
      fd = os.open(self.path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
      with os.fdopen(fd, 'w') as f:
        f.write(str(os.getpid()))
      return True
    except FileExistsError:
      return self._handle_existing_lock()

  def release(self):
    try:
      os.remove(self.path)
    except OSError:
      pass

  def _handle_existing_lock(self):
    try:
      with open(self.path, 'r') as f:
        old_pid_str = f.read().strip()

      if not old_pid_str:
        logger.warning('Found empty recovery lock. Breaking lock.')
        return self._break_and_reacquire()

      try:
        old_pid = int(old_pid_str)
      except ValueError:
        logger.warning(f'Found invalid recovery lock content: "{old_pid_str}". Breaking lock.')
        return self._break_and_reacquire()

      if not psutil.pid_exists(old_pid):
        logger.warning(f'Found stale recovery lock from dead PID {old_pid}. Breaking lock.')
        return self._break_and_reacquire()
    except Exception:
      pass
    return False

  def _break_and_reacquire(self):
    try:
      os.remove(self.path)
    except OSError:
      pass
    return self.acquire()
