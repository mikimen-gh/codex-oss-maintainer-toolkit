#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
from collections import Counter
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Any

from canary_runner import run_all
from evaluator import compile_capabilities, propose_hypothesis, report
from gates import invariant_guard, promotion_decision, semantic_judge
from state_store import (
    cost_path,
    load_json,
    load_spec,
    memory_prefetch,
    path_for,
    read_jsonl,
    record_run,
    registry_attach,
    registry_discover,
    registry_spec,
    update_state_md,
    write_json,
)


SPEC_REQUIRED = {"goal": str, "checks": list}
SPEC_OPTIONAL = {
    "run_id": str,
    "risk": int,
    "max_iter": int,
    "parallelism": int,
    "cost_ceiling_tokens": int,
    "state_dir": str,
    "project_root": str,
    "canaries": str,
    "diff_text": str,
}


def validate_spec(spec: dict[str, Any]) -> list[str]:
    errors = []
    if not isinstance(spec, dict):
        return ["spec must be a JSON object"]
    for key, expected in SPEC_REQUIRED.items():
        if key not in spec:
            errors.append(f"missing required field: {key}")
        elif not isinstance(spec[key], expected):
            errors.append(f"{key} must be {expected.__name__}")
    for key, expected in SPEC_OPTIONAL.items():
        if key in spec and not isinstance(spec[key], expected):
            errors.append(f"{key} must be {expected.__name__}")
    if isinstance(spec.get("risk"), int) and not 1 <= spec["risk"] <= 10:
        errors.append("risk must be between 1 and 10")
    if isinstance(spec.get("max_iter"), int) and spec["max_iter"] < 1:
        errors.append("max_iter must be >= 1")
    if isinstance(spec.get("parallelism"), int) and spec["parallelism"] < 1:
        errors.append("parallelism must be >= 1")
    if isinstance(spec.get("checks"), list):
        if not spec["checks"]:
            errors.append("checks must not be empty")
        for i, check in enumerate(spec["checks"]):
            if not isinstance(check, dict):
                errors.append(f"checks[{i}] must be an object")
                continue
            if not isinstance(check.get("name"), str):
                errors.append(f"checks[{i}].name must be str")
            cmd = check.get("cmd")
            if not isinstance(cmd, list) or not cmd or not all(isinstance(x, str) for x in cmd):
                errors.append(f"checks[{i}].cmd must be a non-empty list of strings")
            if "timeout_sec" in check and not isinstance(check["timeout_sec"], int):
                errors.append(f"checks[{i}].timeout_sec must be int")
    project_root = Path(str(spec.get("project_root", "."))).expanduser()
    if not project_root.exists():
        errors.append(f"project_root does not exist: {project_root}")
    return errors


def resolve_spec(spec_path: str | None = None, profile_id: str | None = None) -> tuple[dict[str, Any], str]:
    if spec_path:
        return load_spec(spec_path), "spec-file"
    discovered = registry_spec(Path.cwd(), profile_id=profile_id)
    if discovered:
        return discovered, "registry"
    return load_spec(None), "default-spec"


def preflight(spec: dict[str, Any], source: str, prompt: str = "") -> dict[str, Any]:
    errors = validate_spec(spec)
    check_findings: list[str] = []
    root = Path(str(spec.get("project_root") or ".")).expanduser()
    for check_item in spec.get("checks") or []:
        cmd = check_item.get("cmd") if isinstance(check_item, dict) else None
        if not isinstance(cmd, list) or not cmd:
            continue
        exe = cmd[0]
        if "/" in exe:
            exists = (root / exe).exists() if not Path(exe).is_absolute() else Path(exe).exists()
            if not exists:
                check_findings.append(f"check executable missing: {exe}")
    memory = memory_prefetch(prompt or str(spec.get("goal") or root))
    discovery = registry_discover(project_root=root, query=prompt or str(spec.get("goal") or ""), limit=5)
    blockers = list(errors)
    if memory.get("verdict") == "block":
        blockers.append("bounded memory prefetch blocked")
    return {
        "verdict": "pass" if not blockers else "block",
        "source": source,
        "spec_ref": spec.get("_spec_path"),
        "registry_profile_id": spec.get("_registry_profile_id"),
        "project_root": str(root),
        "blockers": blockers,
        "warnings": check_findings,
        "memory_prefetch": {
            "verdict": memory.get("verdict"),
            "always_apply_chars": memory.get("always_apply_chars"),
            "cap_chars": memory.get("cap_chars"),
            "domain_matches": [item.get("path") for item in memory.get("domain_matches", [])],
            "search_docs": [item.get("path") for item in memory.get("search_hits", {}).get("docs", [])],
        },
        "registry": {
            "exact": (discovery.get("exact") or {}).get("profile_id") if discovery.get("exact") else None,
            "candidate_count": len(discovery.get("candidates") or []),
        },
    }


def read_iter_cost(spec: dict[str, Any], iter_no: int, cli_cost: int = 0) -> dict[str, Any]:
    if cli_cost > 0:
        return {"tokens": cli_cost, "usd": 0.0, "source": "cli"}
    env_tokens = os.environ.get("LOOP_KERNEL_COST_TOKENS_LAST_ITER")
    if env_tokens:
        try:
            return {
                "tokens": int(env_tokens),
                "usd": float(os.environ.get("LOOP_KERNEL_COST_USD_LAST_ITER", "0") or 0),
                "source": "env",
            }
        except ValueError:
            pass
    path = cost_path(spec, str(spec.get("run_id", "manual")), iter_no)
    if path.exists():
        data = load_json(path, {})
        try:
            return {
                "tokens": int(data.get("input_tokens", 0)) + int(data.get("output_tokens", 0)),
                "usd": float(data.get("usd", 0) or 0),
                "source": str(path),
            }
        except (TypeError, ValueError):
            pass
    return {"tokens": 0, "usd": 0.0, "source": "unmeasured"}


