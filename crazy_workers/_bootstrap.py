"""
Thin launcher invoked by WorkerManager for every worker subprocess.
Configures logging once so individual worker scripts don't have to.

Invocation (managed internally by WorkerManager):
    python -m crazy_workers._bootstrap <worker_path> <json_params>
"""

import logging
import os
import runpy
import sys


# Must match crazy_workers.core.engine.WORKER_KEY_FLAG. Kept as a local literal
# so launching a worker doesn't import the package (and its heavy dependencies).
_WORKER_KEY_FLAG = '--cw-key='


def main():
  logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    stream=sys.stderr,
    force=True,
  )

  # Restore sys.argv so the worker sees [worker_path, json_params]. Drop any
  # identity token the manager injected for PID-reuse detection — it is only
  # meant to be visible from the outside, never to the worker script itself.
  sys.argv = [a for a in sys.argv[1:] if not a.startswith(_WORKER_KEY_FLAG)]

  worker_path = sys.argv[0]
  sys.path.insert(0, os.path.dirname(os.path.abspath(worker_path)))

  runpy.run_path(worker_path, run_name='__main__')


if __name__ == '__main__':
  main()
