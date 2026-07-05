"""Tests platform judge client."""

from __future__ import annotations

import unittest
from unittest.mock import MagicMock, patch

from arc_one_manifest.intelligence.judge import run_platform_judge
from arc_one_manifest.intelligence.manifest_summary import summarize_manifest
from arc_one_manifest.intelligence.models import CodeSignal, Evidence

MINIMAL = {
    "manifest_version": "1.2",
    "name": "Test",
    "agent_version": "1.0.0",
    "agent_model": "anthropic/claude-sonnet-4-7",
    "data_stores": [{"asset_id": "postgresql", "relation_type": ["READ"]}],
    "integration_endpoints": [],
    "mcp_servers": [],
}


class PlatformJudgeTest(unittest.TestCase):
    def test_run_platform_judge_parses_response(self) -> None:
        summary = summarize_manifest(MINIMAL)
        signals = [
            CodeSignal(
                kind="data_store",
                inferred_id="dynamodb",
                confidence=0.92,
                evidence=Evidence(file="src/x.py", line=1, snippet="ddb"),
                manifest_section="data_stores",
            )
        ]
        mock_resp = MagicMock()
        mock_resp.raise_for_status = MagicMock()
        mock_resp.json.return_value = {
            "findings": [
                {
                    "code": "MANIFEST_STALE",
                    "severity": "high",
                    "confidence": 0.9,
                    "title": "DynamoDB",
                    "detail": "Add dynamodb",
                    "manifestSection": "data_stores",
                    "suggestedCatalogId": "dynamodb",
                    "evidence": [{"file": "src/x.py", "line": 1, "snippet": "ddb"}],
                }
            ],
            "clean": False,
            "judgeModel": "claude-sonnet-4-6",
            "staticOnly": False,
        }
        mock_client = MagicMock()
        mock_client.post.return_value = mock_resp
        mock_client.__enter__ = MagicMock(return_value=mock_client)
        mock_client.__exit__ = MagicMock(return_value=False)

        with patch("arc_one_manifest.intelligence.judge.httpx.Client", return_value=mock_client):
            findings, clean, model = run_platform_judge(
                manifest_path="arc-one.agent.yaml",
                summary=summary,
                signals=signals,
                base_url="https://api.example.com",
                token="arc1_test",
            )
        self.assertFalse(clean)
        self.assertEqual(len(findings), 1)
        self.assertEqual(model, "claude-sonnet-4-6")
        posted = mock_client.post.call_args
        self.assertIn("/api/manifest/intelligence/audit", posted.args[0])


if __name__ == "__main__":
    unittest.main()
