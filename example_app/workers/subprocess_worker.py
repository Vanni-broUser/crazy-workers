"""
Worker used in tests: spawns a long-running child subprocess and writes
its PID to a file so tests can verify it is cleaned up on stop_worker().
"""

import json
import subprocess
import sys
import time


def main():
  params = json.loads(sys.argv[1]) if len(sys.argv) > 1 else {}
  pid_file = params.get('pid_file', '')

  child = subprocess.Popen(
    [sys.executable, '-c', 'import time; time.sleep(3600)'],
    stdout=subprocess.DEVNULL,
    stderr=subprocess.DEVNULL,
  )

  if pid_file:
    with open(pid_file, 'w') as f:
      f.write(str(child.pid))

  try:
    while True:
      time.sleep(1)
  except (KeyboardInterrupt, SystemExit):
    pass
  finally:
    try:
      child.terminate()
      child.wait(timeout=3)
    except Exception:
      pass


if __name__ == '__main__':
  main()
