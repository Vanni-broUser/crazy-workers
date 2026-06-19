import os
import shutil
import tempfile
import unittest
from unittest import mock

from crazy_workers.boot import systemd
from crazy_workers.boot.base import BootError


class FakeRunner:
  def __init__(self, results=None):
    self.calls = []
    self._results = results or {}

  def __call__(self, cmd, env=None):
    self.calls.append((cmd, env))
    return self._results.get(tuple(cmd[:3]), (0, '', ''))


class TestSystemdUserProvider(unittest.TestCase):
  def setUp(self):
    self.tmp = tempfile.mkdtemp()
    self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)

  def _provider(self, runner):
    return systemd.SystemdUserProvider(unit_dir=self.tmp, runner=runner, uid=1000, user='alice')

  def test_install_writes_unit_and_enables(self):
    runner = FakeRunner()
    self._provider(runner).install('myworkers')

    units = os.listdir(self.tmp)
    self.assertEqual(len(units), 1)
    with open(os.path.join(self.tmp, units[0]), encoding='utf-8') as handle:
      content = handle.read()
    self.assertIn('ExecStart=', content)
    self.assertIn('crazy_workers.boot', content)

    commands = [cmd for cmd, _ in runner.calls]
    self.assertIn(['systemctl', '--user', 'daemon-reload'], commands)
    self.assertTrue(any(cmd[:3] == ['systemctl', '--user', 'enable'] for cmd in commands))
    self.assertTrue(any(cmd[0] == 'loginctl' and cmd[1] == 'enable-linger' for cmd in commands))
    systemctl_env = next(env for cmd, env in runner.calls if cmd[0] == 'systemctl')
    self.assertEqual(systemctl_env['XDG_RUNTIME_DIR'], '/run/user/1000')

  def test_install_raises_on_daemon_reload_failure(self):
    runner = FakeRunner({('systemctl', '--user', 'daemon-reload'): (1, '', 'boom')})
    with self.assertRaises(BootError):
      self._provider(runner).install('w')

  def test_install_raises_on_enable_failure(self):
    runner = FakeRunner({('systemctl', '--user', 'enable'): (1, '', 'nope')})
    with self.assertRaises(BootError):
      self._provider(runner).install('w')

  def test_state_not_installed_skips_linger_query(self):
    runner = FakeRunner()
    state = self._provider(runner).state('w')
    self.assertFalse(state.installed)
    self.assertFalse(state.at_boot)
    self.assertFalse(runner.calls)

  def test_state_installed_runs_at_login_without_linger(self):
    runner = FakeRunner({('loginctl', 'show-user', 'alice'): (0, 'Linger=no\n', '')})
    prov = self._provider(runner)
    prov.install('w')
    state = prov.state('w')
    self.assertTrue(state.installed)
    self.assertFalse(state.at_boot)
    self.assertIn('login', state.detail)

  def test_state_installed_runs_at_boot_with_linger(self):
    runner = FakeRunner({('loginctl', 'show-user', 'alice'): (0, 'Linger=yes\n', '')})
    prov = self._provider(runner)
    prov.install('w')
    state = prov.state('w')
    self.assertTrue(state.at_boot)
    self.assertIn('linger', state.detail)

  def test_defaults_resolve_unit_dir_uid_and_user(self):
    prov = systemd.SystemdUserProvider(runner=FakeRunner())
    self.assertTrue(prov._unit_dir.replace('\\', '/').endswith('systemd/user'))
    self.assertIsInstance(prov._uid, int)
    self.assertTrue(prov._user)


class TestSystemdHelpers(unittest.TestCase):
  def test_exec_start_quotes_spaces(self):
    line = systemd._exec_start(['/usr/bin/python', '-m', 'crazy_workers.boot', '--workers-dir', '/a b/w'])
    self.assertIn('"/a b/w"', line)
    self.assertIn('-m', line)

  def test_current_uid_with_getuid(self):
    with mock.patch.object(os, 'getuid', new=lambda: 4242, create=True):
      self.assertEqual(systemd._current_uid(), 4242)

  def test_current_uid_without_getuid(self):
    with mock.patch.object(os, 'getuid', None, create=True):
      self.assertEqual(systemd._current_uid(), 0)

  def test_current_user_from_getpass(self):
    with mock.patch('crazy_workers.boot.systemd.getpass.getuser', return_value='bob'):
      self.assertEqual(systemd._current_user(), 'bob')

  def test_current_user_fallback_on_error(self):
    with mock.patch('crazy_workers.boot.systemd.getpass.getuser', side_effect=KeyError):
      with mock.patch.dict(os.environ, {'USER': 'envuser'}, clear=False):
        self.assertEqual(systemd._current_user(), 'envuser')
