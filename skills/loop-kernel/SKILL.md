---
name: loop-kernel
description: Run a bounded Codex improvement loop with objective checks, anti-gaming gates, canaries, telemetry, and promotion evidence. Use when a task should iterate only while each attempt becomes smarter and safer.
---

# Loop Kernel

Use this skill when work needs a bounded improvement loop instead of a blind
"try until green" retry cycle.

The loop keeps four promises:

- one entrypoint runs the loop,
- false success is rejected before promotion,
- telemetry is written after every run,
- the next attempt must be smarter than the last.

## Quick Start

From this skill directory:

```sh
python3 scripts/loop_kernel.py check --spec loop.yaml
python3 scripts/loop_kernel.py canary --spec loop.yaml
python3 scripts/loop_kernel.py run --spec loop.yaml
python3 scripts/loop_kernel.py status --spec loop.yaml
```

## Operating Model

The kernel has four phases:

1. `decide`: read `loop.yaml`, `STATE.md`, and telemetry.
2. `act`: run one bounded unit of checks or implementation support.
3. `verify`: objective checks, semantic gates, canaries, and invariants.
4. `learn`: update telemetry, hypothesis confidence, and `STATE.md`.

## Public Safety

This public version intentionally excludes private runtime state. The committed
`state/` directory starts empty except for `.gitkeep`; local runs will create
telemetry files on the user's machine.

Do not commit generated files under `state/`.
