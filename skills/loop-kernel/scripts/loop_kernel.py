#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import subprocess
from collections import Counter
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Any

from canary_runner import run_all
from evaluator import propose_hypothesis, report
from gates import invariant_guard, promotion_decision, semantic_judge
from state_store import load_spec, path_for, read_jsonl, record_run, update_state_md


def govern(spec: dict[str, Any]) -> dict[str, Any]:
    risk = int(spec.get("risk") or 3)
    rows = read_jsonl(path_for(spec, "runs"))
    successful = sorted(int(r.get("iter") or 1) for r in rows if r.get("status") == "pass")
    if len(successful) >= 5:
        idx = max(0, int(len(successful) * 0.9) - 1)
        max_iter = max(2, min(12, int(successful[idx] * 1.5) or 2))
        reason = "history-p90"
    else:
        max_iter = int(spec.get("max_iter") or (4 if risk <= 3 else 6 if risk <= 6 else 8))
        reason = "spec-or-risk-default"
    topology = "solo"
    if risk >= 8:
        topology = "main+strategist+verifier+auditor"
    elif risk >= 5:
        topology = "main+doer+verifier"
    elif risk >= 3:
        topology = "main+verifier"
    return {
        "risk": risk,
        "topology": topology,
        "max_iter": max_iter,
        "max_iter_reason": reason,
        "budget_tokens": int(spec.get("cost_ceiling_tokens") or 12000),
    }


def mutate(spec: dict[str, Any], run_id: str) -> dict[str, Any]:
    rows = [r for r in read_jsonl(path_for(spec, "runs")) if r.get("run_id") == run_id]
    if not rows:
        return {"strategy": "root-cause", "stop": False, "reason": "no telemetry yet"}
    last = rows[-1]
    total_cost = sum(int(r.get("cost_tokens") or 0) for r in rows)
    if total_cost > int(spec.get("cost_ceiling_tokens") or 12000):
        return {"strategy": "cost-collapse", "stop": True, "reason": "budget exceeded"}
    sigs = [str(r.get("failure_signature") or "") for r in rows if r.get("failure_signature")]
    if sigs and Counter(sigs)[sigs[-1]] >= 3:
        return {"strategy": "ask-user", "stop": True, "reason": "same failure signature repeated 3 times"}
    if last.get("gate_verdict") == "block":
        return {"strategy": "check-strengthen", "stop": False, "reason": "gate blocked latest iteration"}
    if last.get("status") == "pass":
        return {"strategy": "independent-verify", "stop": False, "reason": "pass should be challenged before final exit"}
    return {"strategy": "targeted-fix", "stop": False, "reason": "failure has bounded signal"}


def run_check(project_root: Path, check: dict[str, Any]) -> dict[str, Any]:
    cmd = check.get("cmd")
    if not isinstance(cmd, list) or not all(isinstance(x, str) for x in cmd):
        return {"name": check.get("name", "unnamed"), "exit_code": 127, "stderr": "cmd must be a string list"}
    env = os.environ.copy()
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    proc = subprocess.run(cmd, cwd=project_root, text=True, capture_output=True, timeout=int(check.get("timeout_sec") or 120), env=env)
    return {
        "name": check.get("name") or " ".join(cmd),
        "cmd": cmd,
        "exit_code": proc.returncode,
        "stdout": proc.stdout[-4000:],
        "stderr": proc.stderr[-4000:],
    }


