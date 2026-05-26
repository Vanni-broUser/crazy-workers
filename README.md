# Crazy Workers

A standalone Python library for managing background worker processes with an internal persistent state.

## Features

- **Isolated State**: Uses an internal SQLite database to track worker status, PIDs, and parameters.
- **Process Management**: Start, stop, and monitor background Python scripts as independent processes.
- **CLI Interface**: Manage and monitor workers with an intelligent discovery mechanism (see [CLI.md](CLI.md)).
- **Security**: Built-in protection against path traversal attacks.
- **Observability**: Per-worker file logging and robust process verification.
- **Automatic Recovery**: Detects crashed workers and restarts them on application boot.
- **Zombie Protection**: Robustly distinguishes between active and zombie processes using `psutil`.
- **Clean Structure**: All application files (DB, lock, logs) are consolidated into a `.service` folder within the workers directory.
- **Modern Tooling**: Fully compliant with `ruff` for linting and formatting.

## Project Structure

- `crazy_workers/`: The core library package.
  - `manager.py`: Main `WorkerManager` class.
  - `models.py`: Internal SQLAlchemy models.
  - `storage.py`: SQLite database management.
  - `process.py`: Process management utilities.
  - `recovery.py`: Recovery and locking mechanisms.
- `example_app/`: A dummy Flask application demonstrating library integration.
  - `workers/`: Example worker scripts.
    - `.service/`: Consolidated application state and logs.
- `tests/`: Reorganized test suite mirroring the package structure.

## Usage

### Basic Setup

```python
from crazy_workers import WorkerManager

# Initialize the manager
# workers_dir: directory containing your worker .py scripts (default: 'workers')
# create_dir: whether to create workers_dir if it doesn't exist (default: True)
# This will automatically create a '.service' folder inside workers_dir for DB and logs.
manager = WorkerManager(workers_dir='my_workers', create_dir=True)
```

### Starting Workers

The `start_worker` method is simple and flexible:

```python
# Super simple: worker_key defaults to 'example_worker'
# Logs will be saved to 'my_workers/.service/logs/example_worker.log'
success, result = manager.start_worker('example_worker')

# With custom key and parameters
success, result = manager.start_worker(
    'example_worker', 
    worker_key='my_custom_key',
    parameters={'param1': 'value1'}
)
```

### Process Verification

The library ensures that processes are correctly started and tracked:
- **Immediate Check**: Verifies the process is alive right after startup.
- **OS Verification**: Uses `psutil` to confirm PIDs actually exist on the system.
- **Cleanup**: Aggressively terminates orphans during manager disposal.

### Monitoring & Control

```python
# List all workers (returns status, PID, parameters, etc.)
workers = manager.list_workers()

# Stop a worker gracefully (with SIGTERM, then SIGKILL if needed)
manager.stop_worker('my_custom_key')
```

### Integration with Flask

See `example_app/app.py` for a full example. Key integration point:

```python
@app.before_first_request # or during app factory
def startup():
    manager.recover_workers()
```

## Concurrency & Gunicorn

When using `crazy_workers` with a pre-fork server like **Gunicorn**, keep the following in mind:

1.  **Atomic Recovery**: The library uses a file-based lock (`.service/workers.db.recovery.lock`) to ensure that `recover_workers()` only runs once, even if called by multiple Gunicorn workers.
2.  **Orphan Processes**: Background workers are started as subprocesses. If a Gunicorn worker is killed or recycled, the background workers it started will continue to run (becoming orphans). This is intended for persistence, as the next recovery cycle will re-attach to them or restart them if they crash.

## Development

### Requirements

- Python 3.10+
- `sqlalchemy`
- `psutil`
- `flask` (only for the example app)

### Standards (AI.md)

This project follows strict engineering standards:
- **Indentation**: 2 spaces.
- **Quotes**: Single quotes.
- **Formatting**: `ruff format .`
- **Linting**: `ruff check .`

### Testing

Run tests and check coverage:

```bash
pip install .[dev]
python -m unittest discover tests
coverage run -m unittest discover tests && coverage report
```
