import json
import sys
import time


def main():
  if len(sys.argv) > 1:
    params = json.loads(sys.argv[1])
  else:
    params = {}

  steps = params.get('steps', 10)
  fail_at = params.get('fail_at', -1)  # Step to simulate failure

  sys.stdout.write(f'Starting simulation: {steps} steps, fail_at={fail_at}\n')
  sys.stdout.flush()

  for i in range(1, steps + 1):
    if i == fail_at:
      sys.stdout.write(f'Step {i}: simulating failure\n')
      sys.stdout.flush()
      sys.exit(1)

    sys.stdout.write(f'Step {i}/{steps}: OK\n')
    sys.stdout.flush()
    time.sleep(1)

  sys.stdout.write('Simulation completed successfully.\n')
  sys.stdout.flush()


if __name__ == '__main__':
  main()
