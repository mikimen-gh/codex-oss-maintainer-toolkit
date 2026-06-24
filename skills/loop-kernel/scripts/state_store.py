#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sqlite3
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_SPEC = PROJECT_ROOT / "loop.yaml"
DEFAULT_GLOBAL_STATE = Path(os.environ.get("LOOP_KERNEL_STATE_DIR") or os.environ.get("LOOPS_GLOBAL_STATE_DIR") or "~/.local/state/loop-kernel").expanduser()
DEFAULT_LESSONS = Path(os.environ.get("LOOP_KERNEL_LESSONS_PATH") or os.environ.get("CODEX_LESSONS_PATH") or "~/.local/share/loop-kernel/lessons.md").expanduser()
ALWAYS_BEGIN = "<!-- ALWAYS_APPLY_MEMORY_BEGIN -->"
ALWAYS_END = "<!-- ALWAYS_APPLY_MEMORY_END -->"


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
    if not spec_path.is_absolute():
        spec_path = (Path.cwd() / spec_path).resolve()
    spec = load_json(spec_path, {})
    if not isinstance(spec, dict):
        raise ValueError(f"spec must be a JSON/YAML object: {spec_path}")
    spec["_spec_path"] = str(spec_path)
    spec.setdefault("project_root", str(spec_path.parent))
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
        "delegation": "delegation_manifest.json",
        "deploy": "deploy_readiness.json",
        "lesson_candidates": "lesson_candidates.jsonl",
        "canary_candidates": "canary_candidates.jsonl",
        "court_evidence": "court_evidence.jsonl",
    }
    return state_dir(spec) / mapping[name]


def cost_path(spec: dict[str, Any], run_id: str, iter_no: int) -> Path:
    return state_dir(spec) / f"cost-{run_id}-iter{iter_no}.json"


def global_state_dir() -> Path:
    DEFAULT_GLOBAL_STATE.mkdir(parents=True, exist_ok=True)
    return DEFAULT_GLOBAL_STATE


def global_path(name: str) -> Path:
    mapping = {
        "runs": "global_runs.jsonl",
        "capabilities": "capability_candidates.jsonl",
        "report": "global_report.json",
        "memory_check": "memory_bounded_check.json",
        "memory_retire": "memory_retire_candidates.json",
        "memory_sync": "memory_sync_candidates.jsonl",
        "sqlite": "loops_memory.sqlite",
        "registry": "registry.sqlite",
    }
    return global_state_dir() / mapping[name]


