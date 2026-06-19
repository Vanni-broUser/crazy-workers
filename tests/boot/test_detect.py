import unittest
from unittest import mock

from crazy_workers.boot import detect
from crazy_workers.boot.systemd import SystemdUserProvider
from crazy_workers.boot.windows import WindowsTaskProvider


class TestGetProvider(unittest.TestCase):
  def test_linux_returns_systemd(self):
    self.assertIsInstance(detect.get_provider('Linux'), SystemdUserProvider)

  def test_windows_returns_task(self):
    self.assertIsInstance(detect.get_provider('Windows'), WindowsTaskProvider)

  def test_other_returns_none(self):
    self.assertIsNone(detect.get_provider('Darwin'))

  def test_defaults_to_platform_system(self):
    with mock.patch('crazy_workers.boot.detect.platform.system', return_value='Windows'):
      self.assertIsInstance(detect.get_provider(), WindowsTaskProvider)
