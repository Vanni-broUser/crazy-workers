import json
import logging
import os

from .base import BootError, BootState, atomic_write
from .detect import get_provider


logger = logging.getLogger('crazy_workers')

_MARKER_NAME = 'boot.json'


def ensure_boot_restore(service_dir, workers_dir, provider=None):
  """Best-effort, one-time install of the per-user boot-restore hook.

  Called automatically when a worker starts. Never raises: a failure is logged
  and recorded in the marker so `status` can report it. The attempt happens at
  most once per workers directory — delete ``.service/boot.json`` to retry.
  """
  if os.environ.get('CRAZY_WORKERS_NO_BOOT'):
    return
  os.makedirs(service_dir, exist_ok=True)
  marker = os.path.join(service_dir, _MARKER_NAME)
  if os.path.exists(marker):
    return

  prov = provider if provider is not None else get_provider()
  if prov is None:
    _write_marker(marker, {'installed': False, 'mechanism': 'unsupported'})
    return

  try:
    prov.install(workers_dir)
    _write_marker(marker, {'installed': True, 'mechanism': prov.mechanism})
    logger.info('Boot-restore hook installed via %s', prov.mechanism)
  except BootError as exc:
    logger.warning('Boot-restore hook not installed: %s', exc)
    _write_marker(marker, {'installed': False, 'mechanism': prov.mechanism, 'error': str(exc)})


def boot_state(workers_dir, provider=None):
  """Live BootState for `status`. Degrades gracefully when unavailable."""
  if os.environ.get('CRAZY_WORKERS_NO_BOOT'):
    return BootState(
      supported=False, installed=False, mechanism='disabled', detail='disabled via CRAZY_WORKERS_NO_BOOT'
    )

  prov = provider if provider is not None else get_provider()
  if prov is None:
    return BootState(supported=False, installed=False, mechanism='unsupported', detail='platform not supported')
  try:
    return prov.state(workers_dir)
  except BootError as exc:
    return BootState(supported=True, installed=False, mechanism=prov.mechanism, detail=str(exc))


def _write_marker(marker, data):
  atomic_write(marker, json.dumps(data))
