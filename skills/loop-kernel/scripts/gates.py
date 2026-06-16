#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Any

from state_store import load_json, load_spec, path_for, utc_now, write_json


PATTERNS = [
    ("G1", "test_skip", "high", re.compile(r"\b(pytest\.skip|it\.skip|describe\.skip|test\.skip|xit\()\b")),
    ("G2", "tautological_assertion", "high", re.compile(r"\b(assert\s+True|expect\(true\)|expect\(([^)]*)\)\.to(Be|Equal)\(\2\)|toEqual\([^)]*\))")),
    ("G3", "forced_success_exit", "high", re.compile(r"(\|\|\s*true|;\s*exit\s+0|\bexit\s+0\b|return\s+0\s*#\s*ignore)")),
    ("G4", "catch_ignore", "med", re.compile(r"(except\s+.*:\s*(pass|return|continue)|catch\s*\([^)]*\)\s*{\s*})", re.DOTALL)),
    ("G5", "coverage_lowered", "med", re.compile(r"(coverageThreshold|minimum|threshold).{0,80}(-\s*\d+|\b[0-6]\d\b)", re.IGNORECASE | re.DOTALL)),
    ("G6", "ci_bypass", "high", re.compile(r"(continue-on-error:\s*true|skip-ci|CI\s*=\s*false|--no-verify)")),
    ("G7", "snapshot_force_update", "med", re.compile(r"(-u|--updateSnapshot|snapshot update|toMatchSnapshot\(\))", re.IGNORECASE)),
    ("G8", "warning_suppression", "low", re.compile(r"(eslint-disable|ts-ignore|type:\s*ignore|@SuppressWarnings|# noqa)")),
    ("G9", "mock_happy_path", "med", re.compile(r"(mockResolvedValue|mockReturnValue|jest\.fn\(\).{0,80}(true|success|200)|sinon\.stub)", re.DOTALL)),
    ("G10", "test_surface_shrank", "high", re.compile(r"^-\s*(def test_|it\(|test\(|describe\()", re.MULTILINE)),
    ("G11", "retry_mask", "med", re.compile(r"(\.retry\(\d+\)|retries:\s*\d+|flaky.*retry)", re.IGNORECASE)),
    ("G12", "expected_to_actual", "high", re.compile(r"expect\((result|actual|response|output)\)\.to(Be|Equal|StrictEqual)\(\1\)")),
    ("G13", "check_cmd_rewrite", "high", re.compile(r'("(test|lint|build)"\s*:\s*".*(true|exit 0|echo|--passWithNoTests))')),
    ("G14", "env_branch_skip", "high", re.compile(r"(if\s*\(?\s*(process\.env\.CI|CI)\s*\)?\s*(return|pass)|if\s*\(?\s*CI\s*\)?\s*return)")),
    ("G15", "test_file_delete", "high", re.compile(r"^---\s+a/.*(test|spec).*\n^\+\+\+\s+/dev/null", re.MULTILINE)),
]


def semantic_judge(diff_text: str) -> dict[str, Any]:
    findings = []
    for gid, rule, severity, pattern in PATTERNS:
        if pattern.search(diff_text):
            findings.append({"id": gid, "rule": rule, "severity": severity, "message": f"diff matches {gid}:{rule}"})
    high = [f for f in findings if f["severity"] == "high"]
    med = [f for f in findings if f["severity"] == "med"]
    return {
        "ts": utc_now(),
        "verdict": "block" if high else ("warn" if med else "pass"),
        "findings": findings,
    }


def sycophancy_guard(text: str) -> dict[str, Any]:
    lowered = text.lower()
    needles = [
        "ignore the rules",
        "relax the gate",
        "promote anyway",
        "because i said",
        "ユーザーが言ったから",
        "ルールを緩め",
        "とにかく通",
    ]
    hits = [n for n in needles if n in lowered]
    return {
        "ts": utc_now(),
        "verdict": "block" if hits else "pass",
        "findings": [{"rule": "sycophancy_drift", "severity": "high", "message": h} for h in hits],
    }


def delegation_guard(brief: str, required_terms: list[str]) -> dict[str, Any]:
    missing = [term for term in required_terms if term not in brief]
    return {
        "ts": utc_now(),
        "verdict": "block" if missing else "pass",
        "findings": [{"rule": "lossy_delegation", "severity": "high", "message": term} for term in missing],
    }


def falsifiability_score(hypothesis: dict[str, Any]) -> dict[str, Any]:
    axes = {
        "claim": bool(hypothesis.get("claim")),
        "intervention": bool(hypothesis.get("intervention")),
        "expected_movement": bool(hypothesis.get("expected_movement")),
        "disconfirmation": bool(hypothesis.get("disconfirmation")),
    }
    score = sum(1 for ok in axes.values() if ok) / len(axes)
    return {
        "ts": utc_now(),
        "hypothesis_id": hypothesis.get("hypothesis_id"),
        "score": round(score, 2),
        "decision": "allow" if score >= 0.75 else "block",
        "axes": axes,
    }


