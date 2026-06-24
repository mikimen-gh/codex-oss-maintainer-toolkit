# EVALS - Loop Kernel

## Smoke
Run from the project root:

```bash
python3 -c "import ast, pathlib; [ast.parse(p.read_text(encoding='utf-8')) for p in pathlib.Path('scripts').glob('*.py')]"
python3 scripts/loop_kernel.py validate --spec loop.yaml --json
python3 scripts/canary_runner.py --spec loop.yaml --json
python3 scripts/loop_kernel.py govern --spec loop.yaml --json
python3 scripts/loop_kernel.py check --spec loop.yaml --json
python3 scripts/loop_kernel.py attach --spec loop.yaml --project-root "$PWD" --json
python3 scripts/loop_kernel.py discover --project-root "$PWD" --query loop --json
python3 scripts/loop_kernel.py preflight --prompt "loop registry cross project" --json
python3 scripts/evaluator.py report --spec loop.yaml --json
python3 scripts/evaluator.py capabilities --spec loop.yaml --json
python3 scripts/evaluator.py decay --spec loop.yaml --json
python3 scripts/evaluator.py deploy --spec loop.yaml --json
python3 scripts/state_store.py memory-check --cap-chars 3000
python3 scripts/state_store.py memory-index --json
python3 scripts/state_store.py memory-search --query "ループスキル ppt-to-psd" --json
python3 scripts/state_store.py memory-prefetch --prompt "ループスキルでppt-to-psdを確認" --json
python3 scripts/state_store.py memory-sync --prompt "ループスキル" --capture "candidate lesson" --json
python3 scripts/state_store.py registry-attach --spec loop.yaml --project-root "$PWD" --tag kernel --json
python3 scripts/state_store.py registry-discover --project-root "$PWD" --query loop --json
python3 scripts/state_store.py registry-spec --project-root "$PWD" --json
python3 scripts/loop_kernel.py run --spec loop.yaml --json
```

## Quality Bar
The kernel is successful only if all are true:

- one command starts the loop,
- all fixed canaries pass,
- gaming diffs are blocked,
- sycophantic pressure is blocked,
- lossy verifier briefs are blocked,
- no required state artifact is missing,
- promotion evidence includes goal/check/judge/cost/run id,
- global ledger rows are lightweight and contain no stdout/stderr/diff/file contents,
- Always-Apply memory is bounded and domain lessons exist for on-demand recall,
- SQLite memory search returns relevant docs/runs without reading full lessons,
- memory prefetch/sync commands work without injecting the full lessons file,
- registry attach/discover/preflight resolve a loop profile without requiring a project-local `loop-profile.json`,
- `STATE.md` explains the current state without reading source code.
- `deploy_readiness.json` clearly says whether this is deploy-ready or still only smoke-tested.

## Scoring
- `A`: canaries pass, check passes, no false success, state is updated.
- `B`: checks pass but canary or state evidence is missing.
- `C`: telemetry exists but promotion evidence is incomplete.
- `D`: no telemetry or false success is promoted.
