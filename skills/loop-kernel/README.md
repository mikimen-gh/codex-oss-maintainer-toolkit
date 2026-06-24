# Loop Kernel

Loop Kernel is a compact improvement-loop skill for coding agents. It is not a
"retry until green" script; it is a bounded loop that requires objective checks,
anti-gaming gates, canaries, telemetry, and learning evidence before promotion.

## What It Adds

- A single runtime entrypoint: `scripts/loop_kernel.py`.
- External canaries for gaming, sycophancy drift, lossy delegation, identity drift, and theater iteration.
- A cross-project registry backed by SQLite.
- A lightweight global ledger that stores metadata only.
- Bounded memory primitives with cap checks, search, prefetch, sync, and retire candidates.
- Deploy-readiness reporting that distinguishes deploy-ready from production-proven.

## Quick Start

```sh
cd skills/loop-kernel
python3 scripts/loop_kernel.py validate --spec loop.yaml --json
python3 scripts/canary_runner.py --spec loop.yaml --json
python3 scripts/loop_kernel.py preflight --prompt "improve this checked task" --json
python3 scripts/loop_kernel.py run --spec loop.yaml --json
python3 scripts/evaluator.py deploy --spec loop.yaml --json
```

## State

Generated telemetry stays local. By default, cross-project state is written under
`~/.local/state/loop-kernel`. Override this with `LOOP_KERNEL_STATE_DIR`.

Do not commit generated files under `state/`.
