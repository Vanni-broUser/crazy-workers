import logging
import signal
import time

from crazy_workers import parse_params


running = True


def signal_handler(signum, frame):
  global running
  logging.info(f'Received signal {signum}. Shutting down gracefully...')
  running = False


def main():
  global running
  running = True

  signal.signal(signal.SIGTERM, signal_handler)
  signal.signal(signal.SIGINT, signal_handler)

  params = parse_params()
  duration = params.get('duration', 60)
  worker_key = params.get('worker_key', 'unknown')

  logging.info(f'Worker {worker_key} starting. Will run for {duration} seconds.')

  start_time = time.time()
  while running and (time.time() - start_time < duration):
    # Simulate work
    time.sleep(1)

  if not running:
    logging.info(f'Worker {worker_key} stopped by signal.')
  else:
    logging.info(f'Worker {worker_key} completed its task.')


if __name__ == '__main__':
  main()
