# Architecture

The repository is intentionally small:

- `docs/` contains public documentation.
- `examples/` contains sanitized examples.
- `scripts/` contains reusable checks and maintainer helpers.
- `src/oss_maintainer_toolkit/` contains the Python CLI and scanning logic.
- `tests/` contains public tests.
- `.github/workflows/` contains CI for tests and public-safety checks.

Private runtime state belongs outside this repository.

## Components

- `checks.py`: builds a readiness report from repository files.
- `cli.py`: formats the report as Markdown or JSON and supports CI failure.
- `verify-public-safety.sh`: shell-level safety check for publication.

The scanner contains a narrow fixture allowlist for its own detector definitions
and tests. That keeps the repository self-testable while still flagging the same
patterns in ordinary project files.
