import json
import logging
import sys
import time


def main():
  params = json.loads(sys.argv[1]) if len(sys.argv) > 1 else {}
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
