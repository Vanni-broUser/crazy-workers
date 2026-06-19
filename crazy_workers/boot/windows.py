import os

from .base import BootError, BootProvider, BootState, dir_token, restore_command, run_command


class WindowsTaskProvider(BootProvider):
  """Boot-restore via a per-user Scheduled Task triggered at logon (Windows).

  A user task cannot run before logon without administrator rights, so it fires
  at the next user logon. `state` reports this.
  """

  mechanism = 'windows-task'

  def __init__(self, runner=run_command):
    self._run = runner

  def install(self, workers_dir):
    task = self._task_name(workers_dir)
    command = _task_command(restore_command(workers_dir))
    code, _, err = self._run(['schtasks', '/Create', '/TN', task, '/TR', command, '/SC', 'ONLOGON', '/F'])
    if code != 0:
      raise BootError(f'schtasks /Create failed: {err.strip()}')

  def state(self, workers_dir):
    task = self._task_name(workers_dir)
    code, _, _ = self._run(['schtasks', '/Query', '/TN', task])
    return BootState(
      supported=True,
      installed=code == 0,
      mechanism=self.mechanism,
      at_boot=False,
      detail='runs at user logon',
    )

  def _task_name(self, workers_dir):
    return f'CrazyWorkers\\restore-{dir_token(workers_dir)}'


def _task_command(argv):
  argv = list(argv)
  # Prefer pythonw.exe so the restore runs without flashing a console window.
  if argv and argv[0].lower().endswith('python.exe'):
    pythonw = argv[0][: -len('python.exe')] + 'pythonw.exe'
    if os.path.exists(pythonw):
      argv[0] = pythonw
  return ' '.join(f'"{arg}"' if ' ' in arg else arg for arg in argv)
