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

  sys.stdout.write(f'Starting batch processing of {len(items)} items...\n')
  sys.stdout.flush()

  for i, item in enumerate(items, 1):
    sys.stdout.write(f'[{i}/{len(items)}] Processing: {item}\n')
    sys.stdout.flush()
    time.sleep(delay)

  sys.stdout.write('Batch processing completed successfully.\n')
  sys.stdout.flush()


if __name__ == '__main__':
  main()
