# AI Project Context & Rules

## Core Mandates
- **Clean & Talking Code**: Prioritize expressive, self-documenting code ("codice parlante"). Variables, functions, and classes should have clear, descriptive names that reveal their intent.
- **Modularity & Decomposition**: Keep files small and focused on a single responsibility. If a file becomes too large or complex, refactor it into a module (a directory with `__init__.py` and sub-modules).
- **Structured Testing**: Tests must be organized into a `tests/` directory that mirrors the package structure of the codebase. Each source module should have a corresponding test module.
- **Responsibility Distribution**: Aim for a balanced distribution of responsibilities. Use design patterns (e.g., Command, Strategy, Factory) where appropriate to reduce complexity.
- **Linting & Formatting**: Always run `ruff check . --fix` and `ruff format .` after any code change.
- **Testing**: Always run `python -m unittest discover tests` after changes.
- **Coverage**: Ensure total coverage stays above 90%. New code must be covered by tests.
- **Style**: Follow `pyproject.toml` (2-space indent, single quotes). No `print` statements. Imports must be sorted alphabetically and organized into two blocks separated by a blank line:
  1. External dependencies: Standard library and third-party packages (e.g., Flask, SQLAlchemy, psutil).
  2. Project-internal imports: Modules belonging to the project itself.

## Commands
- **Test**: `python -m unittest discover tests`
- **Coverage**: `coverage run -m unittest discover tests && coverage report`
- **Lint**: `ruff check .`
- **Format**: `ruff format .`
