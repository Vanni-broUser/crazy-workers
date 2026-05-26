# Crazy Workers CLI

The `crazy-workers` library provides a command-line interface to manage workers directly from the terminal.

## Installation

The CLI is installed automatically with the library:

```bash
pip install .
```

## Global Options

- `--workers-dir`: Directory containing the worker scripts (`.py` files). Defaults to `workers`.

Note: The database and logs are automatically managed within a `.service` folder inside the specified `--workers-dir`.

## Commands

### List Workers

Shows a list of all workers stored in the database with their current status and PID.

```bash
crazy-workers --workers-dir /path/to/workers list
```

### Stop Worker

Stops a running worker by its unique key.

```bash
crazy-workers --workers-dir /path/to/workers stop <worker_key>
```

## Example Usage

If you are using the example application:

```bash
crazy-workers --workers-dir example_app/workers list
```
