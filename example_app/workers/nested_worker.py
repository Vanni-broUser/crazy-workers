import json
import logging
import sys
import time

from crazy_workers import WorkerManager


def main():
  params = json.loads(sys.argv[1]) if len(sys.argv) > 1 else {}
  child_type = params.get('child_type', 'example_worker')
  num_children = params.get('num_children', 2)
  workers_dir = params.get('workers_dir', '.')

  manager = WorkerManager(workers_dir=workers_dir, create_dir=False)

  logging.info(f'Spawning {num_children} children of type "{child_type}"')

  try:
    for i in range(num_children):
      child_key = f'child_{i}'
      success, _ = manager.start_worker(child_type, worker_key=child_key)
      if success:
        logging.info(f'Started child: {child_key}')
      else:
        logging.warning(f'Failed to start child: {child_key}')

    logging.info('All children spawned. Waiting...')
    time.sleep(15)
  finally:
    manager.dispose()


if __name__ == '__main__':
  main()
