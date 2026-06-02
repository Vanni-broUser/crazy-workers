import json
import logging
import signal
import sys
import time


running = True


def signal_handler(signum, frame):
  global running
  logging.info(f'Received signal {signum}. Shutting down gracefully...')
  running = False


# Register signal handlers for graceful shutdown
signal.signal(signal.SIGTERM, signal_handler)
signal.signal(signal.SIGINT, signal_handler)


def main():
  if len(sys.argv) < 2:
    logging.error('Missing parameters')
    return

  params = json.loads(sys.argv[1])
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
