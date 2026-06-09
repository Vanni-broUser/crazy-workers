import json
from rich.prompt import IntPrompt

from ..ui import console, err_console


def show_params(manager, worker_key):

  workers = manager.list_workers()
  if not workers:
    console().print('[yellow]No workers found.[/yellow]')
    return False

  if not worker_key:
    # Interactive mode
    active_workers = [w for w in workers if w['worker_key'] is not None]

    if not active_workers:
      console().print('[yellow]No registered workers to show parameters for.[/yellow]')
      return False

    console().print('\n[bold cyan]Select a worker to show parameters:[/bold cyan]')
    for i, w in enumerate(active_workers, 1):
      status_style = 'green' if w['status'] == 'RUNNING' else 'dim'
      console().print(f'  [bold]{i})[/bold] {w["worker_key"]} [{status_style}]({w["status"]})[/{status_style}]')

    choice = IntPrompt.ask('Enter the number', choices=[str(i) for i in range(1, len(active_workers) + 1)])
    selected_worker = active_workers[choice - 1]
  else:
    selected_worker = next((w for w in workers if w['worker_key'] == worker_key), None)
    if not selected_worker:
      err_console().print(f'[bold red]Error:[/bold red] Worker {worker_key} not found')
      return False

  console().print(f'\n[bold cyan]Parameters for worker:[/bold cyan] {selected_worker["worker_key"]}')
  console().print_json(json.dumps(selected_worker['parameters']))
  return True
