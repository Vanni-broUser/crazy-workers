import json
import sys
import time


def main():
  if len(sys.argv) > 1:
    params = json.loads(sys.argv[1])
  else:
    params = {}

  interval = params.get('interval', 5)
  message = params.get('message', 'Infinite worker pulsing...')

  # Use sys.stdout.write to bypass ruff T201 if needed, or just use print and ignore lint for examples
  sys.stdout.write(f'Starting infinite worker with interval {interval}s\n')
  sys.stdout.flush()

  try:
    while True:
      sys.stdout.write(f'[{time.strftime("%H:%M:%S")}] {message}\n')
      sys.stdout.flush()
      time.sleep(interval)
  except KeyboardInterrupt:
    sys.stdout.write('Infinite worker received interrupt, exiting...\n')
    sys.stdout.flush()
  except Exception as e:
    sys.stderr.write(f'Infinite worker error: {e}\n')
    sys.stderr.flush()
    sys.exit(1)


if __name__ == '__main__':
  main()
