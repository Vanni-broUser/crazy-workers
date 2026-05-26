# AI Project Context & Rules

## Core Mandates
- **Linting & Formatting**: Always run `ruff check . --fix` and `ruff format .` after any code change.
- **Testing**: Always run `coverage run -m unittest tests.py` after changes.
- **Coverage**: Ensure total coverage stays above 90%. New code must be covered by tests.
- **Style**: Follow `pyproject.toml` (2-space indent, single quotes). No `print` statements. Imports must be sorted alphabetically and organized into two blocks separated by a blank line:
  1. External dependencies: Standard library and third-party packages (e.g., Flask, SQLAlchemy, psutil).
  2. Project-internal imports: Modules belonging to the project itself.

## Commands
- **Test**: `python -m unittest tests.py`
- **Coverage**: `coverage run -m unittest tests.py && coverage report`
- **Lint**: `ruff check .`
- **Format**: `ruff format .`
