import sys
import unittest
from unittest.mock import patch

from crazy_workers import _bootstrap


class TestBootstrap(unittest.TestCase):
  def test_main_strips_identity_token_from_argv(self):
    """The worker script must never see the manager's identity token."""
    captured = {}

    def fake_run_path(path, run_name):
      captured['argv'] = list(sys.argv)
      captured['path'] = path
      captured['run_name'] = run_name

    original_argv = sys.argv
    original_path = list(sys.path)
    sys.argv = ['bootstrap.py', '--cw-key=foo', '/tmp/worker.py', '{"a": 1}']
    try:
      with patch('crazy_workers._bootstrap.logging.basicConfig'):
        with patch('crazy_workers._bootstrap.runpy.run_path', side_effect=fake_run_path):
          _bootstrap.main()
    finally:
      sys.argv = original_argv
      sys.path[:] = original_path

    self.assertEqual(captured['argv'], ['/tmp/worker.py', '{"a": 1}'])
    self.assertEqual(captured['path'], '/tmp/worker.py')
    self.assertEqual(captured['run_name'], '__main__')


if __name__ == '__main__':
  unittest.main()
