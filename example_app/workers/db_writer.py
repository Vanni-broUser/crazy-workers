"""Demo worker that uses the host backend's database.

It does NOT receive a live connection (that cannot cross a process boundary).
Instead crazy_workers injects the connection URL via worker_env as DATABASE_URL,
and the worker opens its own connection to it.
"""

import json
import os
import sys
import time
from datetime import datetime, timezone
from sqlalchemy import create_engine, text


def main():
  params = json.loads(sys.argv[1]) if len(sys.argv) > 1 else {}
  worker_key = params.get('worker_key', 'db_writer')
  iterations = params.get('iterations', 3)
  interval = params.get('interval', 1)

  db_url = os.environ.get('DATABASE_URL')
  if not db_url:
    sys.exit('DATABASE_URL not provided (expected via crazy_workers worker_env)')

  engine = create_engine(db_url)
  with engine.begin() as conn:
    conn.execute(text('CREATE TABLE IF NOT EXISTS worker_events (worker_key TEXT, note TEXT, created_at TEXT)'))

  for i in range(iterations):
    with engine.begin() as conn:
      conn.execute(
        text('INSERT INTO worker_events (worker_key, note, created_at) VALUES (:k, :n, :t)'),
        {'k': worker_key, 'n': f'tick {i}', 't': datetime.now(timezone.utc).isoformat()},
      )
    time.sleep(interval)

  engine.dispose()


if __name__ == '__main__':
  main()
