import logging
import os
import psutil
import subprocess


logger = logging.getLogger('crazy_workers')

# Command-line flag used to tag a worker subprocess with its key. The same
# prefix is stripped by crazy_workers._bootstrap so the worker never sees it.
WORKER_KEY_FLAG = '--cw-key='


def worker_key_token(worker_key):
  """Returns the argv token that tags a subprocess as belonging to worker_key.

  Injected into the subprocess command line at spawn time so a worker's
  identity can later be confirmed by reading its command line — see
  is_worker_process.
  """
  return f'{WORKER_KEY_FLAG}{worker_key}'


def is_worker_process(pid, worker_key):
  """True only if pid is alive AND its command line carries worker_key's tag.

  This defeats PID reuse: a recycled PID now held by an unrelated process will
  not carry our identity token, so it is correctly reported as 'not our
  worker'. It relies on psutil.Process.cmdline(), which is readable for
  same-user processes on both Unix and Windows — unlike the process
  environment, which several platforms refuse to expose across processes.

  Any failure to read the command line (the process vanished, or belongs to
  another user) is treated as 'not our worker', the safe default for both
  recovery (restart it) and stop (do not signal an unknown PID).
  """
  proc = get_running_process(pid)
  if proc is None:
    return False
  try:
    cmdline = proc.cmdline()
  except (psutil.Error, OSError):
    return False
  return worker_key_token(worker_key) in cmdline


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


def resolve_system_pid(pid, worker_key=None):
  """Return the most-native PID visible for ``pid``.

  ``pid`` remains the control PID used by the current process namespace. On
  Linux, ``CRAZY_WORKERS_HOST_PROC`` can point at a read-only host procfs mount
  (for example /host/proc in Docker) so status can show the host PID. Without
  that mount, /proc exposes NSpid when PID namespaces are visible; its first
  value is the PID in the outermost namespace visible to this procfs mount. On
  Windows and ordinary Linux hosts this is just ``pid``.
  """
  if pid is None:
    return None
  if os.name != 'posix':
    return pid

  host_pid = _resolve_from_host_proc(pid, worker_key=worker_key)
  if host_pid is not None:
    return host_pid

  try:
    with open(f'/proc/{pid}/status', encoding='utf-8') as f:
      for line in f:
        if line.startswith('NSpid:'):
          values = [int(value) for value in line.split()[1:]]
          return values[0] if values else pid
  except (OSError, ValueError):
    return pid

  return pid


def _resolve_from_host_proc(pid, worker_key=None):
  host_proc = os.environ.get('CRAZY_WORKERS_HOST_PROC')
  if not host_proc:
    return None
  if not os.path.isdir(host_proc):
    return None

  for entry in os.listdir(host_proc):
    if not entry.isdigit():
      continue

    status_path = os.path.join(host_proc, entry, 'status')
    try:
      with open(status_path, encoding='utf-8') as f:
        nspid = _read_nspid(f)
    except (OSError, ValueError):
      continue

    if not nspid or nspid[-1] != pid:
      continue
    if worker_key and not _host_proc_cmdline_matches(host_proc, entry, worker_key):
      continue
    return nspid[0]

  return None


def _read_nspid(lines):
  for line in lines:
    if line.startswith('NSpid:'):
      return [int(value) for value in line.split()[1:]]
  return None


def _host_proc_cmdline_matches(host_proc, host_pid, worker_key):
  try:
    with open(os.path.join(host_proc, host_pid, 'cmdline'), 'rb') as f:
      raw = f.read()
  except OSError:
    return False
  parts = [part.decode(errors='ignore') for part in raw.split(b'\0') if part]
  return worker_key_token(worker_key) in parts


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
