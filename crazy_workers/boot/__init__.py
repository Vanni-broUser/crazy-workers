"""Automatic, per-user boot-restore of workers.

Using crazy_workers to start a worker transparently installs an OS-level hook
(systemd user unit on Linux, a logon Scheduled Task on Windows) that runs
``recover_workers()`` after a reboot — so workers come back without the host
application having to do anything. Set ``CRAZY_WORKERS_NO_BOOT`` to opt out.
"""

from .base import BootError, BootProvider, BootState
from .detect import get_provider
from .orchestrator import boot_state, ensure_boot_restore


__all__ = ['BootError', 'BootProvider', 'BootState', 'boot_state', 'ensure_boot_restore', 'get_provider']
