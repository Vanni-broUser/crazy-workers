import argparse
import os
import sys

from rich.console import Console
from rich.panel import Panel
from rich.prompt import Prompt
from rich.table import Table

from crazy_workers import WorkerManager

console = Console()


def load_env():
  """Loads variables from .env file into os.environ."""
  if os.path.exists('.env'):
    try:
      with open('.env', 'r') as f:
        for line in f:
          line = line.strip()
          if not line or line.startswith('#'):
            continue
          if '=' in line:
            key, value = line.split('=', 1)
            os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))
    except Exception:
      pass


def save_to_env(key, value):
  """Saves a key-value pair to .env file."""
  lines = []
  if os.path.exists('.env'):
    try:
      with open('.env', 'r') as f:
        lines = f.readlines()
    except Exception:
      pass

  found = False
  new_line = f'{key}={value}\n'
  for i, line in enumerate(lines):
    if line.strip().startswith(f'{key}='):
      lines[i] = new_line
      found = True
      break

  if not found:
    if lines and not lines[-1].endswith('\n'):
      lines.append('\n')
    lines.append(new_line)

  with open('.env', 'w') as f:
    f.writelines(lines)


def resolve_workers_dir(flag_dir):
  load_env()
  console = Console()
  err_console = Console(stderr=True)

  # 1. Flag priority (if provided explicitly in argv)
  if flag_dir:
    if os.path.isdir(flag_dir):
      return flag_dir
    else:
      err_console.print(f'[bold red]Error:[/bold red] Directory "{flag_dir}" does not exist.')
      sys.exit(1)

  # 2. Environment Variable
  env_dir = os.environ.get('CRAZY_WORKERS_DIR')
  if env_dir:
    if os.path.isdir(env_dir):
      return env_dir
    else:
      err_console.print(f'[bold red]Error:[/bold red] Directory "{env_dir}" (from CRAZY_WORKERS_DIR) does not exist.')
      sys.exit(1)

  # 3. Interactive Prompt (if in a TTY)
  if sys.stdin.isatty():
    console.print('[bold yellow]CRAZY_WORKERS_DIR not set in environment.[/bold yellow]')
    user_input = Prompt.ask('Please enter the path to your workers directory')
    if user_input:
      if os.path.isdir(user_input):
        abs_path = os.path.abspath(user_input)
        try:
          save_to_env('CRAZY_WORKERS_DIR', abs_path)
          console.print(f'[bold green]Saved CRAZY_WORKERS_DIR={abs_path} to .env[/bold green]')
        except Exception as e:
          err_console.print(f'[bold red]Failed to save configuration:[/bold red] {e}')
        return abs_path
      else:
        err_console.print(f'[bold red]Error:[/bold red] "{user_input}" is not a valid directory.')
        sys.exit(1)

  # 4. Local workers/ folder auto-detection (fallback)
  if os.path.isdir('workers'):
    return 'workers'

  err_console.print(
    '[bold red]Error:[/bold red] Workers directory not found. '
    'Please provide it via --workers-dir or set CRAZY_WORKERS_DIR.'
  )
  sys.exit(1)


def main():
  console = Console()
  err_console = Console(stderr=True)

  # Custom formatter to fix alignment issues with long options/placeholders
  def formatter(prog):
    return argparse.HelpFormatter(prog, max_help_position=32)

  parser = argparse.ArgumentParser(description='Crazy Workers CLI', formatter_class=formatter)
  parser.add_argument('--workers-dir', help='Directory containing worker scripts')

  subparsers = parser.add_subparsers(dest='command', help='Commands')

  # List command
  subparsers.add_parser('list', help='List all workers and their status')

  # Stop command
  stop_parser = subparsers.add_parser('stop', help='Stop a worker')
  stop_parser.add_argument('worker_key', help='The key of the worker to stop')

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
    manager = WorkerManager(workers_dir, create_dir=False)
  except ValueError as e:
    err_console.print(f'[bold red]Error:[/bold red] {e}')
    sys.exit(1)

  try:
    if args.command == 'list':
      workers = manager.list_workers()
      if not workers:
        console.print('[yellow]No workers found in database.[/yellow]')
      else:
        table = Table(
          title='[bold cyan]Active & Registered Workers[/bold cyan]', border_style='cyan', header_style='bold magenta'
        )
        table.add_column('Key', style='bold')
        table.add_column('Type')
        table.add_column('Status', justify='center')
        table.add_column('PID', justify='right', style='green')

        for w in workers:
          status = w['status']
          status_style = 'green' if status == 'RUNNING' else 'yellow'
          if status in ['CRASHED', 'FAILED']:
            status_style = 'bold red'
          elif status == 'STOPPED':
            status_style = 'dim'

          table.add_row(
            w['worker_key'],
            w['worker_type'],
            f'[{status_style}]{status}[/{status_style}]',
            str(w['pid']) if w['pid'] else '-',
          )
        console.print(table)

    elif args.command == 'stop':
      success, message = manager.stop_worker(args.worker_key)
      if success:
        console.print(f'[bold green]Success:[/bold green] {message}')
      else:
        err_console.print(f'[bold red]Error:[/bold red] {message}')
        sys.exit(1)
  finally:
    manager.dispose()


if __name__ == '__main__':
  main()
