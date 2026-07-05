#!/usr/bin/env python3
"""Corre todos los escenarios de audit y muestra tabla legible (desarrollo / QA manual)."""

from __future__ import annotations

import sys
from pathlib import Path

# Permite ejecutar sin pip install: python scripts/run_audit_scenarios.py
ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tests.test_audit_scenarios import FIXTURES_ROOT, _load_expected  # noqa: E402
from arc_one_manifest.intelligence.audit import run_audit  # noqa: E402


def main() -> int:
    scenarios = sorted(
        p for p in FIXTURES_ROOT.iterdir() if p.is_dir() and (p / "expected.yaml").is_file()
    )
    if not scenarios:
        print("No scenarios found.", file=sys.stderr)
        return 2

    failed = 0
    print(f"{'SCENARIO':<28} {'OK':<4} {'FINDINGS':<8} DETAIL")
    print("-" * 72)

    for scenario_dir in scenarios:
        exp = _load_expected(scenario_dir)
        report = run_audit(
            scenario_dir / "arc-one.agent.yaml",
            repo=scenario_dir,
            scan_all=True,
            min_confidence=0.85,
        )
        ok = report.clean == exp.clean
        for want in exp.must_find:
            keys = {(f.manifest_section, f.suggested_catalog_id) for f in report.findings}
            if (want.manifest_section, want.suggested_catalog_id) not in keys:
                ok = False
        for forbid in exp.must_not_find:
            keys = {(f.manifest_section, f.suggested_catalog_id) for f in report.findings}
            if (forbid.manifest_section, forbid.suggested_catalog_id) in keys:
                ok = False

        if not ok:
            failed += 1

        detail = ", ".join(
            f"{f.manifest_section}:{f.suggested_catalog_id}" for f in report.findings
        ) or "—"
        print(f"{exp.name:<28} {'yes' if ok else 'NO':<4} {len(report.findings):<8} {detail}")

    print("-" * 72)
    print(f"{len(scenarios) - failed}/{len(scenarios)} scenarios passed")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
