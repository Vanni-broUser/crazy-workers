import os
import shutil
import signal
import tempfile
import unittest
from unittest.mock import MagicMock, patch

from crazy_workers.daemon.runner import _install_signal_handlers
from crazy_workers.daemon.runner import main as daemon_main


class TestDaemonMain(unittest.TestCase):
  def setUp(self):
    self.tmp = tempfile.mkdtemp(prefix='cw_daemon_')
    self.workers_dir = os.path.join(self.tmp, 'workers')
    os.makedirs(self.workers_dir)

  def tearDown(self):
    shutil.rmtree(self.tmp, ignore_errors=True)

  def test_missing_workers_dir_returns_2(self):
    code = daemon_main(['--workers-dir', os.path.join(self.tmp, 'nope')])
    self.assertEqual(code, 2)

  def test_runs_and_releases_lock(self):
    # Don't actually loop — just prove the daemon builds, locks, runs, unlocks.
    with patch('crazy_workers.daemon.runner.Reconciler') as fake_reconciler:
      fake_reconciler.return_value.run_forever.return_value = None
      code = daemon_main(['--workers-dir', self.workers_dir])

    self.assertEqual(code, 0)
    fake_reconciler.return_value.run_forever.assert_called_once()
    # Lock released on exit.
    self.assertFalse(os.path.exists(os.path.join(self.workers_dir, '.service', 'daemon.lock')))

  def test_single_instance_lock_blocks_second_daemon(self):
    service_dir = os.path.join(self.workers_dir, '.service')
    os.makedirs(service_dir, exist_ok=True)
    # A live PID (our own) already holds the daemon lock.
    with open(os.path.join(service_dir, 'daemon.lock'), 'w') as f:
      f.write(str(os.getpid()))

    with patch('crazy_workers.daemon.runner.Reconciler') as fake_reconciler:
      code = daemon_main(['--workers-dir', self.workers_dir])

    self.assertEqual(code, 1)
    fake_reconciler.assert_not_called()

  def test_install_signal_handlers_invokes_stop(self):
    reconciler = MagicMock()
    with patch('crazy_workers.daemon.runner.signal.signal') as mock_signal:
      _install_signal_handlers(reconciler)

    handler = None
    for call in mock_signal.call_args_list:
      if call[0][0] == signal.SIGTERM:
        handler = call[0][1]
    self.assertIsNotNone(handler)

    handler(signal.SIGTERM, None)
    reconciler.stop.assert_called_once()