def stable_hash(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()[:12]


def current_session_id() -> str:
    for key in ("CODEX_THREAD_ID", "CODEX_SESSION_ID", "CODEX_CONVERSATION_ID", "CLAUDE_SESSION_ID", "SESSION_ID"):
        value = os.environ.get(key)
        if value:
            return value[:80]
    return "unknown"


def project_key(spec: dict[str, Any]) -> str:
    root = Path(str(spec.get("project_root") or PROJECT_ROOT)).expanduser().resolve()
    return stable_hash(str(root))


def git_remote(project_root: Path) -> str:
    try:
        proc = subprocess.run(
            ["git", "-C", str(project_root), "remote", "get-url", "origin"],
            text=True,
            capture_output=True,
            timeout=5,
        )
    except (OSError, subprocess.SubprocessError):
        return ""
    return proc.stdout.strip() if proc.returncode == 0 else ""


def project_identity(project_root: str | Path | None = None) -> dict[str, str]:
    root = Path(project_root or Path.cwd()).expanduser().resolve()
    remote = git_remote(root)
    identity_source = remote or str(root)
    return {
        "project_root": str(root),
        "git_remote": remote,
        "project_key": stable_hash(identity_source),
        "identity_source": "git_remote" if remote else "path",
    }


def record_global_run(spec: dict[str, Any], row: dict[str, Any]) -> dict[str, Any]:
    signature = str(row.get("failure_signature") or "")[:240]
    slim = {
        "ts": row.get("ts") or utc_now(),
        "run_id": row.get("run_id"),
        "project_key": project_key(spec),
        "project_root": str(Path(str(spec.get("project_root") or PROJECT_ROOT)).expanduser().resolve()),
        "spec_path": str(spec.get("_spec_path") or ""),
        "goal": row.get("goal"),
        "iter": row.get("iter"),
        "status": row.get("status"),
        "failure_signature": signature,
        "sig_hash": stable_hash(signature) if signature else "",
        "gate_verdict": row.get("gate_verdict"),
        "judge_verdict": row.get("judge_verdict"),
        "strategy": row.get("strategy"),
        "topology": row.get("topology"),
        "cost_tokens": int(row.get("cost_tokens") or 0),
        "cost_usd": float(row.get("cost_usd") or 0.0),
        "cost_source": row.get("cost_source"),
        "session": current_session_id(),
    }
    append_jsonl(global_path("runs"), slim)
    try:
        index_global_run(slim)
    except sqlite3.Error:
        pass
    return slim


def record_run(spec: dict[str, Any], row: dict[str, Any]) -> dict[str, Any]:
    row = {"ts": utc_now(), **row}
    append_jsonl(path_for(spec, "runs"), row)
    record_global_run(spec, row)
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


def extract_always_apply(text: str) -> tuple[str, bool]:
    if ALWAYS_BEGIN not in text or ALWAYS_END not in text:
        return text, False
    start = text.index(ALWAYS_BEGIN) + len(ALWAYS_BEGIN)
    end = text.index(ALWAYS_END, start)
    return text[start:end].strip(), True


def parse_lesson_blocks(text: str) -> list[dict[str, Any]]:
    matches = list(re.finditer(r"^###\s+(\d{4}-\d{2}-\d{2}):\s+(.+)$", text, re.M))
    blocks: list[dict[str, Any]] = []
    for i, match in enumerate(matches):
        start = match.start()
        end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
        body = text[start:end].strip()
        blocks.append({
            "date": match.group(1),
            "title": match.group(2).strip(),
            "chars": len(body),
            "body": body,
        })
    return blocks


def infer_domain(title: str, body: str) -> str:
    text = f"{title}\n{body}".lower()
    if any(k in text for k in ("loop", "ループ", "skill", "スキル", "capability")):
        return "loops-skill.md"
    if any(k in text for k in ("git", "push", "commit", "archive", "保存先", "sync")):
        return "git-permissions.md"
    if any(k in text for k in ("voicevox", "hook", "通知", "async")):
        return "voicevox-hooks.md"
    return "_retired.md"


def retire_candidates(text: str, stale_days: int = 45, max_block_chars: int = 1200) -> list[dict[str, Any]]:
    now = datetime.now(timezone.utc).date()
    out: list[dict[str, Any]] = []
    for block in parse_lesson_blocks(text):
        try:
            age = (now - datetime.fromisoformat(block["date"]).date()).days
        except ValueError:
            age = 0
        reasons = []
        if age >= stale_days:
            reasons.append(f"older than {stale_days} days")
        if int(block["chars"]) > max_block_chars:
            reasons.append(f"large lesson block >{max_block_chars} chars")
        if not reasons:
            continue
        out.append({
            "title": block["title"],
            "date": block["date"],
            "age_days": age,
            "chars": block["chars"],
            "reasons": reasons,
            "suggested_target": infer_domain(block["title"], block["body"]),
        })
    return out[:20]


def domain_matches(prompt: str, domain_dir: Path) -> list[Path]:
    low = prompt.lower()
    mapping = {
        "loops-skill.md": ("loop", "loops", "ループ", "自己改善", "capability", "canary", "promotion"),
        "git-permissions.md": ("git", "commit", "push", "stage", "archive", "保存", "同期"),
        "voicevox-hooks.md": ("voicevox", "通知", "hook", "hooks", "async", "音声"),
    }
    matched: list[Path] = []
    for filename, keys in mapping.items():
        if any(k in low for k in keys):
            path = domain_dir / filename
            if path.exists():
                matched.append(path)
    return matched


def connect_memory_db() -> sqlite3.Connection:
    con = sqlite3.connect(global_path("sqlite"))
    con.row_factory = sqlite3.Row
    con.execute("""
        create table if not exists global_runs (
            id text primary key,
            ts text,
            run_id text,
            project_key text,
            project_root text,
            spec_path text,
            goal text,
            status text,
            failure_signature text,
            sig_hash text,
            strategy text,
            topology text,
            gate_verdict text,
            judge_verdict text,
            cost_tokens integer,
            session text
        )
    """)
    con.execute("""
        create table if not exists memory_docs (
            id text primary key,
            kind text,
            path text,
            title text,
            body text,
            tags text,
            updated_at text
        )
    """)
    try:
        con.execute("create virtual table if not exists memory_docs_fts using fts5(id unindexed, title, body, tags)")
        con.execute("create virtual table if not exists global_runs_fts using fts5(id unindexed, goal, failure_signature, strategy, topology)")
    except sqlite3.Error:
        pass
    return con


def connect_registry_db() -> sqlite3.Connection:
    con = sqlite3.connect(global_path("registry"))
    con.row_factory = sqlite3.Row
    con.execute("""
        create table if not exists loop_profiles (
            profile_id text primary key,
            project_key text,
            project_root text,
            git_remote text,
            run_id text,
            goal text,
            checks_json text,
            risk integer,
            max_iter integer,
            parallelism integer,
            cost_ceiling_tokens integer,
            state_dir text,
            canaries text,
            read_only_paths_json text,
            tags_json text,
            source text,
            created_at text,
            updated_at text
        )
    """)
    con.execute("create index if not exists idx_loop_profiles_project_key on loop_profiles(project_key)")
    con.execute("create index if not exists idx_loop_profiles_git_remote on loop_profiles(git_remote)")
    con.execute("create index if not exists idx_loop_profiles_goal on loop_profiles(goal)")
    return con


def row_to_profile(row: sqlite3.Row | dict[str, Any]) -> dict[str, Any]:
    data = dict(row)
    for key, default in (("checks_json", []), ("read_only_paths_json", []), ("tags_json", [])):
        raw = data.pop(key, "")
        try:
            data[key.replace("_json", "")] = json.loads(raw) if raw else default
        except json.JSONDecodeError:
            data[key.replace("_json", "")] = default
    return data


def profile_to_spec(profile: dict[str, Any]) -> dict[str, Any]:
    spec = {
        "goal": profile.get("goal") or "",
        "run_id": profile.get("run_id") or profile.get("profile_id") or "registry-loop",
        "risk": int(profile.get("risk") or 4),
        "max_iter": int(profile.get("max_iter") or 3),
        "parallelism": int(profile.get("parallelism") or 3),
        "cost_ceiling_tokens": int(profile.get("cost_ceiling_tokens") or 12000),
        "state_dir": profile.get("state_dir") or ".loop-state",
        "project_root": profile.get("project_root") or str(Path.cwd()),
        "canaries": profile.get("canaries") or str(PROJECT_ROOT / "canaries"),
        "read_only_paths": profile.get("read_only_paths") or [],
        "checks": profile.get("checks") or [],
        "_spec_path": f"registry://{profile.get('profile_id')}",
        "_registry_profile_id": profile.get("profile_id"),
    }
    return spec


def registry_attach(spec: dict[str, Any], project_root: str | Path | None = None, profile_id: str | None = None, tags: list[str] | None = None) -> dict[str, Any]:
    identity = project_identity(project_root or spec.get("project_root") or Path.cwd())
    profile_id = profile_id or str(spec.get("run_id") or "") or stable_hash(identity["project_key"] + str(spec.get("goal") or ""))
    now = utc_now()
    row = {
        "profile_id": profile_id,
        "project_key": identity["project_key"],
        "project_root": identity["project_root"],
        "git_remote": identity["git_remote"],
        "run_id": str(spec.get("run_id") or profile_id),
        "goal": str(spec.get("goal") or ""),
        "checks_json": json.dumps(spec.get("checks") or [], ensure_ascii=False, sort_keys=True),
        "risk": int(spec.get("risk") or 4),
        "max_iter": int(spec.get("max_iter") or 3),
        "parallelism": int(spec.get("parallelism") or 3),
        "cost_ceiling_tokens": int(spec.get("cost_ceiling_tokens") or 12000),
        "state_dir": str(spec.get("state_dir") or ".loop-state"),
        "canaries": str(spec.get("canaries") or PROJECT_ROOT / "canaries"),
        "read_only_paths_json": json.dumps(spec.get("read_only_paths") or [], ensure_ascii=False, sort_keys=True),
        "tags_json": json.dumps(tags or spec.get("tags") or [], ensure_ascii=False, sort_keys=True),
        "source": str(spec.get("_spec_path") or "manual"),
    }
    con = connect_registry_db()
    with con:
        existing = con.execute("select created_at from loop_profiles where profile_id=?", (profile_id,)).fetchone()
        con.execute("""
            insert or replace into loop_profiles
            (profile_id, project_key, project_root, git_remote, run_id, goal, checks_json,
             risk, max_iter, parallelism, cost_ceiling_tokens, state_dir, canaries,
             read_only_paths_json, tags_json, source, created_at, updated_at)
            values (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            row["profile_id"], row["project_key"], row["project_root"], row["git_remote"],
            row["run_id"], row["goal"], row["checks_json"], row["risk"], row["max_iter"],
            row["parallelism"], row["cost_ceiling_tokens"], row["state_dir"], row["canaries"],
            row["read_only_paths_json"], row["tags_json"], row["source"],
            existing["created_at"] if existing else now, now,
        ))
    con.close()
    result = {"ts": now, "verdict": "attached", "registry": str(global_path("registry")), "profile": row_to_profile(row)}
    write_json(global_state_dir() / "registry_attach_report.json", result)
    return result


def registry_discover(project_root: str | Path | None = None, query: str = "", limit: int = 5) -> dict[str, Any]:
    identity = project_identity(project_root or Path.cwd())
    con = connect_registry_db()
    exact = con.execute("select * from loop_profiles where project_key=? order by updated_at desc limit 1", (identity["project_key"],)).fetchone()
    candidates: list[dict[str, Any]] = []
    if identity["git_remote"]:
        rows = con.execute("select * from loop_profiles where git_remote=? order by updated_at desc limit ?", (identity["git_remote"], limit)).fetchall()
        candidates.extend(row_to_profile(r) for r in rows)
    if query:
        like = f"%{query.lower()}%"
        rows = con.execute("""
            select * from loop_profiles
            where lower(goal) like ? or lower(run_id) like ? or lower(tags_json) like ?
            order by updated_at desc
            limit ?
        """, (like, like, like, limit)).fetchall()
        candidates.extend(row_to_profile(r) for r in rows)
    rows = con.execute("select * from loop_profiles order by updated_at desc limit ?", (limit,)).fetchall()
    candidates.extend(row_to_profile(r) for r in rows)
    con.close()
    deduped = dedupe_rows(candidates, ("profile_id",))
    result = {
        "ts": utc_now(),
        "registry": str(global_path("registry")),
        "identity": identity,
        "exact": row_to_profile(exact) if exact else None,
        "candidates": deduped[:limit],
        "memory": memory_search(query or identity["project_root"], limit=limit) if query else None,
    }
    write_json(global_state_dir() / "registry_discover_report.json", result)
    return result


def registry_spec(project_root: str | Path | None = None, profile_id: str | None = None) -> dict[str, Any] | None:
    identity = project_identity(project_root or Path.cwd())
    con = connect_registry_db()
    if profile_id:
        row = con.execute("select * from loop_profiles where profile_id=?", (profile_id,)).fetchone()
    else:
        row = con.execute("select * from loop_profiles where project_key=? order by updated_at desc limit 1", (identity["project_key"],)).fetchone()
    con.close()
    return profile_to_spec(row_to_profile(row)) if row else None


def has_fts(con: sqlite3.Connection, table: str) -> bool:
    row = con.execute("select name from sqlite_master where type='table' and name=?", (table,)).fetchone()
    return row is not None


def sqlite_run_id(row: dict[str, Any]) -> str:
    raw = "|".join(str(row.get(k, "")) for k in ("ts", "run_id", "project_key", "iter", "failure_signature"))
    return stable_hash(raw)


def index_global_run(row: dict[str, Any]) -> None:
    con = connect_memory_db()
    row_id = sqlite_run_id(row)
    with con:
        con.execute("""
            insert or replace into global_runs
            (id, ts, run_id, project_key, project_root, spec_path, goal, status,
             failure_signature, sig_hash, strategy, topology, gate_verdict,
             judge_verdict, cost_tokens, session)
            values (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            row_id, row.get("ts"), row.get("run_id"), row.get("project_key"),
            row.get("project_root"), row.get("spec_path"), row.get("goal"),
            row.get("status"), row.get("failure_signature"), row.get("sig_hash"),
            row.get("strategy"), row.get("topology"), row.get("gate_verdict"),
            row.get("judge_verdict"), int(row.get("cost_tokens") or 0),
            row.get("session"),
        ))
        if has_fts(con, "global_runs_fts"):
            con.execute("delete from global_runs_fts where id=?", (row_id,))
            con.execute(
                "insert into global_runs_fts (id, goal, failure_signature, strategy, topology) values (?, ?, ?, ?, ?)",
                (row_id, row.get("goal") or "", row.get("failure_signature") or "", row.get("strategy") or "", row.get("topology") or ""),
            )
    con.close()


def upsert_memory_doc(con: sqlite3.Connection, doc_id: str, kind: str, path: str, title: str, body: str, tags: str) -> None:
    con.execute("""
        insert or replace into memory_docs (id, kind, path, title, body, tags, updated_at)
        values (?, ?, ?, ?, ?, ?, ?)
    """, (doc_id, kind, path, title, body[:8000], tags, utc_now()))
    if has_fts(con, "memory_docs_fts"):
        con.execute("delete from memory_docs_fts where id=?", (doc_id,))
        con.execute("insert into memory_docs_fts (id, title, body, tags) values (?, ?, ?, ?)", (doc_id, title, body[:8000], tags))


def index_memory(lessons_path: Path | None = None) -> dict[str, Any]:
    path = lessons_path or DEFAULT_LESSONS
    con = connect_memory_db()
    docs = 0
    runs = 0
    with con:
        for row in read_jsonl(global_path("runs")):
            index_global_run(row)
            runs += 1
        text = path.read_text(encoding="utf-8") if path.exists() else ""
        always, bounded = extract_always_apply(text)
        upsert_memory_doc(con, "lessons:always-apply", "always_apply", str(path), "Always-Apply Memory", always, "always apply bounded codex")
        docs += 1
        domain_dir = path.parent / "domain-lessons"
        if domain_dir.exists():
            for doc_path in sorted(domain_dir.glob("*.md")):
                body = doc_path.read_text(encoding="utf-8")
                upsert_memory_doc(con, "domain:" + doc_path.name, "domain", str(doc_path), doc_path.stem, body, doc_path.stem.replace("-", " "))
                docs += 1
        for row in read_jsonl(global_path("capabilities")):
            body = json.dumps(row, ensure_ascii=False, sort_keys=True)
            upsert_memory_doc(con, "capability:" + str(row.get("candidate_id") or stable_hash(body)), "capability", str(global_path("capabilities")), str(row.get("failure_signature") or "capability"), body, "capability repeated failure")
            docs += 1
        reg = connect_registry_db()
        try:
            for row in reg.execute("select * from loop_profiles order by updated_at desc").fetchall():
                profile = row_to_profile(row)
                body = json.dumps(profile, ensure_ascii=False, sort_keys=True)
                tags = " ".join(str(x) for x in profile.get("tags") or [])
                upsert_memory_doc(con, "registry:" + str(profile.get("profile_id")), "registry_profile", str(global_path("registry")), str(profile.get("profile_id") or "registry profile"), body, tags)
                docs += 1
        finally:
            reg.close()
        for i, row in enumerate(read_jsonl(global_path("memory_sync"))):
            body = json.dumps(row, ensure_ascii=False, sort_keys=True)
            upsert_memory_doc(con, "sync:" + stable_hash(body + str(i)), "sync_candidate", str(global_path("memory_sync")), str(row.get("suggested_target") or "sync candidate"), body, "sync candidate review")
            docs += 1
    con.close()
    result = {"ts": utc_now(), "sqlite": str(global_path("sqlite")), "indexed_docs": docs, "indexed_runs": runs, "bounded_markers": bounded}
    write_json(global_state_dir() / "memory_index_report.json", result)
    return result


def fts_query(text: str) -> str:
    words = re.findall(r"[\w\-]+", text.lower())
    return " OR ".join(words[:8]) or text[:80]


def search_terms(text: str) -> list[str]:
    raw = text.strip().lower()
    terms = [raw] if raw else []
    terms.extend(re.findall(r"[\w\-ぁ-んァ-ン一-龥]+", raw))
    alias_terms = {
        "ループ": ("loop", "loops", "loop-run", "loop-memory-search"),
        "自己改善": ("loop", "capability", "hypothesis", "promotion"),
        "スキル": ("skill", "skills", "SKILL.md".lower()),
        "記憶": ("memory", "lessons", "domain-lessons"),
        "メモリ": ("memory", "lessons", "domain-lessons"),
        "検索": ("search", "memory-search", "fts"),
        "通知": ("voicevox", "hook", "hooks"),
    }
    for key, aliases in alias_terms.items():
        if key in raw:
            terms.extend(aliases)
    out: list[str] = []
    seen: set[str] = set()
    for term in terms:
        term = term.strip()
        if len(term) < 2 or term in seen:
            continue
        seen.add(term)
        out.append(term)
    return out[:10]


def like_clauses(columns: list[str], terms: list[str]) -> tuple[str, list[str]]:
    clauses: list[str] = []
    params: list[str] = []
    for term in terms:
        term_clause = []
        for column in columns:
            term_clause.append(f"lower({column}) like ?")
            params.append(f"%{term}%")
        clauses.append("(" + " or ".join(term_clause) + ")")
    return " or ".join(clauses), params


def dedupe_rows(rows: list[dict[str, Any]], keys: tuple[str, ...]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    seen: set[tuple[str, ...]] = set()
    for row in rows:
        key = tuple(str(row.get(k) or "") for k in keys)
        if key in seen:
            continue
        seen.add(key)
        out.append(row)
    return out


def rank_rows(rows: list[dict[str, Any]], terms: list[str], weights: dict[str, int]) -> list[dict[str, Any]]:
    def score(row: dict[str, Any]) -> int:
        total = 0
        for key, weight in weights.items():
            value = str(row.get(key) or "").lower()
            total += sum(weight for term in terms if term in value)
        return total

    return sorted(rows, key=score, reverse=True)


def memory_search(query: str, limit: int = 8) -> dict[str, Any]:
    index_memory()
    con = connect_memory_db()
    q = fts_query(query)
    docs: list[dict[str, Any]] = []
    runs: list[dict[str, Any]] = []
    if has_fts(con, "memory_docs_fts"):
        try:
            rows = con.execute("""
                select d.kind, d.path, d.title, snippet(memory_docs_fts, 2, '[', ']', '...', 16) as snippet
                from memory_docs_fts f join memory_docs d on d.id = f.id
                where memory_docs_fts match ?
                limit ?
            """, (q, limit)).fetchall()
            docs.extend(dict(r) for r in rows)
        except sqlite3.Error:
            pass
    terms = search_terms(query)
    if terms and len(docs) < limit:
        try:
            where, params = like_clauses(["title", "body", "tags", "path"], terms)
            rows = con.execute(f"""
                select kind, path, title, substr(body, 1, 320) as snippet
                from memory_docs
                where {where}
                limit ?
            """, (*params, limit)).fetchall()
            docs.extend(dict(r) for r in rows)
        except sqlite3.Error:
            pass
    else:
        docs = docs[:limit]
    docs = rank_rows(dedupe_rows(docs, ("kind", "path", "title")), terms, {"title": 5, "path": 4, "snippet": 1})[:limit]
    if has_fts(con, "global_runs_fts"):
        try:
            rows = con.execute("""
                select r.ts, r.run_id, r.project_root, r.status, r.failure_signature, r.strategy, r.session
                from global_runs_fts f join global_runs r on r.id = f.id
                where global_runs_fts match ?
                limit ?
            """, (q, limit)).fetchall()
            runs.extend(dict(r) for r in rows)
        except sqlite3.Error:
            pass
    if terms and len(runs) < limit:
        try:
            where, params = like_clauses(["goal", "failure_signature", "strategy", "topology", "project_root"], terms)
            rows = con.execute(f"""
                select ts, run_id, project_root, status, failure_signature, strategy, session
                from global_runs
                where {where}
                limit ?
            """, (*params, limit)).fetchall()
            runs.extend(dict(r) for r in rows)
        except sqlite3.Error:
            pass
    else:
        runs = runs[:limit]
    runs = rank_rows(dedupe_rows(runs, ("ts", "run_id", "project_root", "failure_signature")), terms, {"failure_signature": 5, "strategy": 3, "project_root": 1})[:limit]
    con.close()
    result = {"ts": utc_now(), "query": query, "sqlite": str(global_path("sqlite")), "docs": docs, "runs": runs}
    write_json(global_state_dir() / "memory_search_report.json", result)
    return result


def memory_check(cap_chars: int = 3000, lessons_path: Path | None = None, stale_days: int = 45) -> dict[str, Any]:
    path = lessons_path or DEFAULT_LESSONS
    text = path.read_text(encoding="utf-8") if path.exists() else ""
    always, bounded = extract_always_apply(text)
    domain_dir = path.parent / "domain-lessons"
    domain_files = sorted(str(p) for p in domain_dir.glob("*.md")) if domain_dir.exists() else []
    chars = len(always)
    findings: list[str] = []
    if not path.exists():
        findings.append("lessons file missing")
    if not bounded:
        findings.append("always-apply markers missing; full lessons file would be injected")
    if chars > cap_chars:
        findings.append(f"always-apply memory exceeds cap: {chars}>{cap_chars}")
    if not domain_dir.exists():
        findings.append("domain-lessons directory missing")
    candidates = retire_candidates(text, stale_days=stale_days)
    result = {
        "ts": utc_now(),
        "verdict": "block" if chars > cap_chars or not bounded else ("warn" if findings else "pass"),
        "lessons_path": str(path),
        "always_apply_chars": chars,
        "cap_chars": cap_chars,
        "stale_days": stale_days,
        "bounded_markers": bounded,
        "domain_dir": str(domain_dir),
        "domain_files": domain_files,
        "retire_candidates": candidates,
        "findings": findings,
    }
    write_json(global_path("memory_check"), result)
    write_json(global_path("memory_retire"), {"ts": utc_now(), "candidates": candidates})
    return result


def memory_prefetch(prompt: str, cap_chars: int = 3000, lessons_path: Path | None = None) -> dict[str, Any]:
    path = lessons_path or DEFAULT_LESSONS
    text = path.read_text(encoding="utf-8") if path.exists() else ""
    always, bounded = extract_always_apply(text)
    domain_dir = path.parent / "domain-lessons"
    domains = []
    for p in domain_matches(prompt, domain_dir):
        body = p.read_text(encoding="utf-8")
        domains.append({"path": str(p), "chars": len(body), "content": body})
    search = memory_search(prompt, limit=5) if prompt else {"docs": [], "runs": []}
    result = {
        "ts": utc_now(),
        "mode": "prefetch",
        "verdict": "pass" if bounded and len(always) <= cap_chars else "block",
        "always_apply": always,
        "always_apply_chars": len(always),
        "cap_chars": cap_chars,
        "domain_matches": domains,
        "search_hits": {
            "docs": search.get("docs", []),
            "runs": search.get("runs", []),
        },
        "notes": [
            "SessionStart should inject Always-Apply only.",
            "UserPromptSubmit should inject matched domain files only.",
        ],
    }
    write_json(global_state_dir() / "memory_prefetch_plan.json", result)
    return result


def memory_sync(capture: str = "", prompt: str = "", cap_chars: int = 3000, lessons_path: Path | None = None) -> dict[str, Any]:
    check = memory_check(cap_chars=cap_chars, lessons_path=lessons_path)
    candidate = {
        "ts": utc_now(),
        "prompt_hash": stable_hash(prompt) if prompt else "",
        "capture": capture[:1200],
        "suggested_target": infer_domain(prompt, capture),
        "requires_review": bool(capture),
    }
    if capture:
        append_jsonl(global_path("memory_sync"), candidate)
    result = {
        "ts": utc_now(),
        "mode": "sync",
        "bounded_check": check,
        "candidate_captured": bool(capture),
        "candidate": candidate if capture else None,
        "notes": [
            "Stop/SessionEnd should capture candidates, not auto-inject them.",
            "Promotion to Always-Apply requires bounded check and human review.",
        ],
    }
    write_json(global_state_dir() / "memory_sync_report.json", result)
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description="Persistent state helpers for Loop Kernel.")
    sub = parser.add_subparsers(dest="cmd", required=True)
    init = sub.add_parser("init")
    init.add_argument("--spec")
    mem = sub.add_parser("memory-check")
    mem.add_argument("--cap-chars", type=int, default=3000)
    mem.add_argument("--lessons", type=Path)
    mem.add_argument("--stale-days", type=int, default=45)
    mem.add_argument("--json", action="store_true")
    idx = sub.add_parser("memory-index")
    idx.add_argument("--lessons", type=Path)
    idx.add_argument("--json", action="store_true")
    srch = sub.add_parser("memory-search")
    srch.add_argument("--query", required=True)
    srch.add_argument("--limit", type=int, default=8)
    srch.add_argument("--json", action="store_true")
    pre = sub.add_parser("memory-prefetch")
    pre.add_argument("--prompt", default="")
    pre.add_argument("--cap-chars", type=int, default=3000)
    pre.add_argument("--lessons", type=Path)
    pre.add_argument("--json", action="store_true")
    sync = sub.add_parser("memory-sync")
    sync.add_argument("--prompt", default="")
    sync.add_argument("--capture", default="")
    sync.add_argument("--cap-chars", type=int, default=3000)
    sync.add_argument("--lessons", type=Path)
    sync.add_argument("--json", action="store_true")
    reg_discover = sub.add_parser("registry-discover")
    reg_discover.add_argument("--project-root", type=Path)
    reg_discover.add_argument("--query", default="")
    reg_discover.add_argument("--limit", type=int, default=5)
    reg_discover.add_argument("--json", action="store_true")
    reg_attach = sub.add_parser("registry-attach")
    reg_attach.add_argument("--spec", required=True)
    reg_attach.add_argument("--project-root", type=Path)
    reg_attach.add_argument("--profile-id")
    reg_attach.add_argument("--tag", action="append", default=[])
    reg_attach.add_argument("--json", action="store_true")
    reg_get = sub.add_parser("registry-spec")
    reg_get.add_argument("--project-root", type=Path)
    reg_get.add_argument("--profile-id")
    reg_get.add_argument("--json", action="store_true")
    rec = sub.add_parser("record")
    rec.add_argument("--spec")
    rec.add_argument("--run-id", required=True)
    rec.add_argument("--iter", type=int, default=1)
    rec.add_argument("--status", choices=["pass", "fail"], required=True)
    rec.add_argument("--signature", default="")
    rec.add_argument("--cost-tokens", type=int, default=0)
    args = parser.parse_args()
    if args.cmd == "memory-check":
        print(json.dumps(memory_check(cap_chars=args.cap_chars, lessons_path=args.lessons, stale_days=args.stale_days), ensure_ascii=False, indent=2, sort_keys=True))
        return 0
    if args.cmd == "memory-prefetch":
        print(json.dumps(memory_prefetch(prompt=args.prompt, cap_chars=args.cap_chars, lessons_path=args.lessons), ensure_ascii=False, indent=2, sort_keys=True))
        return 0
    if args.cmd == "memory-sync":
        print(json.dumps(memory_sync(prompt=args.prompt, capture=args.capture, cap_chars=args.cap_chars, lessons_path=args.lessons), ensure_ascii=False, indent=2, sort_keys=True))
        return 0
    if args.cmd == "memory-index":
        print(json.dumps(index_memory(lessons_path=args.lessons), ensure_ascii=False, indent=2, sort_keys=True))
        return 0
    if args.cmd == "memory-search":
        print(json.dumps(memory_search(query=args.query, limit=args.limit), ensure_ascii=False, indent=2, sort_keys=True))
        return 0
    if args.cmd == "registry-discover":
        print(json.dumps(registry_discover(project_root=args.project_root, query=args.query, limit=args.limit), ensure_ascii=False, indent=2, sort_keys=True))
        return 0
    if args.cmd == "registry-attach":
        print(json.dumps(registry_attach(load_spec(args.spec), project_root=args.project_root, profile_id=args.profile_id, tags=args.tag), ensure_ascii=False, indent=2, sort_keys=True))
        return 0
    if args.cmd == "registry-spec":
        spec = registry_spec(project_root=args.project_root, profile_id=args.profile_id)
        print(json.dumps({"ts": utc_now(), "verdict": "found" if spec else "missing", "spec": spec}, ensure_ascii=False, indent=2, sort_keys=True))
        return 0 if spec else 2
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
