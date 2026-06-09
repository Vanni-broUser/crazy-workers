import json
from datetime import datetime
from rich.table import Table

from ..ui import console


def list_workers(manager):
  workers = manager.list_workers()
  if not workers:
    console().print('[yellow]No workers found in database.[/yellow]')
    return []
  else:
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
    console().print(table)
    return workers
