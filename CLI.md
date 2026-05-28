# Crazy Workers CLI

The `crazy-workers` library provides a command-line interface to manage workers directly from the terminal.

## Installation

The CLI is installed automatically with the library:

```bash
pip install .
```

## Global Options

- `--workers-dir`: Directory containing the worker scripts (`.py` files).

## Worker Directory Discovery

The CLI uses a tiered discovery mechanism to find your workers directory. The discovery order is:

1.  **Command Line Flag**: High priority. If `--workers-dir` is provided, it must point to an existing directory.
2.  **Environment Variable**: Checks for `CRAZY_WORKERS_DIR`. This can be set in your shell or in a local `.env` file.
3.  **Interactive Prompt**: If the above fail and you are in an interactive terminal, the CLI will ask for the path. If provided, it will be validated and **automatically saved** to a `.env` file for future use.
4.  **Auto-detection**: If no input is given in the prompt (or if not in a TTY), it checks for a folder named `workers/` in the current working directory.

If none of the above result in a valid existing directory, the CLI will error out. Unlike the library, the CLI **never** creates the workers directory automatically.

## Commands

### List Workers

Shows a list of all workers stored in the database with their current status and PID.

```bash
crazy-workers list
```

### Start Worker

Starts a new worker process. If no `--key` is provided, the key defaults to the worker type. You can run multiple instances of the same worker type simultaneously by providing different keys.

```bash
# Explicit type (key defaults to 'example_worker')
crazy-workers start example_worker

# Interactive selection (lists available .py files)
crazy-workers start

# With custom key (allows running another 'example_worker' even if one is already running)
crazy-workers start example_worker --key my_worker_1
```

### Stop Worker

Stops a running worker by its unique key.

```bash
# Explicit key
crazy-workers stop my_custom_key

# Interactive selection (lists only running workers)
crazy-workers stop
```

## Interactive Mode

If you omit the required arguments for `start` or `stop`, the CLI will automatically enter **Interactive Mode**, showing you a numbered list of available options. This works in any terminal without additional configuration.

## Configuration via .env

When you provide a path during the interactive prompt, it is stored in a `.env` file in your current directory:

```text
CRAZY_WORKERS_DIR=/absolute/path/to/workers
```

The CLI automatically loads variables from `.env` at startup.

## Example Usage

If you are using the example application and you are in the project root:

```bash
crazy-workers list
```

If you are in a different directory:

```bash
# On Linux/macOS
echo "CRAZY_WORKERS_DIR=$(pwd)/example_app/workers" > .env
crazy-workers list

# On Windows (PowerShell)
"CRAZY_WORKERS_DIR=$((Get-Item .).FullName)\example_app\workers" | Out-File -Encoding utf8 .env
crazy-workers list
```
