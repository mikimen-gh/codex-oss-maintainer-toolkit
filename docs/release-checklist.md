# Release Checklist

Use this checklist before publishing a release.

## Required Checks

```sh
PYTHONPATH=src python -m unittest discover -s tests
PYTHONPATH=src python -m oss_maintainer_toolkit.cli . --fail-on-review
./scripts/verify-public-safety.sh
```

## Manual Review

- Confirm `README.md` describes the current behavior.
- Confirm `CHANGELOG.md` has release notes.
- Confirm examples use placeholder data only.
- Confirm no private local state is included.
- Confirm GitHub Actions passed on `main`.

## v0.1.0 Scope

- Dependency-free Python CLI
- Markdown and JSON reports
- Required maintainer file checks
- Project signal checks
- Secret and private marker scanning
- Tests and CI
