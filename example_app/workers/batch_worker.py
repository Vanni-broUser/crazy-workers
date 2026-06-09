import json
import logging
import sys
import time


def main():
  params = json.loads(sys.argv[1]) if len(sys.argv) > 1 else {}
  items = params.get('items', ['task1', 'task2', 'task3'])
  delay = params.get('delay', 2)

  logging.info(f'Starting batch processing of {len(items)} items...')

  for i, item in enumerate(items, 1):
    logging.info(f'[{i}/{len(items)}] Processing: {item}')
    time.sleep(delay)

  logging.info('Batch processing completed successfully.')


if __name__ == '__main__':
  main()
