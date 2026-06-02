import json
import sys
import time

from crazy_workers import WorkerManager


def main():
  if len(sys.argv) > 1:
    params = json.loads(sys.argv[1])
  else:
    params = {}

  child_type = params.get('child_type', 'example_worker')
  num_children = params.get('num_children', 2)
  workers_dir = params.get('workers_dir', '.')

  sys.stdout.flush()

  # The parent worker uses its own manager to spawn children
  # Note: create_dir=False because we assume the environment is already set up
  manager = WorkerManager(workers_dir=workers_dir, create_dir=False)

  sys.stdout.write(f'Spawning {num_children} children of type "{child_type}"\n')
  sys.stdout.flush()

  try:
    for i in range(num_children):
      child_key = f'child_{i}'
      success, _ = manager.start_worker(child_type, worker_key=child_key)
      if success:
        sys.stdout.write(f'Started child: {child_key}\n')
      else:
        sys.stdout.write(f'Failed to start child: {child_key}\n')
      sys.stdout.flush()

    sys.stdout.write('All children spawned. Waiting...\n')
    sys.stdout.flush()
    time.sleep(15)
  finally:
    # Important: In this implementation, if the parent exits, the children
    # will keep running as independent processes (orphans)
    # unless we explicitly stop them here.
    # Usually, we WANT children to survive the parent in this library's philosophy.
    manager.dispose()


if __name__ == '__main__':
  main()
