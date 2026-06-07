# Codex OSS Maintainer Toolkit

Privacy-safe maintainer readiness checks for public open-source repositories.

This repository is intentionally public-facing. It is designed to hold reusable
automation, documentation, examples, and review workflows that can be shared
without exposing personal local configuration, private logs, credentials, or
operational notes.

## Purpose

This project provides a small, auditable CLI for open-source maintenance work:

- Scans repositories for common secret patterns
- Detects private local-state markers before publication
- Checks for required public maintainer files
- Checks for concrete project signals such as tests, CI, and implementation code
- Emits Markdown or JSON reports for maintainers and CI

The goal is to help maintainers keep public repositories useful and safe while
using Codex for review, documentation, and release workflows.

## Install

This alpha version has no runtime dependencies.

```sh
python -m pip install -e .
```

## Usage

Run a Markdown report:

```sh
oss-maintainer-toolkit .
```

Run a JSON report:

```sh
oss-maintainer-toolkit . --format json
```

Fail CI when the repository needs review:

```sh
oss-maintainer-toolkit . --fail-on-review
```

Without installing:

```sh
PYTHONPATH=src python -m oss_maintainer_toolkit.cli . --fail-on-review
```

## Repository Scope

Included:

- Public documentation
- Sanitized examples
- Reusable scripts
- A dependency-free Python CLI
- Tests for the public checks
- GitHub Actions CI
- Maintainer workflow notes

Excluded:

- Private Codex Desktop state
- Local machine paths and settings
- API keys, tokens, wallet data, and SSH material
- Personal conversation history or logs
- Private repository history
- VPS hostnames, internal service names, and runtime config

## Privacy Policy For This Repository

This repository must stay safe to publish. Before committing or pushing, run:

```sh
./scripts/verify-public-safety.sh
```

If the script reports a possible secret or local-only path, review the finding
before publishing.

## Codex For Open Source Use

Codex and API credits would be used for:

- Reviewing pull requests
- Generating and improving tests
- Maintaining documentation
- Preparing releases
- Auditing changes for security and privacy risks
- Automating repetitive maintainer tasks

## Getting Started

```sh
./scripts/verify-public-safety.sh
PYTHONPATH=src python -m unittest discover -s tests
PYTHONPATH=src python -m oss_maintainer_toolkit.cli . --fail-on-review
```

## Project Status

Alpha. The current implementation is intentionally small but functional:

- `src/oss_maintainer_toolkit/checks.py` implements repository scanning.
- `src/oss_maintainer_toolkit/cli.py` exposes the CLI.
- `tests/test_checks.py` covers pass, review, and CLI behavior.
- `.github/workflows/ci.yml` runs tests and public-safety checks.

See [docs/roadmap.md](docs/roadmap.md) for planned next steps.

## License

MIT
