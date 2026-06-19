import hashlib
import os
import subprocess
import sys
from abc import ABC, abstractmethod
from dataclasses import dataclass


class BootError(Exception):
  """Raised when installing or inspecting the boot-restore hook fails."""


@dataclass
class BootState:
  """Snapshot of the per-user boot-restore hook for one workers directory."""

  supported: bool
  installed: bool
  mechanism: str
  at_boot: bool = False
  detail: str = ''


def dir_token(workers_dir):
  """Stable, filesystem-safe identifier for a workers directory.

  Used to name the per-directory unit/task so independent installations on the
  same machine never collide.
  """
  abs_dir = os.path.abspath(workers_dir)
  digest = hashlib.sha1(abs_dir.encode('utf-8')).hexdigest()[:10]
  base = os.path.basename(abs_dir.rstrip('/\\')) or 'workers'
  safe = ''.join(c if c.isalnum() else '-' for c in base).strip('-')[:24] or 'workers'
  return f'{safe}-{digest}'


def restore_command(workers_dir):
  """Argv the boot hook executes to restore workers for this directory.

  Runs the internal package entrypoint with the current interpreter, so it does
  not depend on the console script being on PATH — which it usually is not
  inside a systemd unit or a Windows scheduled task.
  """
  return [sys.executable, '-m', 'crazy_workers.boot', '--workers-dir', os.path.abspath(workers_dir)]


def run_command(cmd, env=None):
  """Execute a system command, returning (returncode, stdout, stderr).

  A missing executable is reported as a non-zero result rather than raising, so
  callers can degrade gracefully when the init system is absent.
  """
  run_env = None
  if env:
    run_env = os.environ.copy()
    run_env.update(env)
  try:
    proc = subprocess.run(cmd, capture_output=True, text=True, env=run_env, check=False)
    return proc.returncode, proc.stdout, proc.stderr
  except FileNotFoundError as exc:
    return 127, '', str(exc)


def atomic_write(path, content):
  """Write `content` to `path` atomically via a temp file and os.replace."""
  tmp = f'{path}.tmp'
  with open(tmp, 'w', encoding='utf-8') as handle:
    handle.write(content)
  os.replace(tmp, path)


class BootProvider(ABC):
  """A platform-specific way to install and inspect the boot-restore hook."""

  mechanism = 'unsupported'

  @abstractmethod
  def install(self, workers_dir):
    """Idempotently install the per-user hook. Raise BootError on failure."""

  @abstractmethod
  def state(self, workers_dir):
    """Return a BootState describing the hook for workers_dir."""
