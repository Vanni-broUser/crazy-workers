from rich.prompt import IntPrompt

from ..ui import console, err_console


def stop_worker(client, worker_key):
  """Request a worker to stop. The daemon performs the actual termination."""
  if not worker_key:
    # Interactive mode: offer the workers a stop is meaningful for.
    candidates = [w for w in client.list() if w['desired_status'] == 'RUNNING']

    if not candidates:
      console().print('[yellow]No workers desired RUNNING to stop.[/yellow]')
      return False

    console().print('\n[bold cyan]Select a worker to stop:[/bold cyan]')
    for i, w in enumerate(candidates, 1):
      console().print(f'  [bold]{i})[/bold] {w["worker_key"]} [dim]({w["worker_type"]}, {w["status"]})[/dim]')

    choice = IntPrompt.ask('Enter the number', choices=[str(i) for i in range(1, len(candidates) + 1)])
    worker_key = candidates[choice - 1]['worker_key']

  if client.request_stop(worker_key):
    console().print(f'[bold green]Requested:[/bold green] worker {worker_key} set to STOPPED (the daemon will stop it)')
    return True

  err_console().print(f'[bold red]Error:[/bold red] Worker {worker_key} not found')
  return False
