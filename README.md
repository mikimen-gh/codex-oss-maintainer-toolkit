# Codex OSS Maintainer Toolkit

Privacy-safe maintainer readiness checks for public open-source repositories.

This project helps open-source maintainers publish and maintain public
repositories without accidentally leaking private local state, credentials,
machine-specific configuration, or maintainer-only notes.

It is intentionally small, dependency-free, and CI-friendly so maintainers can
add it to an existing repository before making it public, before cutting a
release, or before asking Codex to help with review and maintenance work.

## The Problem

Maintainers often work across local tools, automation logs, private scratch
notes, and public repositories. That makes it easy to accidentally publish:

- Secrets or token-looking values
- Local paths and machine-specific state
- Private maintainer notes
- Incomplete public project files
- Repositories that lack basic maintainer signals such as tests and CI

Codex OSS Maintainer Toolkit gives maintainers a simple report they can run
locally or in GitHub Actions before publishing.

## Current Features

- Scans repositories for common secret patterns
- Detects private local-state markers before publication
- Checks for required public maintainer files
- Checks for concrete project signals such as tests, CI, and implementation code
- Emits Markdown or JSON reports for maintainers and CI
- Publishes a reusable Loop Kernel skill for bounded Codex improvement loops

## Who This Is For

- Maintainers preparing a private project for public release
- Small OSS projects that need lightweight release and privacy gates
- Developers using Codex to review public changes
- Projects that want a simple, auditable pre-publication checklist

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

Example output:

```text
# OSS Maintainer Toolkit Report

- Status: `pass`
- Score: `100/100`

No blocking issues found.
```

## Maintainer Signals

This repository includes the public signals expected from an active early-stage
OSS project:

- Working implementation in `src/oss_maintainer_toolkit/`
- Automated tests in `tests/`
- GitHub Actions CI
- Security policy
- Contributing guide
- Roadmap and use cases
- Sanitized demo project
- Release checklist
- Public Loop Kernel skill in `skills/loop-kernel/`

## Public Skills

### Loop Kernel

`skills/loop-kernel/` is a reusable Codex skill for bounded iterative work. It
runs checks, canaries, anti-gaming gates, telemetry, and promotion evidence so
the loop improves the next attempt instead of blindly retrying.

```sh
cd skills/loop-kernel
python3 scripts/loop_kernel.py check --spec loop.yaml
python3 scripts/loop_kernel.py canary --spec loop.yaml
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

See [docs/codex-for-oss-application.md](docs/codex-for-oss-application.md) for
short application-ready project notes.

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

## Release

The first usable release target is `v0.1.0`. See
[docs/release-checklist.md](docs/release-checklist.md).

## License

MIT
