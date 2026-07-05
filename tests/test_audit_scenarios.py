"""Escenarios de regresión para `arc-one-manifest audit`."""

from __future__ import annotations

import unittest
from dataclasses import dataclass, field
from pathlib import Path

import yaml

from arc_one_manifest.intelligence.audit import run_audit

FIXTURES_ROOT = Path(__file__).resolve().parent / "fixtures" / "audit_scenarios"


@dataclass
class ExpectedFinding:
    manifest_section: str
    suggested_catalog_id: str


@dataclass
class ScenarioExpectation:
    name: str
    clean: bool
    must_find: list[ExpectedFinding] = field(default_factory=list)
    must_not_find: list[ExpectedFinding] = field(default_factory=list)
    max_findings: int | None = None


def _load_expected(scenario_dir: Path) -> ScenarioExpectation:
    raw = yaml.safe_load((scenario_dir / "expected.yaml").read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        raise ValueError(f"{scenario_dir}: expected.yaml must be a mapping")

    def _parse_findings(key: str) -> list[ExpectedFinding]:
        rows = raw.get(key) or []
        out: list[ExpectedFinding] = []
        for row in rows:
            out.append(
                ExpectedFinding(
                    manifest_section=str(row["manifestSection"]),
                    suggested_catalog_id=str(row["suggestedCatalogId"]),
                )
            )
        return out

    return ScenarioExpectation(
        name=scenario_dir.name,
        clean=bool(raw.get("clean", False)),
        must_find=_parse_findings("mustFind"),
        must_not_find=_parse_findings("mustNotFind"),
        max_findings=raw.get("maxFindings"),
    )


def _finding_key(manifest_section: str, suggested_id: str) -> tuple[str, str]:
    return (manifest_section, suggested_id.lower())


class AuditScenarioHarnessTest(unittest.TestCase):
    """Cada subcarpeta en fixtures/audit_scenarios es un mini-repo agente."""

    @classmethod
    def setUpClass(cls) -> None:
        if not FIXTURES_ROOT.is_dir():
            cls.scenarios: list[Path] = []
            return
        cls.scenarios = sorted(
            p for p in FIXTURES_ROOT.iterdir() if p.is_dir() and (p / "expected.yaml").is_file()
        )

    def test_all_scenarios(self) -> None:
        if not self.scenarios:
            self.skipTest("No audit scenarios under tests/fixtures/audit_scenarios")

        failures: list[str] = []
        for scenario_dir in self.scenarios:
            try:
                self._run_scenario(scenario_dir)
            except AssertionError as exc:
                failures.append(f"{scenario_dir.name}: {exc}")

        if failures:
            self.fail("\n".join(failures))

    def _run_scenario(self, scenario_dir: Path) -> None:
        expected = _load_expected(scenario_dir)
        manifest = scenario_dir / "arc-one.agent.yaml"
        self.assertTrue(manifest.is_file(), f"{expected.name}: missing arc-one.agent.yaml")

        report = run_audit(
            manifest,
            repo=scenario_dir,
            scan_all=True,
            static_only=True,
            min_confidence=0.85,
        )

        if expected.clean:
            self.assertTrue(
                report.clean,
                f"{expected.name}: expected clean but got findings: "
                f"{[(f.manifest_section, f.suggested_catalog_id) for f in report.findings]}",
            )
        else:
            self.assertFalse(report.clean, f"{expected.name}: expected findings but report is clean")

        if expected.max_findings is not None:
            self.assertLessEqual(
                len(report.findings),
                expected.max_findings,
                f"{expected.name}: too many findings ({len(report.findings)} > {expected.max_findings})",
            )

        actual = {
            _finding_key(f.manifest_section, f.suggested_catalog_id) for f in report.findings
        }

        for want in expected.must_find:
            key = _finding_key(want.manifest_section, want.suggested_catalog_id)
            self.assertIn(
                key,
                actual,
                f"{expected.name}: missing finding {want.manifest_section}/{want.suggested_catalog_id}. "
                f"Actual: {sorted(actual)}",
            )

        for forbid in expected.must_not_find:
            key = _finding_key(forbid.manifest_section, forbid.suggested_catalog_id)
            self.assertNotIn(
                key,
                actual,
                f"{expected.name}: false positive {forbid.manifest_section}/{forbid.suggested_catalog_id}",
            )


class AuditLabRegressionTest(unittest.TestCase):
    """Smoke contra arc-one-demo-audit-lab (repo de pruebas — no tocar nova-aws)."""

    LAB_ROOT = Path(__file__).resolve().parents[2] / "arc-one-demo-audit-lab"

    def test_audit_lab_baseline_is_clean(self) -> None:
        manifest = self.LAB_ROOT / "arc-one.agent.yaml"
        if not manifest.is_file():
            self.skipTest("arc-one-demo-audit-lab not found beside manifest-tools")

        report = run_audit(manifest, repo=self.LAB_ROOT, scan_all=True, static_only=True, min_confidence=0.85)
        self.assertTrue(
            report.clean,
            f"audit-lab false positives: "
            f"{[(f.manifest_section, f.suggested_catalog_id, f.evidence[0].file if f.evidence else '') for f in report.findings]}",
        )


if __name__ == "__main__":
    unittest.main()
