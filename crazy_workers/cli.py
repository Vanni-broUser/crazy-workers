import argparse
import json
import sys

from crazy_workers import WorkerManager


def main():
  parser = argparse.ArgumentParser(description='Crazy Workers CLI')
  parser.add_argument('--db', required=True, help='Path to the SQLite database')
  parser.add_argument('--workers-dir', required=True, help='Directory containing worker scripts')

  subparsers = parser.add_subparsers(dest='command', help='Commands')

  # List command
  subparsers.add_parser('list', help='List all workers and their status')

  # Stop command
  stop_parser = subparsers.add_parser('stop', help='Stop a worker')
  stop_parser.add_argument('worker_key', help='The key of the worker to stop')

  args = parser.parse_args()

  if not args.command:
    parser.print_help()
    sys.exit(1)

  manager = WorkerManager(args.db, args.workers_dir)

  try:
    if args.command == 'list':
      workers = manager.list_workers()
      # Using sys.stdout.write to comply with 'No print statements' mandate
      sys.stdout.write(json.dumps(workers, indent=2) + '\n')

    elif args.command == 'stop':
      success, message = manager.stop_worker(args.worker_key)
      if success:
        sys.stdout.write(f'Success: {message}\n')
      else:
        sys.stderr.write(f'Error: {message}\n')
        sys.exit(1)
  finally:
    manager.dispose()


if __name__ == '__main__':
  main()
