import json
import sys
import time


def main():
  if len(sys.argv) > 1:
    params = json.loads(sys.argv[1])
  else:
    params = {}

  items = params.get('items', ['task1', 'task2', 'task3'])
  delay = params.get('delay', 2)

  sys.stdout.flush()

  for i, item in enumerate(items, 1):
    sys.stdout.flush()
    time.sleep(delay)

  sys.stdout.flush()


if __name__ == '__main__':
  main()
