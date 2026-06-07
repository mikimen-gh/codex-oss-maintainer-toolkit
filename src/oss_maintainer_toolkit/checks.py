"""Repository checks for public maintainer workflows."""

from __future__ import annotations

from dataclasses import dataclass, asdict
from pathlib import Path
import json
import re
from typing import Iterable


SECRET_PATTERNS = {
    "aws_access_key": re.compile(r"AKIA[0-9A-Z]{16}"),
    "private_key": re.compile(r"-----BEGIN (RSA |OPENSSH |EC |DSA )?PRIVATE KEY-----"),
    "github_token": re.compile(r"(ghp|github_pat)_[A-Za-z0-9_]{20,}"),
    "openai_key": re.compile(r"sk-[A-Za-z0-9]{20,}"),
    "slack_token": re.compile(r"xox[baprs]-[A-Za-z0-9-]{10,}"),
    "google_api_key": re.compile(r"AIza[0-9A-Za-z_-]{20,}"),
}

PRIVATE_MARKERS = {
    "local_path": re.compile(r"(/Users/|/home/|/opt/|/var/lib/)"),
    "codex_private_state": re.compile(
        r"(codex-home-backup|state_[0-9]+\.sqlite|logs_[0-9]+\.sqlite|session_index\.jsonl|\.codex)"
    ),
    "ssh_key_name": re.compile(r"id_ed25519|id_rsa"),
}

REQUIRED_PUBLIC_FILES = [
    "README.md",
    "LICENSE",
    "SECURITY.md",
    "CONTRIBUTING.md",
    "CHANGELOG.md",
]

PROJECT_SIGNAL_FILES = [
    "pyproject.toml",
    "src/oss_maintainer_toolkit/cli.py",
    "tests/test_checks.py",
    ".github/workflows/ci.yml",
    "docs/roadmap.md",
    "docs/use-cases.md",
]

SKIP_DIRS = {".git", "__pycache__", ".pytest_cache", ".venv", "venv", "node_modules", "dist", "build"}
SKIP_SUFFIXES = {".pyc", ".sqlite", ".sqlite3", ".db"}
ALLOWLISTED_FIXTURE_FILES = {
    ".gitignore",
    "scripts/verify-public-safety.sh",
    "src/oss_maintainer_toolkit/checks.py",
    "tests/test_checks.py",
}


@dataclass(frozen=True)
class Finding:
    check: str
    path: str
    line: int
    label: str
    excerpt: str


@dataclass(frozen=True)
class Report:
    root: str
    score: int
    status: str
    missing_required_files: list[str]
    missing_project_signals: list[str]
    findings: list[Finding]

    def to_dict(self) -> dict[str, object]:
        data = asdict(self)
        data["findings"] = [asdict(finding) for finding in self.findings]
        return data

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), indent=2, sort_keys=True)

    def to_markdown(self) -> str:
        lines = [
            "# OSS Maintainer Toolkit Report",
            "",
            f"- Root: `{self.root}`",
            f"- Status: `{self.status}`",
            f"- Score: `{self.score}/100`",
            "",
        ]
        if self.missing_required_files:
            lines.append("## Missing Required Files")
            lines.extend(f"- `{item}`" for item in self.missing_required_files)
            lines.append("")
        if self.missing_project_signals:
            lines.append("## Missing Project Signals")
            lines.extend(f"- `{item}`" for item in self.missing_project_signals)
            lines.append("")
        if self.findings:
            lines.append("## Privacy And Secret Findings")
            lines.extend(
                f"- `{finding.path}:{finding.line}` {finding.check}/{finding.label}: `{finding.excerpt}`"
                for finding in self.findings
            )
            lines.append("")
        if not self.missing_required_files and not self.missing_project_signals and not self.findings:
            lines.append("No blocking issues found.")
        return "\n".join(lines).rstrip() + "\n"


def iter_text_files(root: Path) -> Iterable[Path]:
    for path in root.rglob("*"):
        if path.is_dir():
            continue
        if any(part in SKIP_DIRS for part in path.parts):
            continue
        if path.suffix in SKIP_SUFFIXES:
            continue
        yield path


def scan_file(path: Path, root: Path) -> list[Finding]:
    try:
        text = path.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        return []

    findings: list[Finding] = []
    relative = path.relative_to(root).as_posix()
    if relative in ALLOWLISTED_FIXTURE_FILES:
        return findings

    for line_number, line in enumerate(text.splitlines(), start=1):
        for label, pattern in SECRET_PATTERNS.items():
            if pattern.search(line):
                findings.append(Finding("secret", relative, line_number, label, line.strip()[:120]))
        for label, pattern in PRIVATE_MARKERS.items():
            if pattern.search(line):
                findings.append(Finding("private-marker", relative, line_number, label, line.strip()[:120]))
    return findings


def build_report(root: str | Path) -> Report:
    root_path = Path(root).resolve()
    missing_required = [item for item in REQUIRED_PUBLIC_FILES if not (root_path / item).exists()]
    missing_signals = [item for item in PROJECT_SIGNAL_FILES if not (root_path / item).exists()]
    findings: list[Finding] = []

    for path in iter_text_files(root_path):
        findings.extend(scan_file(path, root_path))

    score = 100
    score -= len(missing_required) * 12
    score -= len(missing_signals) * 5
    score -= len(findings) * 20
    score = max(score, 0)

    status = "pass" if score >= 80 and not findings and not missing_required else "review"
    return Report(str(root_path), score, status, missing_required, missing_signals, findings)