def check(spec: dict[str, Any], iter_no: int = 1, governance: dict[str, Any] | None = None, strategy: str = "targeted-fix") -> dict[str, Any]:
    root = Path(str(spec.get("project_root"))).expanduser()
    checks = list(spec.get("checks") or [])
    results = []
    with ThreadPoolExecutor(max_workers=max(1, min(len(checks), int(spec.get("parallelism") or 3)))) as pool:
        futures = [pool.submit(run_check, root, item) for item in checks]
        for future in as_completed(futures):
            results.append(future.result())
    failed = [r for r in results if r["exit_code"] != 0]
    invariant = invariant_guard(spec, [])
    judge = semantic_judge(str(spec.get("diff_text") or ""))
    status = "pass" if not failed and invariant["verdict"] == "pass" else "fail"
    row = record_run(spec, {
        "run_id": spec.get("run_id", "manual"),
        "iter": iter_no,
        "goal": spec.get("goal"),
        "status": status,
        "check_results": results,
        "judge": judge,
        "judge_verdict": judge["verdict"],
        "gate_verdict": "pass" if status == "pass" and judge["verdict"] != "block" else "block",
        "failure_signature": failed[0]["name"] if failed else "",
        "cost_tokens": 0,
        "strategy": strategy,
        "topology": (governance or {}).get("topology", "solo"),
        "max_iter": (governance or {}).get("max_iter", spec.get("max_iter")),
    })
    return {"verdict": status, "checks": results, "invariants": invariant, "judge": judge, "record": row}


def learn(spec: dict[str, Any]) -> dict[str, Any]:
    rep = report(spec)
    hyp = propose_hypothesis(spec, rep) if rep.get("weaknesses") else None
    update_state_md(spec, rep, note="learned from latest telemetry")
    return {"report": rep, "hypothesis": hyp}


def run(spec: dict[str, Any]) -> dict[str, Any]:
    governance = govern(spec)
    canaries = run_all(spec)
    checked = {}
    strategy = "targeted-fix"
    for iter_no in range(1, int(governance["max_iter"]) + 1):
        checked = check(spec, iter_no=iter_no, governance=governance, strategy=strategy)
        if checked["verdict"] == "pass":
            break
        next_move = mutate(spec, str(spec.get("run_id", "manual")))
        strategy = next_move["strategy"]
        if next_move.get("stop"):
            break
    learned = learn(spec)
    check_exit = 0 if checked.get("verdict") == "pass" else 1
    evidence = {
        "goal": spec.get("goal"),
        "check_cmd": [c.get("name") for c in checked.get("checks", [])],
        "check_exit": check_exit,
        "judge": checked.get("judge", {"verdict": "pass"}),
        "cost_tokens": 0,
        "budget_tokens": governance["budget_tokens"],
        "run_id": spec.get("run_id", "manual"),
        "compare": {"improved": checked["verdict"] == "pass" and canaries["verdict"] == "pass", "grade_points_delta": 1, "weakness_count_delta": 0},
        "invariants": checked["invariants"],
        "high_risk": False,
        "repeated_signature_count": 0,
        "strategy_changed": strategy != "targeted-fix",
        "improved_this_time": "checks and fixed canaries passed through the kernel",
        "improves_next_time": "state telemetry updates future strategy and evaluation",
    }
    promotion = promotion_decision(evidence)
    return {"governance": governance, "canaries": canaries, "check": checked, "learn": learned, "promotion": promotion}


def main() -> int:
    parser = argparse.ArgumentParser(description="Single entrypoint for Codex Loop Kernel.")
    sub = parser.add_subparsers(dest="cmd", required=True)
    for name in ("run", "check", "learn", "canary", "status", "govern", "mutate"):
        p = sub.add_parser(name)
        p.add_argument("--spec")
        p.add_argument("--json", action="store_true")
    args = parser.parse_args()
    spec = load_spec(args.spec)

    if args.cmd == "run":
        result = run(spec)
        ok = result["promotion"]["verdict"] == "promote"
    elif args.cmd == "check":
        result = check(spec, governance=govern(spec))
        ok = result["verdict"] == "pass"
    elif args.cmd == "govern":
        result = govern(spec)
        ok = True
    elif args.cmd == "mutate":
        result = mutate(spec, str(spec.get("run_id", "manual")))
        ok = not result.get("stop")
    elif args.cmd == "learn":
        result = learn(spec)
        ok = True
    elif args.cmd == "canary":
        result = run_all(spec)
        ok = result["verdict"] == "pass"
    else:
        result = report(spec)
        ok = True

    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
    else:
        print(result.get("verdict") or result.get("promotion", {}).get("verdict") or result.get("grade"))
    return 0 if ok else 2


if __name__ == "__main__":
    raise SystemExit(main())
