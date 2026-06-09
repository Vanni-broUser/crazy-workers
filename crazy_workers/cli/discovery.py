import os
import sys
from rich.prompt import Prompt

from .ui import console, err_console


def load_env():
  """Loads variables from .env file into os.environ."""
  if not os.path.exists('.env'):
    return
  with open('.env', 'r') as f:
    for line in f:
      line = line.strip()
      if not line or line.startswith('#'):
        continue
      if '=' in line:
        key, value = line.split('=', 1)
        os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


def save_to_env(key, value):
  """Saves a key-value pair to .env file, using an atomic write."""
  lines = []
  if os.path.exists('.env'):
    with open('.env', 'r') as f:
      lines = f.readlines()

  found = False
  new_line = f'{key}={value}\n'
  for i, line in enumerate(lines):
    if line.strip().startswith(f'{key}='):
      lines[i] = new_line
      found = True
      break

  if not found:
    if lines and not lines[-1].endswith('\n'):
      lines.append('\n')
    lines.append(new_line)

  tmp = '.env.tmp'
  with open(tmp, 'w') as f:
    f.writelines(lines)
  os.replace(tmp, '.env')


def resolve_workers_dir(flag_dir):
  load_env()

  # 1. Flag priority
  if flag_dir:
    if os.path.isdir(flag_dir):
      return flag_dir
    else:
      err_console().print(f'[bold red]Error:[/bold red] Directory "{flag_dir}" does not exist.')
      sys.exit(1)

  # 2. Environment Variable
  env_dir = os.environ.get('CRAZY_WORKERS_DIR')
  if env_dir:
    if os.path.isdir(env_dir):
      return env_dir
    else:
      err_console().print(f'[bold red]Error:[/bold red] Directory "{env_dir}" (from CRAZY_WORKERS_DIR) does not exist.')
      sys.exit(1)

  # 3. Interactive Prompt
  if sys.stdin.isatty():
    console().print('[bold yellow]CRAZY_WORKERS_DIR not set in environment.[/bold yellow]')
    user_input = Prompt.ask('Please enter the path to your workers directory')
    if user_input:
      if os.path.isdir(user_input):
        abs_path = os.path.abspath(user_input)
        try:
          save_to_env('CRAZY_WORKERS_DIR', abs_path)
          console().print(f'[bold green]Saved CRAZY_WORKERS_DIR={abs_path} to .env[/bold green]')
        except Exception as e:
          err_console().print(f'[bold red]Failed to save configuration:[/bold red] {e}')
        return abs_path
      else:
        err_console().print(f'[bold red]Error:[/bold red] "{user_input}" is not a valid directory.')
        sys.exit(1)

  # 4. Fallback
  if os.path.isdir('workers'):
    return 'workers'

  err_console().print(
    '[bold red]Error:[/bold red] Workers directory not found. '
    'Please provide it via --workers-dir or set CRAZY_WORKERS_DIR.'
  )
  sys.exit(1)
