from pathlib import Path
import contextlib
import io
import tempfile
import unittest

from oss_maintainer_toolkit.checks import build_report
from oss_maintainer_toolkit.cli import main


class ReportTests(unittest.TestCase):
    def test_detects_complete_public_project(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            for name in ["README.md", "LICENSE", "SECURITY.md", "CONTRIBUTING.md", "CHANGELOG.md"]:
                (root / name).write_text("public\n", encoding="utf-8")
            for name in [
                "pyproject.toml",
                "src/oss_maintainer_toolkit/cli.py",
                "tests/test_checks.py",
                ".github/workflows/ci.yml",
                "docs/roadmap.md",
                "docs/use-cases.md",
            ]:
                path = root / name
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text("public\n", encoding="utf-8")

            report = build_report(root)

        self.assertEqual(report.status, "pass")
        self.assertEqual(report.findings, [])
        self.assertEqual(report.missing_required_files, [])
        self.assertEqual(report.missing_project_signals, [])

    def test_detects_private_markers(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "README.md").write_text("private path /Users/example/.codex\n", encoding="utf-8")
            report = build_report(root)

        labels = {(finding.check, finding.label) for finding in report.findings}
        self.assertIn(("private-marker", "local_path"), labels)
        self.assertIn(("private-marker", "codex_private_state"), labels)
        self.assertEqual(report.status, "review")

    def test_cli_returns_success_for_markdown_output(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "README.md").write_text("public\n", encoding="utf-8")
            with contextlib.redirect_stdout(io.StringIO()):
                exit_code = main([str(root), "--format", "markdown"])

        self.assertEqual(exit_code, 0)


if __name__ == "__main__":
    unittest.main()
