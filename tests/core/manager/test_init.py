import os

from crazy_workers import WorkerManager
from tests.base import BaseTestCase


class TestManagerInit(BaseTestCase):
  def test_manager_no_create_dir(self):
    test_dir = 'temp_no_create'
    if os.path.exists(test_dir):
      import shutil

      shutil.rmtree(test_dir)

    with self.assertRaises(ValueError):
      WorkerManager(test_dir, create_dir=False)

  def test_manager_no_create_service_dir(self):
    test_dir = 'temp_workers_exists'
    os.makedirs(test_dir, exist_ok=True)
    try:
      manager = WorkerManager(test_dir, create_dir=False)
      self.assertFalse(os.path.exists(os.path.join(test_dir, '.service')))

      # Test protected methods
      self.assertEqual(manager.list_workers(), [])
      success, msg = manager.start_worker('test')
      self.assertFalse(success)
      self.assertIn('database missing', msg)

      manager.dispose()
    finally:
      import shutil

      shutil.rmtree(test_dir)

  def test_library_dispose_exception(self):
    from unittest.mock import MagicMock

    self.manager._active_processes['fail'] = MagicMock()
    self.manager._active_processes['fail'].poll.side_effect = Exception('poll fail')
    self.manager.dispose()
    self.assertEqual(len(self.manager._active_processes), 0)
