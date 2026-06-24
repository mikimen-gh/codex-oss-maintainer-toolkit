---
name: loop-kernel
description: Run a bounded improvement loop with objective checks, anti-gaming gates, canaries, telemetry, a cross-project registry, and bounded memory. Use when a task should iterate only while each attempt becomes smarter and safer.
---

# Loop Kernel

Use this skill when work needs a bounded improvement loop instead of a blind retry cycle.

## Quick Start

From this skill directory:

```sh
python3 scripts/loop_kernel.py validate --spec loop.yaml --json
python3 scripts/loop_kernel.py canary --spec loop.yaml --json
python3 scripts/loop_kernel.py preflight --prompt "<task>" --json
python3 scripts/loop_kernel.py run --spec loop.yaml --json
python3 scripts/evaluator.py deploy --spec loop.yaml --json
```

## Cross-Project Registry

Attach a reviewed profile once, then discover it from the target project root:

```sh
python3 scripts/loop_kernel.py attach --spec loop.yaml --project-root "$PWD" --json
python3 scripts/loop_kernel.py discover --project-root "$PWD" --query "<task>" --json
python3 scripts/loop_kernel.py preflight --prompt "<task>" --json
```

Set `LOOP_KERNEL_STATE_DIR` to choose where global registry and memory indexes live.

## Bounded Memory

```sh
python3 scripts/state_store.py memory-check --cap-chars 3000
python3 scripts/state_store.py memory-index --json
python3 scripts/state_store.py memory-search --query "<task>" --json
python3 scripts/state_store.py memory-prefetch --prompt "<task>" --json
python3 scripts/state_store.py memory-sync --prompt "<task>" --capture "<candidate>" --json
```

## Hard Rules

- Do not weaken tests, checks, or canaries to get green.
- Do not let the maker be the only judge; use objective checks and gates.
- Do not promote changes when deploy readiness reports blockers.
- Do not store stdout, stderr, diffs, file contents, prompts, private paths, or secrets in the global ledger.
- Do not commit generated telemetry from `state/`.
