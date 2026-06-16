#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_SPEC = PROJECT_ROOT / "loop.yaml"


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def load_json(path: Path, default: Any = None) -> Any:
    if not path.exists():
        return default
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def append_jsonl(path: Path, row: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n")


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    rows: list[dict[str, Any]] = []
    with path.open(encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                rows.append(json.loads(line))
            except json.JSONDecodeError:
                rows.append({"_decode_error": line[:160]})
    return rows


def load_spec(path: str | Path | None = None) -> dict[str, Any]:
    spec_path = Path(path or os.environ.get("LOOPS_SPEC") or DEFAULT_SPEC).expanduser()
    spec = load_json(spec_path, {})
    if not isinstance(spec, dict):
        raise ValueError(f"spec must be a JSON/YAML object: {spec_path}")
    spec["_spec_path"] = str(spec_path)
    spec.setdefault("project_root", str(PROJECT_ROOT))
    spec.setdefault("state_dir", "state")
    spec.setdefault("max_iter", 3)
    spec.setdefault("cost_ceiling_tokens", 12000)
    spec.setdefault("checks", [])
    spec.setdefault("canaries", "canaries")
    return spec


def state_dir(spec: dict[str, Any]) -> Path:
    raw = Path(str(spec.get("state_dir") or "state")).expanduser()
    if not raw.is_absolute():
        raw = Path(str(spec.get("project_root") or PROJECT_ROOT)) / raw
    raw.mkdir(parents=True, exist_ok=True)
    return raw


def path_for(spec: dict[str, Any], name: str) -> Path:
    mapping = {
        "runs": "runs.jsonl",
        "report": "eval_report.json",
        "hypotheses": "hypotheses.jsonl",
        "observations": "hypothesis_observations.jsonl",
        "promotion": "promotion_decision.json",
        "canaries": "canary_report.json",
    }
    return state_dir(spec) / mapping[name]


def record_run(spec: dict[str, Any], row: dict[str, Any]) -> dict[str, Any]:
    row = {"ts": utc_now(), **row}
    append_jsonl(path_for(spec, "runs"), row)
    return row


def update_state_md(spec: dict[str, Any], report: dict[str, Any] | None = None, note: str | None = None) -> Path:
    root = Path(str(spec.get("project_root") or PROJECT_ROOT))
    path = root / "STATE.md"
    report = report or load_json(path_for(spec, "report"), {})
    lines = [
        "# STATE - Loop Kernel",
        "",
        f"- updated: {utc_now()}",
        f"- goal: {spec.get('goal', 'unset')}",
        f"- last_grade: {report.get('grade', 'unknown')}",
        f"- success_rate_pct: {report.get('success_rate_pct', 'unknown')}",
        f"- false_success_suspect_rate_pct: {report.get('false_success_suspect_rate_pct', 'unknown')}",
        f"- cost_per_success_tokens: {report.get('cost_per_success_tokens', 'unknown')}",
        "",
        "## Open Signals",
    ]
    weaknesses = report.get("weaknesses") or []
    if weaknesses:
        lines.extend(f"- {item}" for item in weaknesses)
    else:
        lines.append("- none")
    if note:
        lines.extend(["", "## Latest Note", f"- {note}"])
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path


def main() -> int:
    parser = argparse.ArgumentParser(description="Persistent state helpers for Loop Kernel.")
    sub = parser.add_subparsers(dest="cmd", required=True)
    init = sub.add_parser("init")
    init.add_argument("--spec")
    rec = sub.add_parser("record")
    rec.add_argument("--spec")
    rec.add_argument("--run-id", required=True)
    rec.add_argument("--iter", type=int, default=1)
    rec.add_argument("--status", choices=["pass", "fail"], required=True)
    rec.add_argument("--signature", default="")
    rec.add_argument("--cost-tokens", type=int, default=0)
    args = parser.parse_args()
    spec = load_spec(getattr(args, "spec", None))
    if args.cmd == "init":
        state_dir(spec)
        update_state_md(spec, note="initialized")
        print(str(state_dir(spec)))
        return 0
    row = record_run(spec, {
        "run_id": args.run_id,
        "iter": args.iter,
        "goal": spec.get("goal"),
        "status": args.status,
        "failure_signature": args.signature,
        "cost_tokens": args.cost_tokens,
    })
    print(json.dumps(row, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
