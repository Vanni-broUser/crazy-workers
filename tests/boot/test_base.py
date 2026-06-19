import os
import sys
import tempfile
import unittest

from crazy_workers.boot import base


class TestBootBase(unittest.TestCase):
  def test_dir_token_is_stable_and_safe(self):
    first = base.dir_token('some/path/workers')
    second = base.dir_token('some/path/workers')
    self.assertEqual(first, second)
    self.assertTrue(all(c.isalnum() or c == '-' for c in first))

  def test_dir_token_differs_per_directory(self):
    self.assertNotEqual(base.dir_token('a/workers'), base.dir_token('b/workers'))

  def test_dir_token_handles_empty_basename(self):
    token = base.dir_token(os.path.abspath(os.sep))
    self.assertTrue(token.startswith('workers-'))

  def test_restore_command_targets_internal_module(self):
    cmd = base.restore_command('workers')
    self.assertEqual(cmd[0], sys.executable)
    self.assertIn('-m', cmd)
    self.assertIn('crazy_workers.boot', cmd)
    self.assertEqual(cmd[-1], os.path.abspath('workers'))

  def test_run_command_success(self):
    code, out, _ = base.run_command([sys.executable, '-c', 'print("hi")'])
    self.assertEqual(code, 0)
    self.assertIn('hi', out)

  def test_run_command_passes_env(self):
    code, out, _ = base.run_command([sys.executable, '-c', 'import os; print(os.environ["CW_X"])'], env={'CW_X': 'yes'})
    self.assertEqual(code, 0)
    self.assertIn('yes', out)

  def test_run_command_missing_executable(self):
    code, _, err = base.run_command(['definitely-not-a-real-binary-xyz'])
    self.assertEqual(code, 127)
    self.assertTrue(err)

  def test_atomic_write(self):
    with tempfile.TemporaryDirectory() as tmp:
      path = os.path.join(tmp, 'f.txt')
      base.atomic_write(path, 'content')
      with open(path, encoding='utf-8') as handle:
        self.assertEqual(handle.read(), 'content')
      self.assertFalse(os.path.exists(path + '.tmp'))
