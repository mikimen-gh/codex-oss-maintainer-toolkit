# Codex OSS Maintainer Toolkit

Privacy-safe starter repository for open-source maintainer workflows with Codex.

This repository is intentionally public-facing. It is designed to hold reusable
automation, documentation, examples, and review workflows that can be shared
without exposing personal Codex Desktop state, local configuration, private
logs, credentials, or operational notes.

## Purpose

This project provides a small, auditable structure for open-source maintenance
work:

- Pull request review support
- Issue triage helpers
- Release preparation checklists
- Documentation maintenance workflows
- Security and privacy review gates

## Repository Scope

Included:

- Public documentation
- Sanitized examples
- Reusable scripts
- Tests for public helpers
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
```

## License

MIT
