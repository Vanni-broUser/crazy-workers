import json
import os
import re
import sys
from datetime import datetime
from rich.panel import Panel
from rich.table import Table

from ..ui import console


def show_status(client, workers_dir, json_mode=False):
  """Observability hub: the target state store plus the worker table (desired vs actual)."""
  workers = _merge_with_filesystem(client.list(), workers_dir)

  if json_mode:
    sys.stdout.write(json.dumps({'workers': workers}) + '\n')
    return workers

  console().print(_build_header(workers_dir))
  if not workers:
    console().print('[yellow]No workers found.[/yellow]')
    return workers

  console().print(_build_table(workers))
  return workers


def _build_header(workers_dir):
  db_url = os.environ.get('CRAZY_WORKERS_DB_URL')
  if db_url:
    target = f'[green]shared DB[/green] [dim]({_redact(db_url)})[/dim]'
  else:
    target = '[dim]self-contained SQLite (.service/workers.db)[/dim]'
  dir_label = workers_dir if workers_dir else '[dim](not set — scripts not listed)[/dim]'
  body = f'[bold]Workers dir:[/bold] {dir_label}\n[bold]State store:[/bold] {target}'
  return Panel.fit(body, border_style='cyan', title='[bold cyan]Crazy Workers status[/bold cyan]')


def _redact(db_url):
  """Hide the password in a SQLAlchemy URL for display."""
  return re.sub(r'://([^:/@]+):[^@]*@', r'://\1:***@', db_url)


def _merge_with_filesystem(db_workers, workers_dir):
  """Append NEVER_STARTED rows for worker scripts that have no DB record yet."""
  results = list(db_workers)
  if not workers_dir:
    # No dir resolved (shared-DB mode without CRAZY_WORKERS_DIR): nothing to scan.
    return results
  registered_types = {w['worker_type'] for w in results}
  try:
    available = sorted({f[:-3] for f in os.listdir(workers_dir) if f.endswith('.py') and f != '__init__.py'})
  except OSError:
    available = []
  for worker_type in available:
    if worker_type not in registered_types:
      results.append(
        {
          'worker_key': None,
          'worker_type': worker_type,
          'parameters': {},
          'desired_status': None,
          'pid': None,
          'status': 'NEVER_STARTED',
          'last_started_at': None,
          'last_stopped_at': None,
        }
      )
  return results


def _build_table(workers):
  table = Table(
    title='[bold cyan]Workers — desired vs actual[/bold cyan]', border_style='cyan', header_style='bold magenta'
  )
  table.add_column('#', justify='right', style='dim')
  table.add_column('Key', style='bold')
  table.add_column('Type')
  table.add_column('Desired', justify='center')
  table.add_column('Status', justify='center')
  table.add_column('PID', justify='right', style='green')
  table.add_column('Last Action', justify='center')
  table.add_column('Params', overflow='ellipsis')

  for i, w in enumerate(workers, 1):
    status = w['status']
    status_style = 'green' if status == 'RUNNING' else 'yellow'
    if status in ('CRASHED', 'FAILED'):
      status_style = 'bold red'
    elif status == 'STOPPED':
      status_style = 'dim'
    elif status == 'NEVER_STARTED':
      status_style = 'cyan'

    desired = w.get('desired_status') or '-'
    desired_style = 'green' if desired == 'RUNNING' else 'dim'

    last_action = '-'
    if status == 'RUNNING' and w.get('last_started_at'):
      dt = datetime.fromisoformat(w['last_started_at'])
      last_action = f'[green]Started {dt.strftime("%H:%M:%S")}[/green]'
    elif w.get('last_stopped_at'):
      dt = datetime.fromisoformat(w['last_stopped_at'])
      last_action = f'[dim]Stopped {dt.strftime("%H:%M:%S")}[/dim]'

    params_str = json.dumps(w['parameters']) if w['parameters'] else '-'
    if len(params_str) > 30:
      params_str = params_str[:27] + '...'

    table.add_row(
      str(i),
      w['worker_key'] or '-',
      w['worker_type'],
      f'[{desired_style}]{desired}[/{desired_style}]',
      f'[{status_style}]{status}[/{status_style}]',
      str(w['pid']) if w['pid'] else '-',
      last_action,
      params_str,
    )
  return table
