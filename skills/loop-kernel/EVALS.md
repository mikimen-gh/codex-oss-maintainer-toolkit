# EVALS - Loop Kernel

Run from the skill root:

```sh
python3 -c "import ast, pathlib; [ast.parse(p.read_text(encoding='utf-8')) for p in pathlib.Path('scripts').glob('*.py')]"
python3 scripts/canary_runner.py --spec loop.yaml --json
python3 scripts/loop_kernel.py govern --spec loop.yaml --json
python3 scripts/loop_kernel.py check --spec loop.yaml --json
python3 scripts/evaluator.py report --spec loop.yaml --json
python3 scripts/evaluator.py decay --spec loop.yaml --json
python3 scripts/loop_kernel.py run --spec loop.yaml --json
```

## Quality Bar

- One command starts the loop.
- Fixed canaries pass.
- Gaming diffs are blocked.
- Sycophantic pressure is blocked.
- Lossy verifier briefs are blocked.
- Promotion evidence includes goal, check, judge, cost, and run id.
- `STATE.md` explains the current state without reading source code.
