import argparse
import sys

from rich.console import Console
from rich.panel import Panel

from ..core.manager import WorkerManager
from .commands import list_workers, start_worker, stop_worker
from .discovery import resolve_workers_dir


def main():
  console = Console()
  err_console = Console(stderr=True)

  def formatter(prog):
    return argparse.HelpFormatter(prog, max_help_position=32)

  parser = argparse.ArgumentParser(description='Crazy Workers CLI', formatter_class=formatter)
  parser.add_argument('--workers-dir', help='Directory containing worker scripts')

  subparsers = parser.add_subparsers(dest='command', help='Commands')

  # List command
  subparsers.add_parser('list', help='List all workers and their status')

  # Start command
  start_parser = subparsers.add_parser('start', help='Start a worker (interactive if type missing)')
  start_parser.add_argument('worker_type', nargs='?', help='The type (filename) of worker to start')
  start_parser.add_argument('--key', help='Optional custom key for the worker')

  # Stop command
  stop_parser = subparsers.add_parser('stop', help='Stop a worker (interactive if key missing)')
  stop_parser.add_argument('worker_key', nargs='?', help='The key of the worker to stop')

  args = parser.parse_args()

  if not args.command:
    console.print(
      Panel.fit(
        '[bold cyan]Crazy Workers CLI[/bold cyan]\n[dim]Manage your background processes with ease[/dim]',
        border_style='cyan',
      )
    )
    parser.print_help()
    sys.exit(1)

  workers_dir = resolve_workers_dir(args.workers_dir)
  try:
    with WorkerManager(workers_dir, create_dir=False) as manager:
      if args.command == 'list':
        list_workers(manager)
      elif args.command == 'start':
        if not start_worker(manager, args.worker_type, worker_key=args.key):
          sys.exit(1)
      elif args.command == 'stop':
        if not stop_worker(manager, args.worker_key):
          sys.exit(1)
  except ValueError as e:
    err_console.print(f'[bold red]Error:[/bold red] {e}')
    sys.exit(1)


if __name__ == '__main__':
  main()