def counterfactual(actual: dict[str, Any], controls: list[dict[str, Any]]) -> dict[str, Any]:
    actual_effect = float(actual.get("grade_points_delta") or 0) - max(0.0, float(actual.get("false_success_suspect_rate_pct_delta") or 0) / 10)
    control_effect = max([float(c.get("grade_points_delta") or 0) for c in controls] or [0.0])
    effect_size = actual_effect - control_effect
    return {
        "ts": utc_now(),
        "verdict": "causal_support" if actual.get("improved") and effect_size >= 0.25 else "causal_unproven",
        "effect_size": round(effect_size, 3),
        "actual_effect": round(actual_effect, 3),
        "best_control_effect": round(control_effect, 3),
    }


def invariant_guard(spec: dict[str, Any], changed_files: list[str]) -> dict[str, Any]:
    findings = []
    read_only = set(spec.get("read_only_paths") or ["vendor/prior-art/loops"])
    for item in changed_files:
        for protected in read_only:
            if item.startswith(protected):
                findings.append({"rule": "read_only_prior_art", "severity": "high", "message": item})
    for rel in ("CODEX.md", "SPEC.md", "STATE.md", "loop.yaml"):
        if not (Path(str(spec.get("project_root"))) / rel).exists():
            findings.append({"rule": "required_file_missing", "severity": "high", "message": rel})
    return {
        "ts": utc_now(),
        "verdict": "block" if findings else "pass",
        "findings": findings,
    }


def promotion_decision(evidence: dict[str, Any]) -> dict[str, Any]:
    blockers = []
    warnings = []
    compare = evidence.get("compare") or {}
    judge = evidence.get("judge") or {}
    falsifiability = evidence.get("falsifiability") or {}
    causal = evidence.get("counterfactual") or {}
    invariants = evidence.get("invariants") or {}
    sycophancy = evidence.get("sycophancy") or {}
    required = ("goal", "check_cmd", "check_exit", "judge", "cost_tokens", "run_id")
    for field in required:
        if field not in evidence:
            blockers.append(f"missing required evidence: {field}")

    if not compare.get("improved"):
        blockers.append("evaluation did not improve")
    if judge.get("verdict") == "block":
        blockers.append("semantic judge blocked the diff")
    elif judge.get("verdict") == "warn":
        warnings.append("semantic judge warned on the diff")
    if evidence.get("check_exit") not in (0, None):
        blockers.append(f"check command failed: {evidence.get('check_exit')}")
    if falsifiability.get("decision") == "block":
        blockers.append("hypothesis is not falsifiable")
    if evidence.get("high_risk") and causal.get("verdict") != "causal_support":
        blockers.append("high-risk change lacks counterfactual support")
    if invariants.get("verdict") == "block":
        blockers.append("invariant contract failed")
    if sycophancy.get("verdict") == "block":
        blockers.append("conversational drift or sycophancy pressure detected")
    if compare.get("weakness_count_delta", 0) > 0:
        blockers.append("new weaknesses were introduced")
    if compare.get("grade_points_delta", 0) == 0:
        warnings.append("no grade-point movement")
    if evidence.get("cost_tokens", 0) > evidence.get("budget_tokens", evidence.get("cost_tokens", 0) + 1):
        blockers.append("cost budget exceeded")
    if evidence.get("external_effects") and not evidence.get("user_approved_external_effects"):
        blockers.append("external effects lack user approval")
    if evidence.get("repeated_signature_count", 0) >= 3 and not evidence.get("strategy_changed"):
        blockers.append("same failure signature repeated without strategy change")
    if not evidence.get("improved_this_time"):
        warnings.append("missing narrative: improved_this_time")
    if not evidence.get("improves_next_time"):
        warnings.append("missing narrative: improves_next_time")

    return {
        "ts": utc_now(),
        "verdict": "promote" if not blockers else "reject",
        "blockers": blockers,
        "warnings": warnings,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Objective gates for Loop Kernel.")
    sub = parser.add_subparsers(dest="cmd", required=True)
    judge = sub.add_parser("judge")
    judge.add_argument("--diff", type=Path, required=True)
    judge.add_argument("--json", action="store_true")
    promote = sub.add_parser("promote")
    promote.add_argument("--spec")
    promote.add_argument("--evidence", type=Path, required=True)
    promote.add_argument("--write", action="store_true")
    promote.add_argument("--json", action="store_true")
    inv = sub.add_parser("invariants")
    inv.add_argument("--spec")
    inv.add_argument("--changed-file", action="append", default=[])
    inv.add_argument("--json", action="store_true")
    args = parser.parse_args()

    if args.cmd == "judge":
        result = semantic_judge(args.diff.read_text(encoding="utf-8"))
    elif args.cmd == "invariants":
        result = invariant_guard(load_spec(args.spec), args.changed_file)
    else:
        spec = load_spec(args.spec)
        result = promotion_decision(load_json(args.evidence, {}))
        if args.write:
            write_json(path_for(spec, "promotion"), result)
    if getattr(args, "json", False):
        print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
    else:
        print(result["verdict"])
    return 0 if result["verdict"] in {"pass", "promote"} else 2


if __name__ == "__main__":
    raise SystemExit(main())
