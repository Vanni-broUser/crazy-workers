from rich.console import Console
from rich.table import Table


def list_workers(manager):
  console = Console()
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


def stop_worker(manager, worker_key):
  console = Console()
  err_console = Console(stderr=True)
  success, message = manager.stop_worker(worker_key)
  if success:
    console.print(f'[bold green]Success:[/bold green] {message}')
  else:
    err_console.print(f'[bold red]Error:[/bold red] {message}')
    return False
  return True
