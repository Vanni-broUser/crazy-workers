import argparse
import sys
from rich.panel import Panel

from ..core.manager import WorkerManager
from .commands import show_params, show_status, start_worker, stop_worker
from .discovery import resolve_workers_dir
from .ui import console, err_console


def main():

  def formatter(prog):
    return argparse.HelpFormatter(prog, max_help_position=32)

  parser = argparse.ArgumentParser(description='Crazy Workers CLI', formatter_class=formatter)
  parser.add_argument('--workers-dir', help='Directory containing worker scripts')

  subparsers = parser.add_subparsers(dest='command', help='Commands')

  # Status command
  subparsers.add_parser('status', help='Show workers and boot-restore status')

  # Start command
  start_parser = subparsers.add_parser('start', help='Start a worker (interactive if type missing)')
  start_parser.add_argument('worker_type', nargs='?', help='The type (filename) of worker to start')
  start_parser.add_argument('--key', help='Optional custom key for the worker')
  start_parser.add_argument('--params', help='JSON string of parameters for the worker')

  # Stop command
  stop_parser = subparsers.add_parser('stop', help='Stop a worker (interactive if key missing)')
  stop_parser.add_argument('worker_key', nargs='?', help='The key of the worker to stop')

  # Params command
  params_parser = subparsers.add_parser('params', help='Show parameters for a worker')
  params_parser.add_argument('worker_key', nargs='?', help='The key of the worker')

  args = parser.parse_args()

  if not args.command:
    console().print(
      Panel.fit(
        '[bold cyan]Crazy Workers CLI[/bold cyan]\n[dim]Manage your background processes with ease[/dim]',
        border_style='cyan',
      )
    )
    parser.print_help()
    sys.exit(1)

  workers_dir = resolve_workers_dir(args.workers_dir)
  try:
    with WorkerManager(workers_dir, create_dir=False, auto_recover=False) as manager:
      if args.command == 'status':
        show_status(manager)
      elif args.command == 'start':
        import json

        params = None
        if args.params:
          try:
            params = json.loads(args.params)
          except json.JSONDecodeError:
            err_console().print('[bold red]Error:[/bold red] Invalid JSON in --params')
            sys.exit(1)

        if not start_worker(manager, args.worker_type, worker_key=args.key, parameters=params):
          sys.exit(1)
      elif args.command == 'stop':
        if not stop_worker(manager, args.worker_key):
          sys.exit(1)
      elif args.command == 'params':
        if not show_params(manager, args.worker_key):
          sys.exit(1)
  except ValueError as e:
    err_console().print(f'[bold red]Error:[/bold red] {e}')
    sys.exit(1)


if __name__ == '__main__':
  main()
