import argparse

from ..core.manager import WorkerManager


def main(argv=None):
  """Internal entrypoint invoked by the boot hook to restore workers.

  Not a user-facing command: ``ensure_boot_restore`` wires it into the OS boot
  hook, and it runs ``recover_workers()`` for a single workers directory.
  """
  parser = argparse.ArgumentParser(prog='crazy_workers.boot', description='Restore workers at boot (internal).')
  parser.add_argument('--workers-dir', required=True, help='Directory containing the worker scripts')
  args = parser.parse_args(argv)

  with WorkerManager(args.workers_dir, create_dir=False, auto_boot=False, auto_recover=False) as manager:
    restarted = manager.recover_workers()
  return len(restarted)
