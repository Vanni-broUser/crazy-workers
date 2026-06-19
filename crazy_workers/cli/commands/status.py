import json
from datetime import datetime
from rich.panel import Panel
from rich.table import Table

from ...boot import boot_state
from ..ui import console


def show_status(manager):
  """Observability hub: boot-restore state plus the worker table."""
  console().print(_build_header(manager))

  workers = manager.list_workers()
  if not workers:
    console().print('[yellow]No workers found in database.[/yellow]')
    return workers

  console().print(_build_table(workers))
  return workers


def _build_header(manager):
  state = boot_state(manager.workers_dir, provider=manager._boot_provider)
  if state.mechanism == 'disabled':
    boot_line = '[dim]boot-restore: disabled[/dim]'
  elif not state.supported:
    boot_line = '[dim]boot-restore: not supported on this platform[/dim]'
  elif state.installed:
    boot_line = f'[green]boot-restore: enabled[/green] [dim]({state.mechanism}, {state.detail})[/dim]'
  else:
    reason = f' — {state.detail}' if state.detail else ''
    boot_line = f'[yellow]boot-restore: not installed[/yellow][dim]{reason}[/dim]'

  body = f'[bold]Workers dir:[/bold] {manager.workers_dir}\n{boot_line}'
  return Panel.fit(body, border_style='cyan', title='[bold cyan]Crazy Workers status[/bold cyan]')


def _build_table(workers):
  table = Table(
    title='[bold cyan]Active & Registered Workers[/bold cyan]', border_style='cyan', header_style='bold magenta'
  )
  table.add_column('#', justify='right', style='dim')
  table.add_column('Key', style='bold')
  table.add_column('Type')
  table.add_column('Status', justify='center')
  table.add_column('PID', justify='right', style='green')
  table.add_column('Last Action', justify='center')
  table.add_column('Params', overflow='ellipsis')

  for i, w in enumerate(workers, 1):
    status = w['status']
    status_style = 'green' if status == 'RUNNING' else 'yellow'
    if status in ['CRASHED', 'FAILED']:
      status_style = 'bold red'
    elif status == 'STOPPED':
      status_style = 'dim'
    elif status == 'NEVER_STARTED':
      status_style = 'cyan'

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
      f'[{status_style}]{status}[/{status_style}]',
      str(w['pid']) if w['pid'] else '-',
      last_action,
      params_str,
    )
  return table
