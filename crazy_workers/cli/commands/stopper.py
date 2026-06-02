from rich.prompt import IntPrompt

from ..ui import console, err_console


def stop_worker(manager, worker_key):

  if not worker_key:
    # Interactive mode
    workers = manager.list_workers()
    running_workers = [w for w in workers if w['status'] == 'RUNNING']

    if not running_workers:
      console().print('[yellow]No running workers to stop.[/yellow]')
      return False

    console().print('\n[bold cyan]Select a worker to stop:[/bold cyan]')
    for i, w in enumerate(running_workers, 1):
      console().print(f'  [bold]{i})[/bold] {w["worker_key"]} [dim]({w["worker_type"]})[/dim]')

    choice = IntPrompt.ask('Enter the number', choices=[str(i) for i in range(1, len(running_workers) + 1)])
    worker_key = running_workers[choice - 1]['worker_key']

  success, message = manager.stop_worker(worker_key)
  if success:
    console().print(f'[bold green]Success:[/bold green] {message}')
  else:
    err_console().print(f'[bold red]Error:[/bold red] {message}')
    return False
  return True
