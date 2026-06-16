# loop-kernel - Codex Loop Kernel

## Mission

Loop Kernel is a compact loop system for Codex-style work. It is not "loop
until green"; it is "loop until the next attempt is smarter."

The loop keeps four promises:

- run from one entrypoint,
- reject false success before promotion,
- update persistent local state after every run,
- preserve the operating contract.

## Entry Point

Use only the kernel for normal operation:

```sh
python3 scripts/loop_kernel.py run --spec loop.yaml
python3 scripts/loop_kernel.py check --spec loop.yaml
python3 scripts/loop_kernel.py learn --spec loop.yaml
python3 scripts/loop_kernel.py canary --spec loop.yaml
```

## Hard Stops

- Do not weaken tests, checks, or gate rules to pass.
- Do not promote high-risk loop changes without objective evidence.
- Stop after repeated identical failure signatures unless strategy changes.
- Keep normal operation inside the five scripts; avoid helper sprawl.
- Do not commit generated telemetry from `state/`.
