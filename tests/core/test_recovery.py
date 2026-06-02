import os
from unittest.mock import patch

from crazy_workers.core.recovery import RecoveryLock
from tests.base import BaseTestCase


class TestRecoveryLock(BaseTestCase):
  def _lock_path(self, name='test.lock'):
    return os.path.join(self.test_dir, name)

  def test_acquire_and_release(self):
    lock = RecoveryLock(self._lock_path())
    self.assertTrue(lock.acquire())
    self.assertTrue(os.path.exists(self._lock_path()))
    lock.release()
    self.assertFalse(os.path.exists(self._lock_path()))

  def test_second_acquire_fails_while_held(self):
    lock1 = RecoveryLock(self._lock_path())
    lock2 = RecoveryLock(self._lock_path())
    self.assertTrue(lock1.acquire())
    self.assertFalse(lock2.acquire())
    lock1.release()

  def test_release_after_release_is_silent(self):
    lock = RecoveryLock(self._lock_path())
    lock.acquire()
    lock.release()
    lock.release()  # should not raise

  def test_stale_lock_reacquired(self):
    path = self._lock_path()
    with open(path, 'w') as f:
      f.write('999999')  # dead PID

    lock = RecoveryLock(path)
    self.assertTrue(lock.acquire())
    lock.release()

  def test_empty_lock_reacquired(self):
    path = self._lock_path()
    with open(path, 'w') as f:
      f.write('')

    lock = RecoveryLock(path)
    self.assertTrue(lock.acquire())
    lock.release()

  def test_invalid_content_lock_reacquired(self):
    path = self._lock_path()
    with open(path, 'w') as f:
      f.write('not-a-pid')

    lock = RecoveryLock(path)
    self.assertTrue(lock.acquire())
    lock.release()

  def test_live_pid_lock_not_broken(self):
    path = self._lock_path()
    with open(path, 'w') as f:
      f.write(str(os.getpid()))  # our own PID — definitely alive

    lock = RecoveryLock(path)
    self.assertFalse(lock.acquire())
    os.remove(path)

  def test_reacquire_after_release(self):
    lock = RecoveryLock(self._lock_path())
    self.assertTrue(lock.acquire())
    lock.release()
    self.assertTrue(lock.acquire())
    lock.release()

  def test_handle_lock_unreadable(self):
    path = self._lock_path()
    with open(path, 'w') as f:
      f.write('12345')
    lock = RecoveryLock(path)
    with patch('crazy_workers.core.recovery.open', side_effect=OSError('permission denied')):
      self.assertFalse(lock.acquire())
    os.remove(path)

  def test_pid_exists_raises_oserror(self):
    path = self._lock_path()
    with open(path, 'w') as f:
      f.write('12345')
    lock = RecoveryLock(path)
    with patch('crazy_workers.core.recovery.psutil.pid_exists', side_effect=OSError('os error')):
      self.assertFalse(lock.acquire())
    os.remove(path)

  def test_break_and_reacquire_remove_fails(self):
    path = self._lock_path()
    with open(path, 'w') as f:
      f.write('999999')  # dead PID → will try to break
    lock = RecoveryLock(path)
    with patch('crazy_workers.core.recovery.os.remove', side_effect=OSError('locked')):
      self.assertFalse(lock.acquire())
    os.remove(path)

  def test_break_and_reacquire_race_condition(self):
    path = self._lock_path()
    with open(path, 'w') as f:
      f.write('999999')  # dead PID → will try to break
    lock = RecoveryLock(path)
    original_remove = os.remove

    def remove_then_recreate(p):
      original_remove(p)
      with open(p, 'w') as f:
        f.write('99998')

    with patch('crazy_workers.core.recovery.os.remove', side_effect=remove_then_recreate):
      with patch('crazy_workers.core.recovery.os.open', side_effect=FileExistsError):
        self.assertFalse(lock.acquire())
