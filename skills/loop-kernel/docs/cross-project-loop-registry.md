# Cross-Project Loop Registry Design

This release moves Loop Kernel from project-local state toward a reusable cross-project and cross-session operating model.

## Core Choices

- Global profiles live in a registry SQLite database under `~/.local/state/loop-kernel/registry.sqlite` by default.
- Project-local loop profile files are compatibility inputs, not the durable source of truth.
- The global ledger stores lightweight metadata only: project identity, run id, status, failure signature hash, strategy, cost, and verdict.
- The ledger must not store stdout, stderr, diffs, source files, prompts, credentials, or private paths.
- Memory is bounded: always-apply memory is capped, domain lessons are fetched on demand, and stale lessons are flagged for retirement.

## Lifecycle

1. `memory-prefetch` selects bounded context for the current prompt.
2. `registry-discover` resolves a reusable loop profile for the current project.
3. `preflight` validates profile, memory, and checks before work begins.
4. `run` records local telemetry and lightweight global metadata.
5. `capabilities` compiles repeated failure signatures into reusable improvement candidates.

## Public Safety

The public version uses environment-configurable state roots and does not include generated telemetry. Keep `state/` local-only except for `.gitkeep`.
