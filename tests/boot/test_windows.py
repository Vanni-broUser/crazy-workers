import os
import tempfile
import unittest

from crazy_workers.boot import windows
from crazy_workers.boot.base import BootError


class FakeRunner:
  def __init__(self, code=0, out='', err=''):
    self.calls = []
    self._result = (code, out, err)

  def __call__(self, cmd, env=None):
    self.calls.append(cmd)
    return self._result


class TestWindowsTaskProvider(unittest.TestCase):
  def test_install_creates_logon_task(self):
    runner = FakeRunner()
    windows.WindowsTaskProvider(runner=runner).install('w')
    cmd = runner.calls[0]
    self.assertEqual(cmd[0], 'schtasks')
    self.assertIn('/Create', cmd)
    self.assertIn('ONLOGON', cmd)
    task_name = cmd[cmd.index('/TN') + 1]
    self.assertTrue(task_name.startswith('CrazyWorkers\\restore-'))

  def test_install_raises_on_failure(self):
    with self.assertRaises(BootError):
      windows.WindowsTaskProvider(runner=FakeRunner(code=1, err='bad')).install('w')

  def test_state_installed(self):
    state = windows.WindowsTaskProvider(runner=FakeRunner(code=0)).state('w')
    self.assertTrue(state.installed)
    self.assertFalse(state.at_boot)
    self.assertIn('logon', state.detail)

  def test_state_not_installed(self):
    state = windows.WindowsTaskProvider(runner=FakeRunner(code=1)).state('w')
    self.assertFalse(state.installed)


class TestTaskCommand(unittest.TestCase):
  def test_quotes_spaces(self):
    cmd = windows._task_command(['/a b/python3', '--workers-dir', '/x y/w'])
    self.assertIn('"/a b/python3"', cmd)
    self.assertIn('"/x y/w"', cmd)

  def test_keeps_python_when_no_pythonw(self):
    cmd = windows._task_command(['C:\\Py\\python.exe', '-m', 'crazy_workers.boot'])
    self.assertIn('python.exe', cmd)
    self.assertNotIn('pythonw.exe', cmd)

  def test_swaps_to_pythonw_when_present(self):
    with tempfile.TemporaryDirectory() as tmp:
      python = os.path.join(tmp, 'python.exe')
      pythonw = os.path.join(tmp, 'pythonw.exe')
      open(python, 'w').close()
      open(pythonw, 'w').close()
      cmd = windows._task_command([python, '-m', 'crazy_workers.boot'])
      self.assertIn('pythonw.exe', cmd)
