import getpass
import os

from .base import BootError, BootProvider, BootState, atomic_write, dir_token, restore_command, run_command


_UNIT_TEMPLATE = """[Unit]
Description=Crazy Workers boot restore for {workers_dir}
After=default.target

[Service]
Type=oneshot
ExecStart={exec_start}

[Install]
WantedBy=default.target
"""


class SystemdUserProvider(BootProvider):
  """Boot-restore via a per-user systemd unit (Linux).

  The unit runs at login by default; it runs at true machine boot only when
  lingering is enabled for the user (a one-time, privileged action). `state`
  reports which of the two applies.
  """

  mechanism = 'systemd-user'

  def __init__(self, unit_dir=None, runner=run_command, uid=None, user=None):
    self._unit_dir = unit_dir or os.path.expanduser('~/.config/systemd/user')
    self._run = runner
    self._uid = uid if uid is not None else _current_uid()
    self._user = user or _current_user()

  def install(self, workers_dir):
    os.makedirs(self._unit_dir, exist_ok=True)
    unit_name = self._unit_name(workers_dir)
    unit_path = os.path.join(self._unit_dir, unit_name)
    exec_start = _exec_start(restore_command(workers_dir))
    content = _UNIT_TEMPLATE.format(workers_dir=os.path.abspath(workers_dir), exec_start=exec_start)
    atomic_write(unit_path, content)

    env = self._systemctl_env()
    code, _, err = self._run(['systemctl', '--user', 'daemon-reload'], env=env)
    if code != 0:
      raise BootError(f'systemctl --user daemon-reload failed: {err.strip()}')
    code, _, err = self._run(['systemctl', '--user', 'enable', unit_name], env=env)
    if code != 0:
      raise BootError(f'systemctl --user enable failed: {err.strip()}')

    # Best-effort: without lingering the unit only runs at login. Enabling it
    # needs privileges we may not have, so a failure here is intentionally
    # non-fatal — `state` will report that it runs at login instead of at boot.
    self._run(['loginctl', 'enable-linger', self._user])

  def state(self, workers_dir):
    unit_path = os.path.join(self._unit_dir, self._unit_name(workers_dir))
    installed = os.path.exists(unit_path)
    at_boot = False
    detail = 'runs at user login'
    if installed and self._linger_enabled():
      at_boot = True
      detail = 'runs at boot (linger enabled)'
    return BootState(supported=True, installed=installed, mechanism=self.mechanism, at_boot=at_boot, detail=detail)

  def _unit_name(self, workers_dir):
    return f'crazy-workers-restore-{dir_token(workers_dir)}.service'

  def _systemctl_env(self):
    # `systemctl --user` needs the user bus; point it at the user runtime dir so
    # it also works from non-session callers (a worker started by a script that
    # has no login environment).
    return {'XDG_RUNTIME_DIR': f'/run/user/{self._uid}'}

  def _linger_enabled(self):
    code, out, _ = self._run(['loginctl', 'show-user', self._user, '--property=Linger'])
    return code == 0 and 'Linger=yes' in out


def _exec_start(argv):
  return ' '.join(f'"{arg}"' if ' ' in arg else arg for arg in argv)


def _current_uid():
  getter = getattr(os, 'getuid', None)
  return getter() if getter else 0


def _current_user():
  try:
    return getpass.getuser()
  except (OSError, KeyError):
    return os.environ.get('USER') or 'root'
