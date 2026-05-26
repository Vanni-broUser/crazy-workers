# Crazy Workers

A standalone Python library for managing background worker processes with an internal persistent state.

## Features

- **Isolated State**: Uses an internal SQLite database to track worker status, PIDs, and parameters.
- **Process Management**: Start, stop, and monitor background Python scripts as independent processes.
- **Security**: Built-in protection against path traversal attacks in worker types.
- **Observability**: Optional per-worker file logging for easy debugging of subprocesses.
- **Automatic Recovery**: Built-in logic to detect crashed workers and restart them on application boot.
- **Framework Agnostic**: Core logic is independent of any web framework, but easy to integrate (e.g., with Flask).
- **Modern Tooling**: Fully compliant with `ruff` for linting and formatting.

## Project Structure

- `crazy_workers/`: The core library package.
  - `manager.py`: Main `WorkerManager` class.
  - `models.py`: Internal SQLAlchemy models.
  - `storage.py`: SQLite database management.
- `example_app/`: A dummy Flask application demonstrating library integration.
  - `workers/`: Example worker scripts.
  - `logs/`: Directory for worker log files.
- `tests.py`: Comprehensive test suite (94% coverage).

## Usage

### Basic Setup

```python
from crazy_workers import WorkerManager

# Initialize the manager
# db_path: path to the internal SQLite file
# workers_dir: directory containing your worker .py scripts
manager = WorkerManager(db_path='instance/workers.db', workers_dir='workers')

# Start a worker with logging
success, result = manager.start_worker(
    worker_key='my_unique_task',
    worker_type='example_worker', # maps to workers/example_worker.py
    parameters={'param1': 'value1'},
    log_dir='logs' # Optional: captures stdout/stderr to logs/my_unique_task.log
)
```

# List all workers
workers = manager.list_workers()

# Stop a worker
manager.stop_worker('my_unique_task')
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

1.  **Atomic Recovery**: The library uses a file-based lock (`.recovery.lock`) to ensure that `recover_workers()` only runs once, even if called by multiple Gunicorn workers.
2.  **Orphan Processes**: Background workers are started as subprocesses. If a Gunicorn worker is killed or recycled, the background workers it started will continue to run (becoming orphans). This is intended for persistence, as the next recovery cycle will re-attach to them or restart them if they crash.
3.  **Best Practice**: For optimal performance and to avoid redundant recovery attempts, it is recommended to call `recover_workers()` in Gunicorn's `on_starting` hook rather than inside your Flask app factory:

```python
# gunicorn_config.py
from my_app import manager

def on_starting(server):
    manager.recover_workers()
```

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
python -m unittest tests.py
coverage run -m unittest tests.py && coverage report
```
