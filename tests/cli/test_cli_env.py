import os
from io import StringIO
from unittest.mock import patch

from crazy_workers.cli.discovery import load_env, save_to_env, resolve_workers_dir
from crazy_workers.cli.main import main as cli_main
from tests.base import BaseTestCase


class TestCliEnv(BaseTestCase):
  def setUp(self):
    super().setUp()
    self.env_file = '.env'
    if os.path.exists(self.env_file):
      os.remove(self.env_file)
    # Isolate environment variables
    self.env_patcher = patch.dict(os.environ, {})
    self.env_patcher.start()

  def tearDown(self):
    self.env_patcher.stop()
    if os.path.exists(self.env_file):
      os.remove(self.env_file)
    super().tearDown()

  def test_save_to_env_new_file(self):
    save_to_env('TEST_KEY', 'test_value')
    with open(self.env_file, 'r') as f:
      content = f.read()
    self.assertIn('TEST_KEY=test_value\n', content)

  def test_save_to_env_update_existing(self):
    with open(self.env_file, 'w') as f:
      f.write('OTHER_KEY=other\nTEST_KEY=old_value\n')

    save_to_env('TEST_KEY', 'new_value')

    with open(self.env_file, 'r') as f:
      lines = f.readlines()
    self.assertIn('TEST_KEY=new_value\n', lines)
    self.assertIn('OTHER_KEY=other\n', lines)
    self.assertEqual(len(lines), 2)

  def test_load_env(self):
    with open(self.env_file, 'w') as f:
      f.write('# Comment\n  \nLOADED_KEY="loaded_value"\n')

    with patch.dict(os.environ, {}):
      load_env()
      self.assertEqual(os.environ.get('LOADED_KEY'), 'loaded_value')

  def test_resolve_workers_dir_env_not_exists(self):
    with patch.dict(os.environ, {'CRAZY_WORKERS_DIR': '/non/existent/env/dir'}):
      with patch('sys.stderr', new=StringIO()) as fake_err:
        with self.assertRaises(SystemExit) as cm:
          resolve_workers_dir(None)
        self.assertEqual(cm.exception.code, 1)
        self.assertIn(
          'Error: Directory "/non/existent/env/dir" (from CRAZY_WORKERS_DIR) does not exist', fake_err.getvalue()
        )

  def test_resolve_workers_dir_interactive_save(self):
    # Mock isatty to True
    with patch('sys.stdin.isatty', return_value=True):
      # Mock Prompt.ask from rich
      with patch('rich.prompt.Prompt.ask', return_value=self.workers_path):
        with patch('sys.stdout', new=StringIO()) as fake_out:
          # Also patch stderr for this test if needed, but stdout is where Prompt.ask prints the question
          with patch('sys.stderr', new=StringIO()):
            resolved = resolve_workers_dir(None)
          self.assertEqual(os.path.abspath(resolved), os.path.abspath(self.workers_path))
          output = fake_out.getvalue()
          self.assertIn('Saved', output)
          self.assertIn('CRAZY_WORKERS_DIR', output)

          # Verify .env was written
          with open(self.env_file, 'r') as f:
            self.assertIn(f'CRAZY_WORKERS_DIR={os.path.abspath(self.workers_path)}', f.read())

  def test_resolve_workers_dir_interactive_invalid_dir(self):
    with patch('sys.stdin.isatty', return_value=True):
      with patch('rich.prompt.Prompt.ask', return_value='/non/existent/interactive/dir'):
        with patch('sys.stderr', new=StringIO()) as fake_err:
          with patch('sys.stdout', new=StringIO()):
            with self.assertRaises(SystemExit) as cm:
              resolve_workers_dir(None)
          self.assertEqual(cm.exception.code, 1)
          self.assertIn('is not a valid directory', fake_err.getvalue())

  def test_main_no_command(self):
    argv = ['crazy-workers']
    with patch('sys.argv', argv):
      with patch('sys.stdout', new=StringIO()):
        with self.assertRaises(SystemExit) as cm:
          cli_main()
        self.assertEqual(cm.exception.code, 1)