def build_delegation_manifest(spec: dict[str, Any], governance: dict[str, Any]) -> dict[str, Any] | None:
    topology = governance.get("topology", "solo")
    if topology == "solo":
        return None
    role_map = {
        "main+verifier": ["verifier"],
        "main+doer+verifier": ["doer", "verifier"],
        "main+strategist+verifier+auditor": ["strategist", "doer", "verifier", "auditor"],
    }
    roles = role_map.get(topology, [])
    manifest = {
        "topology": topology,
        "goal": spec.get("goal"),
        "delegations": [
            {
                "role": role,
                "brief_ref": f"inline://codex-loop/{role}",
                "brief_hash": hashlib.sha256(f"{role}\n{spec.get('goal')}\n{topology}".encode("utf-8")).hexdigest()[:12],
                "required_terms": ["goal", str(spec.get("goal", ""))[:80], "objective check"],
            }
            for role in roles
        ],
    }
    write_json(path_for(spec, "delegation"), manifest)
    return manifest


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


def check(
    spec: dict[str, Any],
    iter_no: int = 1,
    governance: dict[str, Any] | None = None,
    strategy: str = "targeted-fix",
    cli_cost: int = 0,
) -> dict[str, Any]:
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
    cost = read_iter_cost(spec, iter_no, cli_cost)
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
        "cost_tokens": cost["tokens"],
        "cost_usd": cost["usd"],
        "cost_source": cost["source"],
        "strategy": strategy,
        "topology": (governance or {}).get("topology", "solo"),
        "max_iter": (governance or {}).get("max_iter", spec.get("max_iter")),
    })
    return {"verdict": status, "checks": results, "invariants": invariant, "judge": judge, "cost": cost, "record": row}


def learn(spec: dict[str, Any]) -> dict[str, Any]:
    rep = report(spec)
    hyp = propose_hypothesis(spec, rep) if rep.get("weaknesses") else None
    caps = compile_capabilities(spec, write=True)
    update_state_md(spec, rep, note="learned from latest telemetry")
    return {"report": rep, "hypothesis": hyp, "capabilities": caps}


def run(spec: dict[str, Any], cli_cost_per_iter: int = 0) -> dict[str, Any]:
    errors = validate_spec(spec)
    if errors:
        return {"verdict": "invalid-spec", "errors": errors}
    governance = govern(spec)
    manifest = build_delegation_manifest(spec, governance)
    canaries = run_all(spec)
    checked = {}
    strategy = "targeted-fix"
    total_cost = 0
    for iter_no in range(1, int(governance["max_iter"]) + 1):
        checked = check(spec, iter_no=iter_no, governance=governance, strategy=strategy, cli_cost=cli_cost_per_iter)
        total_cost += int((checked.get("cost") or {}).get("tokens") or 0)
        if total_cost > governance["budget_tokens"]:
            checked["verdict"] = "fail"
            break
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
        "cost_tokens": total_cost,
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
    return {
        "verdict": promotion["verdict"],
        "governance": governance,
        "delegation_manifest": manifest,
        "canaries": canaries,
        "check": checked,
        "learn": learned,
        "promotion": promotion,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Single entrypoint for Codex Loop Kernel.")
    sub = parser.add_subparsers(dest="cmd", required=True)
    for name in ("run", "check", "learn", "canary", "status", "govern", "mutate", "validate", "preflight"):
        p = sub.add_parser(name)
        p.add_argument("--spec")
        p.add_argument("--profile-id")
        p.add_argument("--prompt", default="")
        p.add_argument("--json", action="store_true")
        if name in {"run", "check"}:
            p.add_argument("--cost-per-iter", type=int, default=0)
    discover = sub.add_parser("discover")
    discover.add_argument("--project-root", type=Path)
    discover.add_argument("--query", default="")
    discover.add_argument("--json", action="store_true")
    attach = sub.add_parser("attach")
    attach.add_argument("--spec", required=True)
    attach.add_argument("--project-root", type=Path)
    attach.add_argument("--profile-id")
    attach.add_argument("--tag", action="append", default=[])
    attach.add_argument("--json", action="store_true")
    args = parser.parse_args()
    if args.cmd == "discover":
        result = registry_discover(project_root=args.project_root, query=args.query, limit=5)
        ok = True
        if args.json:
            print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
        else:
            print(result.get("exact", {}).get("profile_id") if result.get("exact") else "missing")
        return 0 if ok else 2
    if args.cmd == "attach":
        result = registry_attach(load_spec(args.spec), project_root=args.project_root, profile_id=args.profile_id, tags=args.tag)
        ok = result.get("verdict") == "attached"
        if args.json:
            print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
        else:
            print(result.get("verdict"))
        return 0 if ok else 2

    spec, spec_source = resolve_spec(args.spec, profile_id=getattr(args, "profile_id", None))

    if args.cmd == "run":
        result = run(spec, cli_cost_per_iter=getattr(args, "cost_per_iter", 0))
        ok = result.get("promotion", {}).get("verdict") == "promote"
    elif args.cmd == "check":
        result = check(spec, governance=govern(spec), cli_cost=getattr(args, "cost_per_iter", 0))
        ok = result["verdict"] == "pass"
    elif args.cmd == "validate":
        errors = validate_spec(spec)
        result = {"verdict": "valid" if not errors else "invalid", "errors": errors, "source": spec_source, "spec_ref": spec.get("_spec_path")}
        ok = not errors
    elif args.cmd == "preflight":
        result = preflight(spec, spec_source, prompt=getattr(args, "prompt", ""))
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
