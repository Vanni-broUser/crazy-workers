import logging
import time

from crazy_workers import parse_params


def main():
  params = parse_params()
  items = params.get('items', ['task1', 'task2', 'task3'])
  delay = params.get('delay', 2)

  logging.info(f'Starting batch processing of {len(items)} items...')

  for i, item in enumerate(items, 1):
    logging.info(f'[{i}/{len(items)}] Processing: {item}')
    time.sleep(delay)

  logging.info('Batch processing completed successfully.')


if __name__ == '__main__':
  main()
