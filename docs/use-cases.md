# Use Cases

## Public Repository Launch

Run a readiness report before making a repository public:

```sh
PYTHONPATH=src python -m oss_maintainer_toolkit.cli --fail-on-review
```

## Pull Request Review

Use the CLI in CI to catch accidental private paths, tokens, local state, or
missing public project files.

## Maintainer Automation

Generate a JSON report that another workflow can parse:

```sh
PYTHONPATH=src python -m oss_maintainer_toolkit.cli --format json
```

## Codex-Assisted Maintenance

Codex can use the report to focus review on concrete repository risks:

- Missing maintainer files
- Missing project implementation signals
- Secret-looking strings
- Private local-state references
