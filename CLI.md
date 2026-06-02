# Crazy Workers CLI

The `crazy-workers` library provides a command-line interface to manage worker processes directly from the terminal.

## Installation

```bash
pip install crazy-workers
```

## Global Options

| Option | Description |
|--------|-------------|
| `--workers-dir PATH` | Directory containing the worker scripts. Overrides all other discovery methods. |

## Worker Directory Discovery

The CLI resolves the workers directory through a tiered mechanism (highest priority first):

1. **`--workers-dir` flag** — must point to an existing directory, otherwise the CLI exits with an error.
2. **`CRAZY_WORKERS_DIR` environment variable** — can be set in your shell or in a local `.env` file.
3. **Interactive prompt** — if running in a TTY, asks for the path and saves it to `.env` for future use.
4. **Auto-detection** — checks for a folder named `workers/` in the current working directory.

If none of the above resolves to a valid directory, the CLI exits with an error. Unlike the library, the CLI **never creates** the workers directory.

## Commands

### `list`

Shows all workers tracked in the database, including their status, PID, last action timestamp, and parameters.

```bash
crazy-workers list
crazy-workers --workers-dir /path/to/workers list
```

Status colors: `green` = RUNNING, `cyan` = NEVER_STARTED, `yellow` = STARTING, `dim` = STOPPED, `bold red` = CRASHED.

---

### `start`

Starts a worker process. If `worker_type` is omitted, presents an interactive list of available `.py` files.

```bash
# Start by type (key defaults to worker_type)
crazy-workers start example_worker

# With a custom key (allows multiple instances of the same type)
crazy-workers start example_worker --key job_1

# With parameters (must be a valid JSON string)
crazy-workers start example_worker --params '{"duration": 30, "mode": "fast"}'

# Interactive selection
crazy-workers start
```

| Option | Description |
|--------|-------------|
| `worker_type` | Filename of the worker script (without `.py`). Optional — interactive if omitted. |
| `--key KEY` | Unique key for this instance. Defaults to `worker_type`. |
| `--params JSON` | JSON string passed to the worker as `sys.argv[1]`. |

---

### `stop`

Stops a running worker by its key. If `worker_key` is omitted, presents an interactive list of running workers.

```bash
# Explicit key
crazy-workers stop job_1

# Interactive selection
crazy-workers stop
```

On stop, unmanaged child processes are also terminated. Independently managed nested workers (started via their own `WorkerManager`) are preserved.

---

### `params`

Displays the parameters a worker was started with, formatted as JSON.

```bash
# Explicit key
crazy-workers params job_1

# Interactive selection
crazy-workers params
```

---

### `restore`

Scans the database for workers whose status is `RUNNING` but whose process is dead, and restarts them. Uses a file lock to prevent concurrent recovery.

```bash
crazy-workers restore
```

Typically called on application startup. In code, the equivalent is `manager.recover_workers()`.

---

## Interactive Mode

Omitting `worker_type` (for `start`) or `worker_key` (for `stop` and `params`) activates interactive mode — a numbered list is shown and you select with a number. Requires a TTY.

## Configuration via `.env`

When the interactive prompt is used to set the workers directory, it is automatically saved to `.env` in the current working directory:

```text
CRAZY_WORKERS_DIR=/absolute/path/to/workers
```

The CLI reads this file at every invocation. You can also set it manually.

### Platform examples

```bash
# Linux / macOS
export CRAZY_WORKERS_DIR=/path/to/workers
crazy-workers list

# Windows (PowerShell)
$env:CRAZY_WORKERS_DIR = "C:\path\to\workers"
crazy-workers list

# Persist to .env (any platform)
echo "CRAZY_WORKERS_DIR=/path/to/workers" > .env
crazy-workers list
```
