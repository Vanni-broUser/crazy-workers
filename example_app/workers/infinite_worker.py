import json
import logging
import sys
import time


def main():
  params = json.loads(sys.argv[1]) if len(sys.argv) > 1 else {}
  interval = params.get('interval', 5)
  message = params.get('message', 'Infinite worker pulsing...')

  logging.info(f'Starting infinite worker with interval {interval}s')

  try:
    while True:
      logging.info(f'[{time.strftime("%H:%M:%S")}] {message}')
      time.sleep(interval)
  except KeyboardInterrupt:
    logging.info('Infinite worker received interrupt, exiting...')
  except Exception as e:
    logging.error(f'Infinite worker error: {e}')
    sys.exit(1)


if __name__ == '__main__':
  main()
