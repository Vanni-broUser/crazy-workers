from unittest import mock

from tests.base import BaseTestCase


class TestStartTriggersBootRestore(BaseTestCase):
  def test_start_calls_ensure_boot_when_enabled(self):
    self.manager.auto_boot = True
    with mock.patch('crazy_workers.core.manager.starter.ensure_boot_restore') as ensure:
      self.manager.start_worker('example_worker', worker_key='wire')
    ensure.assert_called_once()
    self.manager.stop_worker('wire')

  def test_start_skips_ensure_boot_when_disabled(self):
    self.manager.auto_boot = False
    with mock.patch('crazy_workers.core.manager.starter.ensure_boot_restore') as ensure:
      self.manager.start_worker('example_worker', worker_key='nowire')
    ensure.assert_not_called()
    self.manager.stop_worker('nowire')
