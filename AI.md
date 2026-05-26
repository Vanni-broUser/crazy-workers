# AI Project Context & Rules

## Core Mandates
- **Linting & Formatting**: Always run `ruff check . --fix` and `ruff format .` after any code change.
- **Testing**: Always run `coverage run -m unittest tests.py` after changes.
- **Coverage**: Ensure total coverage stays above 90%. New code must be covered by tests.
- **Style**: Follow `pyproject.toml` (2-space indent, single quotes). No `print` statements.

## Commands
- **Test**: `python -m unittest tests.py`
- **Coverage**: `coverage run -m unittest tests.py && coverage report`
- **Lint**: `ruff check .`
- **Format**: `ruff format .`
