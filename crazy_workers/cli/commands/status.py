import json
import os
import re
import sys
from datetime import datetime
from rich.panel import Panel
from rich.table import Table

from ...core.engine import resolve_system_pid
from ..ui import console


MAX_STOPPED_ROWS = 2


def show_status(client, workers_dir, json_mode=False, show_all=False):
  """Observability hub: the target state store plus the worker table.

  The table shows each worker's effective status; when it diverges from the
  desired state (a stop or restart the daemon has not resolved yet) the row
  carries a pending note. Settled stopped workers beyond the most recent
  ``MAX_STOPPED_ROWS`` are hidden unless ``show_all`` is set. JSON mode always
  emits every worker, including the ``desired_status`` field.
  """
  workers = _with_system_pids(_merge_with_filesystem(client.list(), workers_dir))

  if json_mode:
    sys.stdout.write(json.dumps({'workers': workers}) + '\n')
    return workers

  console().print(_build_header(workers_dir))
  if not workers:
    console().print('[yellow]No workers found.[/yellow]')
    return workers

  visible, hidden = (workers, 0) if show_all else _truncate_stopped(workers)
  console().print(_build_table(visible, hidden))
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


def _with_system_pids(workers):
  results = []
  for worker in workers:
    enriched = dict(worker)
    enriched['system_pid'] = resolve_system_pid(enriched.get('pid'), worker_key=enriched.get('worker_key'))
    results.append(enriched)
  return results


def _truncate_stopped(workers):
  """Keep the MAX_STOPPED_ROWS most recently stopped settled rows, hide the rest."""
  hideable = [w for w in workers if _is_settled_stop(w)]
  hidden = len(hideable) - MAX_STOPPED_ROWS
  if hidden <= 0:
    return workers, 0
  recent = sorted(hideable, key=lambda w: w.get('last_stopped_at') or '', reverse=True)[:MAX_STOPPED_ROWS]
  keep = {id(w) for w in recent}
  return [w for w in workers if not _is_settled_stop(w) or id(w) in keep], hidden


def _is_settled_stop(worker):
  """STOPPED with no pending restart: history, not activity."""
  return worker['status'] == 'STOPPED' and worker.get('desired_status') != 'RUNNING'


def _pending_note(worker):
  """The desired/actual divergence the daemon still has to resolve, if any."""
  desired, status = worker.get('desired_status'), worker['status']
  if desired == 'STOPPED' and status in ('RUNNING', 'STARTING'):
    return 'stop requested'
  if desired == 'RUNNING' and status == 'STOPPED':
    return 'start pending'
  if desired == 'RUNNING' and status in ('CRASHED', 'FAILED'):
    return 'restart pending'
  return None


def _format_status(worker):
  status = worker['status']
  status_style = 'green' if status == 'RUNNING' else 'yellow'
  if status in ('CRASHED', 'FAILED'):
    status_style = 'bold red'
  elif status == 'STOPPED':
    status_style = 'dim'
  elif status == 'NEVER_STARTED':
    status_style = 'cyan'

  cell = f'[{status_style}]{status}[/{status_style}]'
  note = _pending_note(worker)
  if note:
    cell += f' [dim]({note})[/dim]'
  return cell


def _format_pid(worker):
  pid = worker.get('pid')
  system_pid = worker.get('system_pid')
  if not pid:
    return '-'
  if system_pid and system_pid != pid:
    return f'{system_pid} [dim](ns {pid})[/dim]'
  return str(pid)


def _build_table(workers, hidden=0):
  table = Table(title='[bold cyan]Workers[/bold cyan]', border_style='cyan', header_style='bold magenta')
  if hidden:
    plural = 's' if hidden != 1 else ''
    table.caption = f'… {hidden} more stopped worker{plural} hidden — use [bold]--all[/bold] to show them'
    table.caption_style = 'dim italic'
  table.add_column('#', justify='right', style='dim')
  table.add_column('Key', style='bold')
  table.add_column('Type')
  table.add_column('Status', justify='center')
  table.add_column('PID', justify='right', style='green')
  table.add_column('Last Action', justify='center')
  table.add_column('Params', overflow='ellipsis')

  for i, w in enumerate(workers, 1):
    last_action = '-'
    if w['status'] == 'RUNNING' and w.get('last_started_at'):
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
      _format_status(w),
      _format_pid(w),
      last_action,
      params_str,
    )
  return table
