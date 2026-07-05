"""Tests manifest bootstrap — generate."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from arc_one_manifest.intelligence.generate import run_generate
from arc_one_manifest.intelligence.profiles import detect_profile


class GenerateTest(unittest.TestCase):
    def test_detect_profile_generic(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "src").mkdir()
            (root / "src" / "app.py").write_text("print('hi')\n", encoding="utf-8")
            self.assertEqual(detect_profile(root), "generic")

    def test_generate_from_banking_like_repo(self) -> None:
        fixtures = Path(__file__).parent / "fixtures" / "audit_scenarios" / "clean-banking"
        manifest, report = run_generate(fixtures, profile="generic")
        ids = {row["asset_id"] for row in manifest.get("data_stores") or []}
        self.assertIn("postgresql", ids)
        self.assertIn("pinecone", ids)
        self.assertEqual(report.profile, "generic")
        self.assertFalse(report.validation.get("ok"))

    def test_generate_dry_run_has_todo_fields(self) -> None:
        fixtures = Path(__file__).parent / "fixtures" / "audit_scenarios" / "clean-banking"
        manifest, _report = run_generate(fixtures)
        self.assertIn("TODO", manifest["purpose"])
        self.assertEqual(manifest["technical_owner"], "TODO")


if __name__ == "__main__":
    unittest.main()
