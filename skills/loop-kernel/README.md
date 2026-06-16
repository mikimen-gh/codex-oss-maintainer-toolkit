# Loop Kernel Skill

Loop Kernel is a compact Codex-oriented skill for bounded iterative work. It is
not "loop until green"; it is "loop until the next attempt is smarter."

## What It Does

- Runs configured checks from `loop.yaml`
- Runs fixed canaries for anti-gaming behavior
- Blocks obvious false-success patterns
- Records run telemetry locally
- Updates `STATE.md` with the current loop state
- Requires promotion evidence before calling work complete

## Install

Clone this repository and copy `skills/loop-kernel` into your Codex skills
directory, or install it with any Codex skill installer that supports a GitHub
repository path.

## Run

```sh
cd skills/loop-kernel
python3 scripts/loop_kernel.py check --spec loop.yaml
python3 scripts/loop_kernel.py canary --spec loop.yaml
python3 scripts/loop_kernel.py run --spec loop.yaml
```

## Files

- `SKILL.md`: Codex skill entrypoint.
- `scripts/loop_kernel.py`: single runtime entrypoint.
- `scripts/gates.py`: semantic and promotion gates.
- `scripts/evaluator.py`: reports and hypothesis learning.
- `scripts/canary_runner.py`: fixed canary runner.
- `scripts/state_store.py`: local telemetry and `STATE.md` writer.
- `canaries/*/case.json`: external fixtures.
- `loop.yaml`: default public configuration.

## Public State Policy

Runtime state is local-only. Do not publish generated files from `state/`.
