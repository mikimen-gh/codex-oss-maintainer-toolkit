#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
from collections import Counter
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from state_store import append_jsonl, global_path, load_json, load_spec, path_for, read_jsonl, registry_spec, stable_hash, update_state_md, utc_now, write_json


def resolve_spec(spec_path: str | None = None) -> dict[str, Any]:
    if spec_path:
        return load_spec(spec_path)
    return registry_spec(Path.cwd()) or load_spec(None)


def grade_from(points: int) -> str:
    if points >= 9:
        return "A"
    if points >= 7:
        return "B"
    if points >= 5:
        return "C"
    return "D"


def report(spec: dict[str, Any]) -> dict[str, Any]:
    rows = read_jsonl(path_for(spec, "runs"))
    global_rows = read_jsonl(global_path("runs"))
    total = len(rows)
    passes = sum(1 for r in rows if r.get("status") == "pass")
    successes = max(passes, 1)
    false_success = sum(1 for r in rows if r.get("status") == "pass" and r.get("gate_verdict") == "block")
    signatures = [str(r.get("failure_signature") or "") for r in rows if r.get("failure_signature")]
    repeated = {k: v for k, v in Counter(signatures).items() if v >= 2}
    cost = sum(int(r.get("cost_tokens") or 0) for r in rows)
    canary_report = load_json(path_for(spec, "canaries"), {})
    canary_total = int(canary_report.get("total") or 0)
    canary_passed = int(canary_report.get("passed") or 0)
    same_run_global = [r for r in global_rows if r.get("run_id") == spec.get("run_id")]
    global_signatures = [str(r.get("sig_hash") or "") for r in global_rows if r.get("sig_hash")]
    cross_repeated = {k: v for k, v in Counter(global_signatures).items() if v >= 3}
    capability_candidates = compile_capabilities(spec, write=False)

    weaknesses: list[str] = []
    if total == 0:
        weaknesses.append("no telemetry")
    if false_success:
        weaknesses.append("false-success risk")
    if repeated:
        weaknesses.append("repeated failure signatures")
    if cross_repeated and not capability_candidates.get("candidates"):
        weaknesses.append("cross-session failure signatures are not compiled")
    if canary_total == 0:
        weaknesses.append("no canary corpus result")
    elif canary_passed < canary_total:
        weaknesses.append("canary failures")

    points = 0
    if total:
        points += 2
    if total and passes / total >= 0.5:
        points += 2
    if false_success == 0:
        points += 2
    if not repeated:
        points += 1
    if canary_total and canary_passed == canary_total:
        points += 2
    if cost == 0 or cost / successes <= int(spec.get("cost_ceiling_tokens") or 12000):
        points += 1

    result = {
        "ts": utc_now(),
        "goal": spec.get("goal"),
        "total_runs": total,
        "pass_count": passes,
        "success_rate_pct": round((passes / total * 100) if total else 0.0, 2),
        "false_success_suspect_rate_pct": round((false_success / total * 100) if total else 0.0, 2),
        "repeated_signatures": repeated,
        "global_total_runs": len(global_rows),
        "same_run_global_records": len(same_run_global),
        "cross_repeated_signature_count": len(cross_repeated),
        "capability_candidate_count": len(capability_candidates.get("candidates", [])),
        "cost_tokens_total": cost,
        "cost_per_success_tokens": round(cost / successes, 2),
        "canary_pass_rate_pct": round((canary_passed / canary_total * 100) if canary_total else 0.0, 2),
        "weaknesses": weaknesses,
        "grade_points": points,
        "grade": grade_from(points),
    }
    write_json(path_for(spec, "report"), result)
    update_state_md(spec, result)
    return result


def compile_capabilities(spec: dict[str, Any], min_count: int = 3, write: bool = False) -> dict[str, Any]:
    rows = [r for r in read_jsonl(global_path("runs")) if r.get("failure_signature")]
    by_sig: dict[str, list[dict[str, Any]]] = {}
    for row in rows:
        sig_hash = str(row.get("sig_hash") or stable_hash(str(row.get("failure_signature") or "")))
        by_sig.setdefault(sig_hash, []).append(row)
    candidates = []
    for sig_hash, group in by_sig.items():
        if len(group) < min_count:
            continue
        projects = {str(r.get("project_key") or "") for r in group if r.get("project_key")}
        sessions = {str(r.get("session") or "") for r in group if r.get("session") and r.get("session") != "unknown"}
        run_ids = {str(r.get("run_id") or "") for r in group if r.get("run_id")}
        cross_project = len(projects) > 1
        cross_session = len(sessions) > 1
        cross_run = len(run_ids) > 1
        confidence = "high" if cross_project or cross_session else ("medium" if cross_run else "low")
        first = group[0]
        candidates.append({
            "ts": utc_now(),
            "candidate_id": "cap_" + sig_hash,
            "sig_hash": sig_hash,
            "failure_signature": first.get("failure_signature"),
            "count": len(group),
            "project_count": len(projects),
            "session_count": len(sessions),
            "run_count": len(run_ids),
            "cross_project": cross_project,
            "cross_session": cross_session,
            "cross_run": cross_run,
            "confidence": confidence,
            "lesson": "Repeated failure signature should become a reusable check, guard, or project lesson before promotion.",
            "source": "global_runs.jsonl",
        })
    candidates.sort(key=lambda c: (-int(c["count"]), c["confidence"] != "high", str(c["sig_hash"])))
    result = {"ts": utc_now(), "min_count": min_count, "candidates": candidates}
    if write:
        existing_ids = {str(r.get("candidate_id") or "") for r in read_jsonl(global_path("capabilities"))}
        for candidate in candidates:
            if candidate["candidate_id"] not in existing_ids:
                append_jsonl(global_path("capabilities"), candidate)
    return result


