from ..ui import console


def restore_workers(manager):
  restarted = manager.recover_workers()

  if restarted:
    console().print(f'[bold green]Successfully restored {len(restarted)} workers:[/bold green]')
    for key in restarted:
      console().print(f'  - {key}')
    return True
  else:
    console().print('[yellow]No workers needed restoration.[/yellow]')
    return True
