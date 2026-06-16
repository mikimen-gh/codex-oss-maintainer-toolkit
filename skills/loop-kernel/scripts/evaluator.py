#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
from collections import Counter
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from state_store import append_jsonl, load_json, load_spec, path_for, read_jsonl, update_state_md, utc_now, write_json


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

    weaknesses: list[str] = []
    if total == 0:
        weaknesses.append("no telemetry")
    if false_success:
        weaknesses.append("false-success risk")
    if repeated:
        weaknesses.append("repeated failure signatures")
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
        "disconfirmation": "block if the expected metric does not move in the declared direction",
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


def main() -> int:
    parser = argparse.ArgumentParser(description="Evaluate loop performance and learning.")
    sub = parser.add_subparsers(dest="cmd", required=True)
    for name in ("report", "hypothesis", "decay"):
        p = sub.add_parser(name)
        p.add_argument("--spec")
        p.add_argument("--json", action="store_true")
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
        spec = load_spec(args.spec)
        result = observe(spec, load_json(args.hypothesis, {}), load_json(args.compare, {}))
    else:
        spec = load_spec(args.spec)
        rep = report(spec)
        if args.cmd == "report":
            result = rep
        elif args.cmd == "decay":
            result = decay(spec)
        else:
            result = propose_hypothesis(spec, rep)
    if getattr(args, "json", False):
        print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
    else:
        print(result.get("grade", result.get("hypothesis_id", json.dumps(result))))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
