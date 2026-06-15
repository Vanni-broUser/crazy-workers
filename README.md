# Crazy Workers

A Python library for managing background worker processes with persistent state, automatic crash recovery, and a built-in CLI.

[![Python 3.10+](https://img.shields.io/badge/python-3.10+-blue.svg)](https://www.python.org/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

## Features

- **Persistent State** — SQLite database tracks worker status, PIDs, and parameters across restarts.
- **Process Management** — Start, stop, and monitor background Python scripts as independent OS processes.
- **Automatic Recovery** — Detects crashed workers and restarts them on application boot.
- **Child Process Control** — On stop, terminates unmanaged subprocesses while preserving independently-managed nested workers.
- **CLI Interface** — Manage workers from the terminal with interactive prompts and auto-discovery (see [CLI.md](https://github.com/Vanni-broUser/crazy-workers/blob/main/CLI.md)).
- **Security** — Worker types and keys are restricted to a safe identifier charset (`A-Z a-z 0-9 _ -`), with a defence-in-depth check that the resolved script path stays inside the workers directory. This blocks path traversal on both Unix and Windows (including drive-relative names like `c:evil`).
- **Observability** — Per-worker file logging; all service files (DB, lock, logs) live in a `.service/` folder inside your workers directory.
- **Zombie Protection** — Distinguishes active processes from zombies using `psutil`.
- **PID-Reuse Safe** — Each worker is tagged with an identity token on its command line; recovery and stop confirm a PID still belongs to the worker before acting, so a recycled PID is never mistaken for (or worse, killed as) a live worker. Works on both Unix and Windows.
- **Gunicorn-safe** — File-based lock prevents concurrent recovery runs across multiple workers.

## Installation

```bash
pip install crazy-workers
```

Or from source:

```bash
git clone https://github.com/Vanni-broUser/crazy-workers
cd crazy-workers
pip install .
```

## Quick Start

### 1. Create a worker script

```python
# workers/my_worker.py
import json, sys, time

params = json.loads(sys.argv[1]) if len(sys.argv) > 1 else {}
duration = params.get('duration', 60)

for _ in range(duration):
    time.sleep(1)
```

### 2. Manage it from Python

```python
from crazy_workers import WorkerManager

manager = WorkerManager('workers')

# Start
success, result = manager.start_worker(
    'my_worker',
    worker_key='job_1',
    parameters={'duration': 30},
)
print(result['pid'])   # OS process ID
print(result['status'])  # 'RUNNING'

# List
for w in manager.list_workers():
    print(w['worker_key'], w['status'])

# Stop
manager.stop_worker('job_1')

# Recover crashed workers (call on app startup)
restarted = manager.recover_workers()

manager.dispose()  # releases DB connection; does NOT kill workers
```

### 3. Or from the CLI

```bash
crazy-workers list
crazy-workers start my_worker --key job_1 --params '{"duration": 30}'
crazy-workers stop job_1
crazy-workers restore
```

See [CLI.md](https://github.com/Vanni-broUser/crazy-workers/blob/main/CLI.md) for full CLI documentation.

## API Reference

### `WorkerManager(workers_dir, create_dir=True)`

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `workers_dir` | `str` | `'workers'` | Directory containing worker `.py` scripts |
| `create_dir` | `bool` | `True` | Create `workers_dir` and `.service/` if they don't exist |

### `start_worker(worker_type, worker_key=None, parameters=None, env=None)`

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `worker_type` | `str` | — | Filename (without `.py`) of the worker script |
| `worker_key` | `str` | `worker_type` | Unique identifier; allows multiple instances of the same type |
| `parameters` | `dict` | `{}` | JSON-serializable dict passed as `sys.argv[1]` to the worker |
| `env` | `dict` | `None` | Extra environment variables injected into the worker process |

Returns `(bool, dict | str)` — `(True, worker_dict)` on success, `(False, error_message)` on failure.

> **Note on `RUNNING`:** success means the worker was *spawned* and survived a brief startup grace period that catches immediate launch failures (bad import, missing module). It does **not** guarantee the worker will run to completion — a worker that fails later is still reported `RUNNING` until the next `list_workers()` / `recover_workers()` reconciles its state.

### `stop_worker(worker_key)`

Gracefully terminates the worker (SIGTERM → SIGKILL after timeout). Returns `(bool, str)`.

### `list_workers()`

Returns a list of worker dicts including RUNNING, STOPPED, CRASHED, and NEVER_STARTED (filesystem-discovered) workers.

### `recover_workers()`

Restarts any worker whose DB status is RUNNING but whose process is dead. Uses a file lock to prevent concurrent recovery. Returns a list of restarted keys.

### `dispose()`

Closes the database connection and clears internal process references. Does **not** kill background workers — they continue running independently.

## Worker Script Contract

A worker receives its parameters as a JSON string in `sys.argv[1]`:

```python
import json, sys

params = json.loads(sys.argv[1]) if len(sys.argv) > 1 else {}
# ... do work ...
```

## Project Structure

```
crazy_workers/       # Library package
  core/              # WorkerManager, process engine, recovery lock
  cli/               # CLI entry point, commands, discovery
  database/          # SQLAlchemy schema and SQLite storage
example_app/         # Flask demo application
  app.py
  workers/           # Example worker scripts
tests/
  core/              # Unit tests for core modules
  cli/               # Unit tests for CLI modules
  database/          # Unit tests for storage layer
  integration/       # Full-stack integration tests (real processes)
  app/               # Tests for the example Flask app
```

## Flask Integration

> ⚠️ **Security:** `start_worker()` runs the worker script named by the caller. Exposing it over HTTP makes it a **privileged operation** — anyone who can reach the route can launch any script in your workers directory. Put such routes behind authentication, and prefer validating `worker_type` against a known allow-list of expected workers. The example below is a minimal demo with **no auth**.

```python
from crazy_workers import WorkerManager

def create_app():
    app = Flask(__name__)
    manager = WorkerManager('workers')

    @app.route('/workers/start', methods=['POST'])
    def start():
        data = request.json
        success, result = manager.start_worker(
            data['worker_type'],
            worker_key=data.get('worker_key'),
            parameters=data.get('parameters', {}),
        )
        return (jsonify(result), 200) if success else (jsonify({'error': result}), 400)

    manager.recover_workers()  # restart any crashed workers on boot
    return app
```

See [`example_app/app.py`](https://github.com/Vanni-broUser/crazy-workers/blob/main/example_app/app.py) for a complete example.

## Gunicorn / Multi-Process Servers

When using a pre-fork server like Gunicorn:

- **Recovery is atomic** — a file lock (`.service/workers.db.recovery.lock`) ensures `recover_workers()` runs once even when multiple workers boot simultaneously.
- **Workers outlive their parent** — if a Gunicorn worker is recycled, background processes keep running. The next recovery cycle re-attaches or restarts them.

## Logs

Each worker's stdout/stderr is appended to `.service/logs/<worker_key>.log`. These files are written directly by the worker process, so the library does **not** rotate them — they grow until you act. For long-lived deployments, rotate them externally (e.g. `logrotate` with `copytruncate`) or have your worker script configure its own `logging.handlers.RotatingFileHandler` instead of writing to stdout/stderr.

## Development

### Setup

```bash
git clone https://github.com/Vanni-broUser/crazy-workers
cd crazy-workers
pip install -e .[dev]
```

### Commands

```bash
# Lint and format
ruff check . --fix && ruff format .

# Run tests
pytest

# Run tests with coverage
coverage run -m pytest && coverage report
```

### Standards

See [AI.md](https://github.com/Vanni-broUser/crazy-workers/blob/main/AI.md) for the full coding and testing standards used in this project.

## Support the project ❤️

crazy-workers is free and open-source (MIT). If it saves you time or powers your work,
consider supporting its development:

- **GitHub Sponsors** — recurring or one-time, 0% platform fee: https://github.com/sponsors/Vanni-broUser
- **Stripe** — one-time card donation via secure checkout: _Stripe Payment Link (coming soon)_
- **⭐ Star the repo** — free, and it really helps visibility.

> The Stripe link is configured via a [Payment Link](https://stripe.com/docs/payment-links).
> Replace the placeholder above (and in [`.github/FUNDING.yml`](.github/FUNDING.yml)) with your real
> `https://buy.stripe.com/...` URL once created.
