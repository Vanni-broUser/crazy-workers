# Crazy Workers CLI

The `crazy-workers` library provides a command-line interface to manage workers directly from the terminal.

## Installation

The CLI is installed automatically with the library:

```bash
pip install .
```

## Global Options

- `--db`: Path to the SQLite database used by the library.
- `--workers-dir`: Directory containing the worker scripts (`.py` files).

## Commands

### List Workers

Shows a list of all workers stored in the database with their current status and PID.

```bash
crazy-workers --db /path/to/db.sqlite --workers-dir /path/to/workers list
```

### Stop Worker

Stops a running worker by its unique key.

```bash
crazy-workers --db /path/to/db.sqlite --workers-dir /path/to/workers stop <worker_key>
```

## Example Usage

If you are using the example application:

```bash
crazy-workers --db instance/workers_internal.db --workers-dir example_app/workers list
```
