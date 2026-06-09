# Crazy Workers

A Python library for managing background worker processes with persistent state, automatic crash recovery, and a built-in CLI.

[![Python 3.10+](https://img.shields.io/badge/python-3.10+-blue.svg)](https://www.python.org/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

## Features

- **Persistent State** — SQLite database tracks worker status, PIDs, and parameters across restarts.
- **Process Management** — Start, stop, and monitor background Python scripts as independent OS processes.
- **Automatic Recovery** — Detects crashed workers and restarts them on application boot.
- **Child Process Control** — On stop, terminates unmanaged subprocesses while preserving independently-managed nested workers.
- **CLI Interface** — Manage workers from the terminal with interactive prompts and auto-discovery (see [CLI.md](CLI.md)).
- **Security** — Built-in protection against path traversal in worker type and key names.
- **Observability** — Per-worker file logging; all service files (DB, lock, logs) live in a `.service/` folder inside your workers directory.
- **Zombie Protection** — Distinguishes active processes from zombies using `psutil`.
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

See [CLI.md](CLI.md) for full CLI documentation.

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

See `example_app/app.py` for a complete example.

## Gunicorn / Multi-Process Servers

When using a pre-fork server like Gunicorn:

- **Recovery is atomic** — a file lock (`.service/workers.db.recovery.lock`) ensures `recover_workers()` runs once even when multiple workers boot simultaneously.
- **Workers outlive their parent** — if a Gunicorn worker is recycled, background processes keep running. The next recovery cycle re-attaches or restarts them.

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

See [AI.md](AI.md) for the full coding and testing standards used in this project.

