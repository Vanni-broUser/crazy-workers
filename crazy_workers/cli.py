import argparse
import os
import sys

from crazy_workers import WorkerManager


def load_env():
  """Loads variables from .env file into os.environ."""
  if os.path.exists('.env'):
    try:
      with open('.env', 'r') as f:
        for line in f:
          line = line.strip()
          if not line or line.startswith('#'):
            continue
          if '=' in line:
            key, value = line.split('=', 1)
            os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))
    except Exception:
      pass


def save_to_env(key, value):
  """Saves a key-value pair to .env file."""
  lines = []
  if os.path.exists('.env'):
    try:
      with open('.env', 'r') as f:
        lines = f.readlines()
    except Exception:
      pass

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

  with open('.env', 'w') as f:
    f.writelines(lines)


def resolve_workers_dir(flag_dir):
  load_env()

  # 1. Flag priority (if provided explicitly in argv)
  if flag_dir:
    if os.path.isdir(flag_dir):
      return flag_dir
    else:
      sys.stderr.write(f'Error: Directory "{flag_dir}" does not exist.\n')
      sys.exit(1)

  # 2. Environment Variable
  env_dir = os.environ.get('CRAZY_WORKERS_DIR')
  if env_dir:
    if os.path.isdir(env_dir):
      return env_dir
    else:
      sys.stderr.write(f'Error: Directory "{env_dir}" (from CRAZY_WORKERS_DIR) does not exist.\n')
      sys.exit(1)

  # 3. Interactive Prompt (if in a TTY)
  if sys.stdin.isatty():
    sys.stdout.write('CRAZY_WORKERS_DIR not set in environment.\n')
    sys.stdout.write('Please enter the path to your workers directory: ')
    sys.stdout.flush()
    user_input = sys.stdin.readline().strip()
    if user_input:
      if os.path.isdir(user_input):
        abs_path = os.path.abspath(user_input)
        try:
          save_to_env('CRAZY_WORKERS_DIR', abs_path)
          sys.stdout.write(f'Saved CRAZY_WORKERS_DIR={abs_path} to .env\n')
        except Exception as e:
          sys.stderr.write(f'Failed to save configuration: {e}\n')
        return abs_path
      else:
        sys.stderr.write(f'Error: "{user_input}" is not a valid directory.\n')
        sys.exit(1)

  # 4. Local workers/ folder auto-detection (fallback)
  if os.path.isdir('workers'):
    return 'workers'

  sys.stderr.write(
    'Error: Workers directory not found. Please provide it via --workers-dir or set CRAZY_WORKERS_DIR.\n'
  )
  sys.exit(1)


def main():
  parser = argparse.ArgumentParser(description='Crazy Workers CLI')
  parser.add_argument('--workers-dir', help='Directory containing worker scripts')

  subparsers = parser.add_subparsers(dest='command', help='Commands')

  # List command
  subparsers.add_parser('list', help='List all workers and their status')

  # Stop command
  stop_parser = subparsers.add_parser('stop', help='Stop a worker')
  stop_parser.add_argument('worker_key', help='The key of the worker to stop')

  args = parser.parse_args()

  if not args.command:
    parser.print_help()
    sys.exit(1)

  workers_dir = resolve_workers_dir(args.workers_dir)
  try:
    manager = WorkerManager(workers_dir, create_dir=False)
  except ValueError as e:
    sys.stderr.write(f'Error: {e}\n')
    sys.exit(1)

  try:
    if args.command == 'list':
      import json

      workers = manager.list_workers()
      sys.stdout.write(json.dumps(workers, indent=2) + '\n')

    elif args.command == 'stop':
      success, message = manager.stop_worker(args.worker_key)
      if success:
        sys.stdout.write(f'Success: {message}\n')
      else:
        sys.stderr.write(f'Error: {message}\n')
        sys.exit(1)
  finally:
    manager.dispose()


if __name__ == '__main__':
  main()
