import logging
import sys
import time

from crazy_workers import parse_params


def main():
  params = parse_params()
  steps = params.get('steps', 10)
  fail_at = params.get('fail_at', -1)

  logging.info(f'Starting simulation: {steps} steps, fail_at={fail_at}')

  for i in range(1, steps + 1):
    if i == fail_at:
      logging.error(f'Step {i}: simulating failure')
      sys.exit(1)

    logging.info(f'Step {i}/{steps}: OK')
    time.sleep(1)

  logging.info('Simulation completed successfully.')


if __name__ == '__main__':
  main()
