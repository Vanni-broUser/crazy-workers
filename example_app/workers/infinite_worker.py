import json
import sys
import time


def main():
  if len(sys.argv) > 1:
    params = json.loads(sys.argv[1])
  else:
    params = {}

  interval = params.get('interval', 5)
  params.get('message', 'Infinite worker pulsing...')

  sys.stdout.flush()

  try:
    while True:
      sys.stdout.flush()
      time.sleep(interval)
  except KeyboardInterrupt:
    pass
  except Exception:
    sys.exit(1)


if __name__ == '__main__':
  main()
