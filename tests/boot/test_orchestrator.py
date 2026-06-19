import json
import os
import shutil
import tempfile
import unittest
from unittest import mock

from crazy_workers.boot import orchestrator
from crazy_workers.boot.base import BootError, BootState


class FakeProvider:
  mechanism = 'fake'

  def __init__(self, raise_error=False, state=None):
    self.installed = False
    self._raise = raise_error
    self._state = state

  def install(self, workers_dir):
    if self._raise:
      raise BootError('cannot install')
    self.installed = True

  def state(self, workers_dir):
    return self._state


class BootTestBase(unittest.TestCase):
  def setUp(self):
    self.tmp = tempfile.mkdtemp()
    self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)
    self.service = os.path.join(self.tmp, '.service')
    os.makedirs(self.service)
    self._env = mock.patch.dict(os.environ, {'CRAZY_WORKERS_NO_BOOT': ''})
    self._env.start()
    self.addCleanup(self._env.stop)

  def marker(self):
    return os.path.join(self.service, 'boot.json')


class TestEnsureBootRestore(BootTestBase):
  def test_env_opt_out_skips(self):
    os.environ['CRAZY_WORKERS_NO_BOOT'] = '1'
    prov = FakeProvider()
    orchestrator.ensure_boot_restore(self.service, 'w', provider=prov)
    self.assertFalse(os.path.exists(self.marker()))
    self.assertFalse(prov.installed)

  def test_installs_and_writes_marker(self):
    prov = FakeProvider()
    orchestrator.ensure_boot_restore(self.service, 'w', provider=prov)
    self.assertTrue(prov.installed)
    with open(self.marker(), encoding='utf-8') as handle:
      data = json.load(handle)
    self.assertTrue(data['installed'])
    self.assertEqual(data['mechanism'], 'fake')

  def test_existing_marker_skips_second_attempt(self):
    orchestrator.ensure_boot_restore(self.service, 'w', provider=FakeProvider())
    second = FakeProvider()
    orchestrator.ensure_boot_restore(self.service, 'w', provider=second)
    self.assertFalse(second.installed)

  def test_boot_error_recorded_not_raised(self):
    orchestrator.ensure_boot_restore(self.service, 'w', provider=FakeProvider(raise_error=True))
    with open(self.marker(), encoding='utf-8') as handle:
      data = json.load(handle)
    self.assertFalse(data['installed'])
    self.assertIn('error', data)

  def test_unsupported_platform_records_marker(self):
    with mock.patch('crazy_workers.boot.orchestrator.get_provider', return_value=None):
      orchestrator.ensure_boot_restore(self.service, 'w')
    with open(self.marker(), encoding='utf-8') as handle:
      data = json.load(handle)
    self.assertEqual(data['mechanism'], 'unsupported')

  def test_default_provider_resolved_via_get_provider(self):
    prov = FakeProvider()
    with mock.patch('crazy_workers.boot.orchestrator.get_provider', return_value=prov):
      orchestrator.ensure_boot_restore(self.service, 'w')
    self.assertTrue(prov.installed)

  def test_creates_service_dir_if_missing(self):
    nested = os.path.join(self.tmp, 'sub', '.service')
    orchestrator.ensure_boot_restore(nested, 'w', provider=FakeProvider())
    self.assertTrue(os.path.exists(os.path.join(nested, 'boot.json')))


class TestBootState(BootTestBase):
  def test_disabled_via_env(self):
    os.environ['CRAZY_WORKERS_NO_BOOT'] = '1'
    state = orchestrator.boot_state('w')
    self.assertEqual(state.mechanism, 'disabled')

  def test_unsupported_platform(self):
    with mock.patch('crazy_workers.boot.orchestrator.get_provider', return_value=None):
      state = orchestrator.boot_state('w')
    self.assertFalse(state.supported)
    self.assertEqual(state.mechanism, 'unsupported')

  def test_delegates_to_provider(self):
    state = BootState(supported=True, installed=True, mechanism='fake', at_boot=True, detail='ok')
    result = orchestrator.boot_state('w', provider=FakeProvider(state=state))
    self.assertTrue(result.installed)
    self.assertTrue(result.at_boot)

  def test_provider_error_becomes_state(self):
    class ErrProvider(FakeProvider):
      def state(self, workers_dir):
        raise BootError('cannot inspect')

    result = orchestrator.boot_state('w', provider=ErrProvider())
    self.assertFalse(result.installed)
    self.assertIn('cannot inspect', result.detail)
