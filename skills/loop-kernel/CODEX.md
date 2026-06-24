# loops - Codex Loop Kernel

## Mission
This project is a compact loop system for Codex.app. It is not "loop until green"; it is "loop until the next attempt is smarter."

The loop keeps four promises:

- run from one entrypoint,
- reject false success before promotion,
- update persistent state after every run,
- write a light cross-project ledger for future sessions,
- preserve the Codex operating contract.

## Canonical Root
- Source of truth: `<skill-root>`
- Skill entry: `SKILL.md`
- Prior art: `vendor/prior-art/loops`
- Prior-art rule: read only unless the user explicitly approves edits.
- Archive mirrors are out of scope unless the user asks to save, sync, commit, or push.

## Entry Point
Use only the kernel for normal operation:

```bash
python3 scripts/loop_kernel.py validate --spec loop.yaml
python3 scripts/loop_kernel.py run --spec loop.yaml
python3 scripts/loop_kernel.py check --spec loop.yaml
python3 scripts/loop_kernel.py learn --spec loop.yaml
python3 scripts/loop_kernel.py canary --spec loop.yaml
python3 scripts/loop_kernel.py discover --project-root "<project>"
python3 scripts/loop_kernel.py attach --spec loop.yaml --project-root "<project>"
python3 scripts/loop_kernel.py preflight --prompt "<task>"
python3 scripts/evaluator.py deploy --spec loop.yaml
python3 scripts/evaluator.py capabilities --spec loop.yaml --write
python3 scripts/state_store.py memory-check --cap-chars 3000
python3 scripts/state_store.py memory-index
python3 scripts/state_store.py memory-search --query "<task>"
python3 scripts/state_store.py memory-prefetch --prompt "<task>"
python3 scripts/state_store.py memory-sync --prompt "<task>" --capture "<candidate>"
python3 scripts/state_store.py registry-discover --project-root "<project>"
python3 scripts/state_store.py registry-attach --spec loop.yaml --project-root "<project>"
```

For a real project, prefer the global registry over a project-local spec file:
attach a profile once, then let `loop_kernel.py preflight` / `run` discover the
profile from the current working directory. A project-local `loop-profile.json`
is only a compatibility input or export artifact, not the source of truth.
Feed real token usage with `--cost-per-iter`, `LOOP_KERNEL_COST_TOKENS_LAST_ITER`,
or `.loop-state/cost-<run_id>-iter<N>.json`.

## Operating Model
The kernel has four phases:

1. `decide`: read `loop.yaml`, `STATE.md`, and telemetry.
2. `act`: run one bounded unit of checks or implementation support.
3. `verify`: objective checks, semantic gates, canaries, and invariants.
4. `learn`: update telemetry, hypothesis confidence, and `STATE.md`.

Local project state lives under the spec's `state_dir`. Cross-project learning
lives under `~/.local/state/loop-kernel` and stores only lightweight metadata:
project key, session id, run id, failure signature hash, cost, strategy, and
verdict. It must not store stdout, stderr, diffs, source files, or secrets.

Global loop registry lives under `~/.local/state/loop-kernel/registry.sqlite`. It is
the source of truth for reusable loop profiles across projects and sessions:
project identity, git remote/path fingerprint, run id, goal, checks, cost
ceiling, risk, read-only paths, tags, and update timestamps. Project-local files
are optional cache/compatibility surfaces.

Global Codex memory is bounded separately: `lessons.md` has an Always-Apply
section capped at 3,000 characters, while domain-specific lessons live under
`~/.local/share/loop-kernel/domain-lessons/` and are read only on demand.
This follows the Hermes-style lifecycle: prefetch only bounded memory, sync
new candidates and retire signals, never inject all memory by default.
Search is SQLite-backed. If FTS5 is available, `memory-search` uses FTS; otherwise
it falls back to bounded LIKE search. This keeps Codex usable without extra
services while preserving a path toward richer retrieval.

## Files
- `scripts/loop_kernel.py`: single runtime entrypoint.
- `scripts/gates.py`: G1-G15 anti-gaming, sycophancy drift, delegation loss, invariants, and promotion court.
- `scripts/evaluator.py`: reports, comparisons, hypothesis learning, observation, and decay.
- `scripts/canary_runner.py`: fixed external canaries.
- `scripts/state_store.py`: JSONL state, cost inputs, deploy readiness files, and `STATE.md`.
- `~/.local/state/loop-kernel/global_runs.jsonl`: cross-project/session loop ledger.
- `~/.local/state/loop-kernel/capability_candidates.jsonl`: repeated-signature capability candidates.
- `~/.local/state/loop-kernel/registry.sqlite`: global loop profile registry.
- `~/.local/share/loop-kernel/domain-lessons/`: on-demand memory files.
- `~/.local/state/loop-kernel/loops_memory.sqlite`: searchable memory/run index.
- `loop.yaml`: JSON-compatible YAML spec.
- `STATE.md`: human-readable current state.
- `canaries/*/case.json`: external ground-truth fixtures.

## Hard Stops
- Do not weaken tests, checks, or gate rules to pass.
- Do not edit `vendor/prior-art/loops`.
- Do not treat `an archive mirror` as the source of truth.
- Do not promote high-risk loop changes without objective evidence.
- Stop after repeated identical failure signatures unless strategy changes.
- Keep all normal operation inside the five scripts; do not add helper sprawl.

## Deploy Vocabulary
- **deploy-ready**: validation, canaries, checks, state writes, cost input, and promotion court work on a real project.
- **production-proven**: at least 5-10 real project runs exist, evaluator trends are visible, and a hypothesis cycle improves later attempts.
