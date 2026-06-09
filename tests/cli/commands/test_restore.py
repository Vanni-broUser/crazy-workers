import os
from io import StringIO
from unittest.mock import patch

from crazy_workers.cli.main import main as cli_main
from tests.base import BaseTestCase


class TestCliRestore(BaseTestCase):
  def test_cli_restore_command(self):
    # Setup: simulate a worker that needs restoration in the DB
    from crazy_workers import WorkerStatus
    from crazy_workers.database.schema import Worker

    # Ensure the .service dir exists so recover_workers doesn't skip
    os.makedirs(self.manager.service_dir, exist_ok=True)

    with self.manager.storage.session_scope() as session:
      session.query(Worker).delete()
      worker = Worker(
        worker_key='restore_me', worker_type='example_worker', parameters={}, status=WorkerStatus.RUNNING, pid=99999
      )
      session.add(worker)

    # We must patch CRAZY_WORKERS_DIR so the CLI uses our test manager's dir
    with patch.dict(os.environ, {'CRAZY_WORKERS_DIR': self.workers_path}):
      with patch('sys.argv', ['crazy-workers', 'restore']):
        with patch('sys.stdout', new=StringIO()) as fake_out:
          try:
            cli_main()
          except SystemExit as e:
            self.assertEqual(e.code, 0)

          output = fake_out.getvalue()
          self.assertIn('Successfully restored 1 workers', output)
          self.assertIn('restore_me', output)

    # Verify it is actually running now
    self.wait_for_worker_status(self.manager, 'restore_me', 'RUNNING')
    workers = self.manager.list_workers()
    worker = next(w for w in workers if w['worker_key'] == 'restore_me')
    self.assertEqual(worker['status'], 'RUNNING')
    self.assertNotEqual(worker['pid'], 99999)

    self.manager.stop_worker('restore_me')

  def test_cli_restore_command_nothing(self):
    with patch.dict(os.environ, {'CRAZY_WORKERS_DIR': self.workers_path}):
      with patch('sys.argv', ['crazy-workers', 'restore']):
        with patch('sys.stdout', new=StringIO()) as fake_out:
          try:
            cli_main()
          except SystemExit as e:
            self.assertEqual(e.code, 0)

          output = fake_out.getvalue()
          self.assertIn('No workers needed restoration', output)
