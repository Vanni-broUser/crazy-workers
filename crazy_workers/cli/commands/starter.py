import os
from rich.console import Console
from rich.prompt import IntPrompt


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
