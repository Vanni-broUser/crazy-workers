import psutil
import subprocess


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
  except Exception:
    return False


def terminate_process(pid, timeout=5, popen_process=None):
  """Gracefully terminates a process, falling back to kill if it takes too long."""
  proc = get_running_process(pid)
  if not proc:
    return True

  try:
    proc.terminate()

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
    return True
  except Exception:
    raise
