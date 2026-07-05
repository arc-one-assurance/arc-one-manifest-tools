#!/usr/bin/env python3
"""Smoke E2E — platform audit + generate (requiere env vars)."""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from arc_one_manifest.intelligence.audit import run_audit  # noqa: E402
from arc_one_manifest.intelligence.generate import run_generate  # noqa: E402


def _platform_audit_direct() -> None:
    base = os.environ.get("ARC_ONE_API_BASE_URL", "").strip().rstrip("/")
    token = os.environ.get("ARC_ONE_BEARER_TOKEN", "").strip()
    if not base or not token:
        print("SKIP platform direct (no ARC_ONE_API_BASE_URL / ARC_ONE_BEARER_TOKEN)")
        return
    body = {
        "manifestPath": "arc-one.agent.yaml",
        "manifestSummary": {"dataStores": ["postgresql"], "mcpServers": []},
        "codeSignals": [
            {
                "kind": "data_store",
                "inferred_id": "dynamodb",
                "confidence": 0.92,
                "manifest_section": "data_stores",
                "evidence": {"file": "src/db.py", "line": 8, "snippet": "boto3.client('dynamodb')"},
            }
        ],
    }
    url = f"{base}/api/manifest/intelligence/audit"
    resp = httpx.post(url, headers={"Authorization": f"Bearer {token}"}, json=body, timeout=60)
    print(f"POST {url} -> {resp.status_code}")
    resp.raise_for_status()
    data = resp.json()
    print(json.dumps({k: data[k] for k in ("clean", "staticOnly", "judgeModel") if k in data}, indent=2))
    assert data.get("clean") is False, "expected drift finding"
    print("OK platform audit endpoint")


def main() -> int:
    lab = ROOT.parent / "arc-one-demo-audit-lab"
    if not lab.is_dir():
        print(f"WARN: {lab} not found, skipping CLI smoke")
    else:
        report = run_audit(lab / "arc-one.agent.yaml", repo=lab, scan_all=True, static_only=True)
        assert report.clean, f"baseline not clean: {report.findings}"
        print("OK audit-lab baseline (static)")

        manifest, gen_report = run_generate(lab, skip_llm=True)
        assert manifest.get("data_stores"), "generate missing data_stores"
        print(f"OK generate skip-llm profile={gen_report.profile} confidence={gen_report.confidence:.0%}")

    _platform_audit_direct()
    print("All smoke checks passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
