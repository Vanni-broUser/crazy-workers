from rich.console import Console


def restore_workers(manager):
  console = Console()
  restarted = manager.recover_workers()

  if restarted:
    console.print(f'[bold green]Successfully restored {len(restarted)} workers:[/bold green]')
    for key in restarted:
      console.print(f'  - {key}')
    return True
  else:
    console.print('[yellow]No workers needed restoration.[/yellow]')
    return True
