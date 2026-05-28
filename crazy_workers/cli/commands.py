import os

from rich.console import Console
from rich.prompt import IntPrompt
from rich.table import Table


def list_workers(manager):
  console = Console()
  workers = manager.list_workers()
  if not workers:
    console.print('[yellow]No workers found in database.[/yellow]')
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

    for i, w in enumerate(workers, 1):
      status = w['status']
      status_style = 'green' if status == 'RUNNING' else 'yellow'
      if status in ['CRASHED', 'FAILED']:
        status_style = 'bold red'
      elif status == 'STOPPED':
        status_style = 'dim'

      table.add_row(
        str(i),
        w['worker_key'],
        w['worker_type'],
        f'[{status_style}]{status}[/{status_style}]',
        str(w['pid']) if w['pid'] else '-',
      )
    console.print(table)
    return workers


def stop_worker(manager, worker_key):
  console = Console()
  err_console = Console(stderr=True)

  if not worker_key:
    # Interactive mode
    workers = manager.list_workers()
    running_workers = [w for w in workers if w['status'] == 'RUNNING']

    if not running_workers:
      console.print('[yellow]No running workers to stop.[/yellow]')
      return False

    console.print('\n[bold cyan]Select a worker to stop:[/bold cyan]')
    for i, w in enumerate(running_workers, 1):
      console.print(f'  [bold]{i})[/bold] {w["worker_key"]} [dim]({w["worker_type"]})[/dim]')

    choice = IntPrompt.ask('Enter the number', choices=[str(i) for i in range(1, len(running_workers) + 1)])
    worker_key = running_workers[choice - 1]['worker_key']

  success, message = manager.stop_worker(worker_key)
  if success:
    console.print(f'[bold green]Success:[/bold green] {message}')
  else:
    err_console.print(f'[bold red]Error:[/bold red] {message}')
    return False
  return True


def start_worker(manager, worker_type, worker_key=None, parameters=None):
  console = Console()
  err_console = Console(stderr=True)

  if not worker_type:
    # Interactive mode: list .py files in workers_dir
    try:
      files = [f[:-3] for f in os.listdir(manager.workers_dir) if f.endswith('.py')]
    except Exception as e:
      err_console.print(f'[bold red]Error reading workers directory:[/bold red] {e}')
      return False

    if not files:
      console.print(f'[yellow]No worker scripts found in {manager.workers_dir}[/yellow]')
      return False

    console.print('\n[bold cyan]Select a worker type to start:[/bold cyan]')
    for i, f in enumerate(files, 1):
      console.print(f'  [bold]{i})[/bold] {f}')

    choice = IntPrompt.ask('Enter the number', choices=[str(i) for i in range(1, len(files) + 1)])
    worker_type = files[choice - 1]

  success, result = manager.start_worker(worker_type, worker_key=worker_key, parameters=parameters)
  if success:
    console.print('[bold green]Success:[/bold green] Worker started')
    console.print(f'  [bold]Key:[/bold] {result["worker_key"]}')
    console.print(f'  [bold]PID:[/bold] {result["pid"]}')
  else:
    err_console.print(f'[bold red]Error:[/bold red] {result}')
    return False
  return True