def compare(before: dict[str, Any], after: dict[str, Any]) -> dict[str, Any]:
    grade_delta = int(after.get("grade_points") or 0) - int(before.get("grade_points") or 0)
    false_success_delta = float(after.get("false_success_suspect_rate_pct") or 0) - float(before.get("false_success_suspect_rate_pct") or 0)
    cost_delta = float(after.get("cost_per_success_tokens") or 0) - float(before.get("cost_per_success_tokens") or 0)
    weakness_delta = len(after.get("weaknesses") or []) - len(before.get("weaknesses") or [])
    regressions = []
    if false_success_delta > 0:
        regressions.append("false-success risk worsened")
    if weakness_delta > 0:
        regressions.append("weakness count increased")
    return {
        "ts": utc_now(),
        "improved": grade_delta > 0 and not regressions,
        "grade_points_delta": grade_delta,
        "false_success_suspect_rate_pct_delta": false_success_delta,
        "cost_per_success_tokens_delta": cost_delta,
        "weakness_count_delta": weakness_delta,
        "regressions": regressions,
        "before_grade": before.get("grade"),
        "after_grade": after.get("grade"),
    }


def disconfirmation_for(expected: dict[str, Any]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for metric, rule in expected.items():
        direction = str(rule.get("direction") or "")
        if direction == "up":
            out[metric] = {"bad_if_delta_less_than": float(rule.get("min_delta") or 0)}
        elif direction == "down":
            out[metric] = {"bad_if_delta_greater_than": -float(rule.get("min_delta") or 0)}
        elif direction == "not_up_more_than_pct":
            out[metric] = {"bad_if_pct_increase_greater_than": float(rule.get("max_pct") or 0)}
        else:
            out[metric] = {"bad_if_unobserved": True}
    return out


def propose_hypothesis(spec: dict[str, Any], rep: dict[str, Any]) -> dict[str, Any]:
    weakness = (rep.get("weaknesses") or ["no weakness"])[0]
    if "false-success" in weakness:
        intervention = "tighten semantic and promotion gates before accepting pass records"
        expected = {"false_success_suspect_rate_pct": {"direction": "down", "min_delta": 10}}
        blocklist = []
    elif "canary" in weakness:
        intervention = "add or repair fixed external canaries before promotion"
        expected = {"canary_pass_rate_pct": {"direction": "up", "min_delta": 20}}
        blocklist = ["canary_pass_rate_pct"]
    elif "repeated" in weakness:
        intervention = "change next strategy after repeated signature instead of retrying"
        expected = {"repeated_signature_count": {"direction": "down", "min_delta": 1}}
        blocklist = ["repeated_signature_count"]
    else:
        intervention = "record richer telemetry and rerun the objective gate"
        expected = {"grade_points": {"direction": "up", "min_delta": 1}}
        blocklist = ["grade_points"]
    raw_id = f"{weakness}\n{intervention}".encode("utf-8")
    hypothesis = {
        "ts": utc_now(),
        "hypothesis_id": "hyp_" + hashlib.sha256(raw_id).hexdigest()[:12],
        "weakness": weakness,
        "claim": f"Loop quality is limited by {weakness}.",
        "intervention": intervention,
        "expected_movement": expected,
        "disconfirmation": disconfirmation_for(expected),
        "self_confirmation_blocklist": blocklist,
        "confidence": 0.55,
    }
    append_jsonl(path_for(spec, "hypotheses"), hypothesis)
    return hypothesis


def supported_by_nonblocked_metric(hypothesis: dict[str, Any], cmp: dict[str, Any]) -> bool:
    blocked = set(hypothesis.get("self_confirmation_blocklist") or [])
    expected = hypothesis.get("expected_movement") or {}
    metric_deltas = {
        "grade_points": cmp.get("grade_points_delta"),
        "false_success_suspect_rate_pct": cmp.get("false_success_suspect_rate_pct_delta"),
        "cost_per_success_tokens": cmp.get("cost_per_success_tokens_delta"),
        "weakness_count": -cmp.get("weakness_count_delta", 0),
    }
    supported = []
    for metric, rule in expected.items():
        value = metric_deltas.get(metric)
        if value is None:
            continue
        direction = rule.get("direction")
        if direction == "up" and value >= float(rule.get("min_delta") or 0):
            supported.append(metric)
        elif direction == "down" and value <= -float(rule.get("min_delta") or 0):
            supported.append(metric)
        elif direction == "not_up_more_than_pct" and value <= float(rule.get("max_pct") or 0):
            supported.append(metric)
    return any(metric not in blocked for metric in supported)


def observe(spec: dict[str, Any], hypothesis: dict[str, Any], cmp: dict[str, Any]) -> dict[str, Any]:
    before = float(hypothesis.get("confidence") or 0.5)
    supported = bool(cmp.get("improved")) and supported_by_nonblocked_metric(hypothesis, cmp)
    after = min(0.95, before + 0.12) if supported else max(0.05, before - 0.18)
    row = {
        "ts": utc_now(),
        "hypothesis_id": hypothesis.get("hypothesis_id"),
        "confidence_before": before,
        "confidence_after": round(after, 3),
        "decision": "promote" if supported else "reject",
        "self_confirmation_blocklist": hypothesis.get("self_confirmation_blocklist") or [],
        "supported_by_nonblocked_metric": supported,
        "compare": cmp,
    }
    append_jsonl(path_for(spec, "observations"), row)
    return row


def decay(spec: dict[str, Any], days: int = 30) -> dict[str, Any]:
    cutoff = datetime.now(timezone.utc) - timedelta(days=days)
    observations = read_jsonl(path_for(spec, "observations"))
    latest: dict[str, dict[str, Any]] = {}
    for row in observations:
        hid = str(row.get("hypothesis_id") or "")
        if hid:
            latest[hid] = row
    changed = []
    for row in read_jsonl(path_for(spec, "hypotheses")):
        ts = row.get("ts")
        try:
            seen = datetime.fromisoformat(str(latest.get(row.get("hypothesis_id"), row).get("ts") or ts))
        except ValueError:
            continue
        if seen < cutoff:
            before = float(row.get("confidence") or 0.5)
            after = round(max(0.05, before * 0.85), 3)
            event = {
                "ts": utc_now(),
                "hypothesis_id": row.get("hypothesis_id"),
                "confidence_before": before,
                "confidence_after": after,
                "decision": "decay",
                "reason": f"no observation for {days}+ days",
            }
            append_jsonl(path_for(spec, "observations"), event)
            changed.append(event)
    return {"ts": utc_now(), "decayed": changed, "days": days}


def deploy_readiness(spec: dict[str, Any]) -> dict[str, Any]:
    rep = report(spec)
    blockers = []
    warnings = []
    if not spec.get("checks"):
        blockers.append("spec has no objective checks")
    if rep.get("canary_pass_rate_pct") != 100.0:
        blockers.append("fixed canaries have not passed")
    if rep.get("false_success_suspect_rate_pct", 100.0) > 0:
        blockers.append("false-success suspicion is non-zero")
    if rep.get("total_runs", 0) < 1:
        blockers.append("no kernel run telemetry")
    if rep.get("total_runs", 0) < 5:
        warnings.append("less than 5 real-project runs; deploy-ready, not production-proven")
    if rep.get("cost_tokens_total", 0) == 0:
        warnings.append("cost input has not been measured yet")
    if rep.get("global_total_runs", 0) == 0:
        warnings.append("global ledger has no records yet")
    result = {
        "ts": utc_now(),
        "verdict": "ready" if not blockers else "not-ready",
        "blockers": blockers,
        "warnings": warnings,
        "report": rep,
    }
    write_json(path_for(spec, "deploy"), result)
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description="Evaluate loop performance and learning.")
    sub = parser.add_subparsers(dest="cmd", required=True)
    for name in ("report", "hypothesis", "decay", "deploy", "capabilities"):
        p = sub.add_parser(name)
        p.add_argument("--spec")
        p.add_argument("--json", action="store_true")
        if name == "capabilities":
            p.add_argument("--min-count", type=int, default=3)
            p.add_argument("--write", action="store_true")
    obs_p = sub.add_parser("observe")
    obs_p.add_argument("--spec")
    obs_p.add_argument("--hypothesis", type=Path, required=True)
    obs_p.add_argument("--compare", type=Path, required=True)
    obs_p.add_argument("--json", action="store_true")
    cmp_p = sub.add_parser("compare")
    cmp_p.add_argument("--before", type=Path, required=True)
    cmp_p.add_argument("--after", type=Path, required=True)
    cmp_p.add_argument("--json", action="store_true")
    args = parser.parse_args()

    if args.cmd == "compare":
        result = compare(load_json(args.before, {}), load_json(args.after, {}))
    elif args.cmd == "observe":
        spec = resolve_spec(args.spec)
        result = observe(spec, load_json(args.hypothesis, {}), load_json(args.compare, {}))
    else:
        spec = resolve_spec(args.spec)
        rep = report(spec)
        if args.cmd == "report":
            result = rep
        elif args.cmd == "decay":
            result = decay(spec)
        elif args.cmd == "deploy":
            result = deploy_readiness(spec)
        elif args.cmd == "capabilities":
            result = compile_capabilities(spec, min_count=args.min_count, write=args.write)
        else:
            result = propose_hypothesis(spec, rep)
    if getattr(args, "json", False):
        print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
    else:
        print(result.get("grade", result.get("hypothesis_id", json.dumps(result))))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
