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


def main():
  logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    stream=sys.stderr,
    force=True,
  )

  # Restore sys.argv so the worker sees [worker_path, json_params]
  sys.argv = sys.argv[1:]

  worker_path = sys.argv[0]
  sys.path.insert(0, os.path.dirname(os.path.abspath(worker_path)))

  runpy.run_path(worker_path, run_name='__main__')


if __name__ == '__main__':
  main()
