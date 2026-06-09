import logging
import psutil
import subprocess


logger = logging.getLogger('crazy_workers')


def get_running_process(pid):
  """Returns a psutil.Process object if the PID exists and is not a zombie."""
  if pid is None:
    return None
  try:
    proc = psutil.Process(pid)
    if proc.is_running() and proc.status() != psutil.STATUS_ZOMBIE:
      return proc
  except (psutil.NoSuchProcess, psutil.AccessDenied):
    pass
  return None


def is_process_running(pid):
  """Checks if a process is truly running. Very resilient."""
  try:
    return get_running_process(pid) is not None
  except (psutil.Error, OSError):
    return False


def terminate_process(pid, timeout=5, popen_process=None, exclude_pids=None):
  """Gracefully terminates a process and its non-managed children.

  Children whose PIDs appear in exclude_pids are left alive — they are
  independently managed workers that should outlive their parent.
  Any other child process (raw subprocesses, shell helpers, etc.) is
  terminated alongside the parent.
  """
  proc = get_running_process(pid)
  if not proc:
    return True

  # Build the full exclusion set: each managed PID and all its descendants.
  # This is necessary on platforms where a single logical worker spans more
  # than one OS process (e.g. the Python launcher on Windows spawns the
  # actual interpreter as a child).
  excluded: set[int] = set(exclude_pids or [])
  for mpid in list(excluded):
    try:
      for desc in psutil.Process(mpid).children(recursive=True):
        excluded.add(desc.pid)
    except (psutil.NoSuchProcess, psutil.AccessDenied):
      pass

  try:
    # Snapshot descendant PIDs before killing the parent; the list becomes
    # unavailable once the parent exits.
    try:
      children = [c for c in proc.children(recursive=True) if c.pid not in excluded]
    except (psutil.NoSuchProcess, psutil.AccessDenied):
      children = []

    proc.terminate()
    for child in children:
      try:
        child.terminate()
      except (psutil.NoSuchProcess, psutil.AccessDenied):
        pass

    try:
      if popen_process:
        popen_process.wait(timeout=timeout)
      else:
        proc.wait(timeout=timeout)
    except (psutil.TimeoutExpired, subprocess.TimeoutExpired):
      if popen_process:
        popen_process.kill()
        popen_process.wait()
      else:
        proc.kill()
      for child in children:
        try:
          if child.is_running():
            child.kill()
        except (psutil.NoSuchProcess, psutil.AccessDenied):
          pass

    return True
  except Exception as e:
    logger.error(f'Unexpected error terminating process {pid}: {e}')
    raise
