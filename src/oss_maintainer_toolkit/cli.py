"""Command line interface for maintainer readiness reports."""

from __future__ import annotations

import argparse
from pathlib import Path
import sys

from .checks import build_report


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="oss-maintainer-toolkit",
        description="Check a public OSS repository for maintainer readiness and privacy risks.",
    )
    parser.add_argument("path", nargs="?", default=".", help="Repository path to inspect.")
    parser.add_argument(
        "--format",
        choices=["markdown", "json"],
        default="markdown",
        help="Output format.",
    )
    parser.add_argument(
        "--fail-on-review",
        action="store_true",
        help="Exit with status 1 when the report status is review.",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(sys.argv[1:] if argv is None else argv)
    report = build_report(Path(args.path))
    output = report.to_json() if args.format == "json" else report.to_markdown()
    sys.stdout.write(output)
    if args.fail_on_review and report.status != "pass":
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
