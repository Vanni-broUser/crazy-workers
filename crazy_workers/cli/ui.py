from rich.console import Console


def console() -> Console:
  return Console()


def err_console() -> Console:
  return Console(stderr=True)
