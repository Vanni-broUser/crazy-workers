import argparse
import logging
import os
import signal

from ..core.manager import WorkerManager
from ..core.recovery import RecoveryLock
from .reconciler import Reconciler


logger = logging.getLogger('crazy_workers')


def main(argv=None):
  parser = argparse.ArgumentParser(prog='crazy_workers.daemon', description='Run the reconcile loop.')
  parser.add_argument('--workers-dir', required=True, help='Directory containing worker scripts')
  parser.add_argument(
    '--db-url',
    default=os.environ.get('CRAZY_WORKERS_DB_URL'),
    help='Shared DB URL (defaults to $CRAZY_WORKERS_DB_URL, else the local SQLite under .service/)',
  )
  parser.add_argument('--interval', type=float, default=2.0, help='Seconds between reconcile passes')
  parser.add_argument('--log-level', default=os.environ.get('CRAZY_WORKERS_LOG_LEVEL', 'INFO'))
  args = parser.parse_args(argv)

  logging.basicConfig(
    level=getattr(logging, args.log_level.upper(), logging.INFO),
    format='%(asctime)s %(levelname)s %(name)s: %(message)s',
  )

  # Fail loudly on a misconfigured path rather than silently creating an empty
  # workers dir (and then never finding any worker script in it).
  if not os.path.isdir(args.workers_dir):
    logger.error('Workers directory %s does not exist', args.workers_dir)
    return 2

  # The daemon owns the host-local runtime area (.service, logs, and the SQLite
  # file in self-contained mode), so it materialises them (create_dir=True).
  # auto_recover is off: a reconcile pass already restarts dead RUNNING workers.
  manager = WorkerManager(
    args.workers_dir,
    create_dir=True,
    auto_boot=False,
    auto_recover=False,
    db_url=args.db_url,
    create_tables=args.db_url is None,
  )

  lock = RecoveryLock(os.path.join(manager.service_dir, 'daemon.lock'))
  if not lock.acquire():
    logger.error('Another crazy_workers daemon already owns %s; exiting.', args.workers_dir)
    manager.dispose()
    return 1

  reconciler = Reconciler(manager, interval=args.interval)
  _install_signal_handlers(reconciler)

  try:
    reconciler.run_forever()
  finally:
    lock.release()
    manager.dispose()
  return 0


def _install_signal_handlers(reconciler):
  def _handle(signum, _frame):
    logger.info('Received signal %s; shutting down.', signum)
    reconciler.stop()

  for signame in ('SIGTERM', 'SIGINT'):
    sig = getattr(signal, signame, None)
    if sig is not None:
      try:
        signal.signal(sig, _handle)
      except (ValueError, OSError):
        # Not the main thread, or unsupported on this platform — best effort.
        pass
