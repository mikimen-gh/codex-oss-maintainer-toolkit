#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from gates import delegation_guard, promotion_decision, semantic_judge, sycophancy_guard
from state_store import load_json, load_spec, path_for, utc_now, write_json


def run_case(case: dict[str, Any]) -> dict[str, Any]:
    kind = case.get("kind")
    expected = case.get("expected_verdict", "block")
    if kind == "gaming_attempt":
        actual = semantic_judge(str(case.get("diff") or ""))
    elif kind in {"sycophancy_drift", "identity_drift"}:
        actual = sycophancy_guard(str(case.get("prompt") or ""))
    elif kind == "lossy_delegation":
        actual = delegation_guard(str(case.get("brief") or ""), list(case.get("required_terms") or []))
    elif kind == "theater_iteration":
        actual = promotion_decision(case.get("evidence") or {})
    else:
        actual = {"verdict": "block", "findings": [{"rule": "unknown_canary", "message": str(kind)}]}
    return {
        "name": case.get("name") or kind,
        "kind": kind,
        "expected": expected,
        "actual": actual.get("verdict"),
        "passed": actual.get("verdict") == expected,
        "findings": actual.get("findings") or actual.get("blockers") or [],
    }


def discover(root: Path) -> list[Path]:
    return sorted(root.glob("*/case.json"))


def run_all(spec: dict[str, Any]) -> dict[str, Any]:
    root = Path(str(spec.get("canaries") or "canaries"))
    if not root.is_absolute():
        root = Path(str(spec.get("project_root"))) / root
    cases = [run_case(load_json(path, {})) for path in discover(root)]
    passed = sum(1 for item in cases if item["passed"])
    result = {
        "ts": utc_now(),
        "total": len(cases),
        "passed": passed,
        "verdict": "pass" if cases and passed == len(cases) else "block",
        "cases": cases,
    }
    write_json(path_for(spec, "canaries"), result)
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description="Run fixed external canaries.")
    parser.add_argument("--spec")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()
    result = run_all(load_spec(args.spec))
    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
    else:
        print(result["verdict"])
        for case in result["cases"]:
            print(f"{case['name']}: {case['actual']} expected {case['expected']}")
    return 0 if result["verdict"] == "pass" else 2


if __name__ == "__main__":
    raise SystemExit(main())
