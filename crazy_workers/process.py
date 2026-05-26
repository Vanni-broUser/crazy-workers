import psutil
import subprocess


def is_process_running(pid):
  if pid is None:
    return False
  try:
    return psutil.pid_exists(pid)
  except Exception:
    return False


def terminate_process(pid, timeout=5, popen_process=None):
  if not is_process_running(pid):
    return True

  try:
    proc = psutil.Process(pid)
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
