import platform

from .systemd import SystemdUserProvider
from .windows import WindowsTaskProvider


def get_provider(system=None):
  """Return the boot-restore provider for the platform, or None if unsupported."""
  system = system or platform.system()
  if system == 'Linux':
    return SystemdUserProvider()
  if system == 'Windows':
    return WindowsTaskProvider()
  return None
