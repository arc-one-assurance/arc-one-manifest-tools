"""Tests del LLM Judge (Capa 2) — client mockeado."""

from __future__ import annotations

import json
import unittest

from arc_one_manifest.intelligence.audit import static_findings
from arc_one_manifest.intelligence.judge import build_judge_payload, parse_judge_response, run_judge
from arc_one_manifest.intelligence.manifest_summary import summarize_manifest
from arc_one_manifest.intelligence.models import CodeSignal, Evidence
from arc_one_manifest.intelligence.reporter import report_to_pr_comment
from arc_one_manifest.intelligence.audit import run_audit
from pathlib import Path

MINIMAL_MANIFEST = {
    "manifest_version": "1.2",
    "name": "Test",
    "agent_version": "1.0.0",
    "agent_model": "anthropic/claude-sonnet-4-7",
    "data_stores": [{"asset_id": "postgresql", "relation_type": ["READ"]}],
    "integration_endpoints": [],
    "mcp_servers": [],
}


class MockJudgeClient:
    def __init__(self, response: str) -> None:
        self._response = response
        self.last_user_payload: str | None = None

    def complete(self, system: str, user_payload: str) -> str:
        self.last_user_payload = user_payload
        return self._response


class JudgeParseTest(unittest.TestCase):
    def test_parse_judge_response(self) -> None:
        raw = json.dumps(
            {
                "findings": [
                    {
                        "code": "MANIFEST_STALE",
                        "severity": "high",
                        "confidence": 0.9,
                        "title": "DynamoDB missing",
                        "detail": "Add dynamodb to data_stores",
                        "manifestSection": "data_stores",
                        "suggestedCatalogId": "dynamodb",
                        "evidence": [{"file": "src/x.py", "line": 1, "snippet": "boto3"}],
                    }
                ],
                "clean": False,
            }
        )
        findings, clean = parse_judge_response(raw)
        self.assertFalse(clean)
        self.assertEqual(len(findings), 1)
        self.assertEqual(findings[0].suggested_catalog_id, "dynamodb")


class JudgeRunTest(unittest.TestCase):
    def test_run_judge_with_mock_client(self) -> None:
        summary = summarize_manifest(MINIMAL_MANIFEST)
        signals = [
            CodeSignal(
                kind="data_store",
                inferred_id="dynamodb",
                confidence=0.92,
                evidence=Evidence(file="src/storage.py", line=42, snippet="boto3.client('dynamodb')"),
                manifest_section="data_stores",
            )
        ]
        mock_response = json.dumps(
            {
                "findings": [
                    {
                        "code": "MANIFEST_STALE",
                        "severity": "high",
                        "confidence": 0.88,
                        "title": "Nuevo DynamoDB",
                        "detail": "Declarar dynamodb",
                        "manifestSection": "data_stores",
                        "suggestedCatalogId": "dynamodb",
                        "evidence": [{"file": "src/storage.py", "line": 42, "snippet": "boto3"}],
                    }
                ],
                "clean": False,
            }
        )
        client = MockJudgeClient(mock_response)
        findings, clean, model = run_judge(
            manifest_path="arc-one.agent.yaml",
            summary=summary,
            signals=signals,
            client=client,
            min_confidence=0.7,
        )
        self.assertFalse(clean)
        self.assertEqual(len(findings), 1)
        self.assertIsNotNone(client.last_user_payload)
        payload = json.loads(client.last_user_payload or "{}")
        self.assertIn("code_signals", payload)

    def test_build_judge_payload_includes_material_paths(self) -> None:
        summary = summarize_manifest(MINIMAL_MANIFEST)
        payload = build_judge_payload(
            manifest_path="arc-one.agent.yaml",
            summary=summary,
            signals=[],
        )
        self.assertIn("material_paths", payload)
        self.assertIn("data_stores", payload["material_paths"])


class ReporterTest(unittest.TestCase):
    def test_pr_comment_clean(self) -> None:
        fixtures = Path(__file__).parent / "fixtures" / "audit_scenarios" / "clean-banking"
        report = run_audit(
            fixtures / "arc-one.agent.yaml",
            repo=fixtures,
            scan_all=True,
            static_only=True,
        )
        md = report_to_pr_comment(report)
        self.assertIn("✅ Sin drift detectado entre código y manifest", md)

    def test_un_diff_limpio_no_afirma_sobre_el_repo_entero(self) -> None:
        """🔴 ``clean`` con alcance `diff` significa "no vi nada en lo que miré".

        El mismo fixture, la misma ausencia de drift: lo único que cambia es cuánto se
        abrió. Un ✅ acá diría que el repositorio está bien cuando lo que pasó es que casi
        no se leyó — el silencio que la Fase 2 vino a cerrar, en la primera línea que el
        cliente lee del comment.
        """
        fixtures = Path(__file__).parent / "fixtures" / "audit_scenarios" / "clean-banking"
        report = run_audit(
            fixtures / "arc-one.agent.yaml",
            repo=fixtures,
            scan_all=False,
            static_only=True,
        )
        self.assertTrue(report.clean)
        md = report_to_pr_comment(report)
        self.assertNotIn("✅", md)
        self.assertIn("Sin drift en los archivos de este cambio", md)
        self.assertIn("--scan-all", md)

    def test_pr_comment_with_findings(self) -> None:
        summary = summarize_manifest(MINIMAL_MANIFEST)
        signal = CodeSignal(
            kind="data_store",
            inferred_id="dynamodb",
            confidence=0.92,
            evidence=Evidence(file="src/storage.py", line=1, snippet="ddb"),
            manifest_section="data_stores",
        )
        findings = static_findings([signal], summary, min_confidence=0.85)
        from arc_one_manifest.intelligence.models import AuditReport

        report = AuditReport(
            manifest_path="arc-one.agent.yaml",
            base_ref="origin/main",
            static_only=True,
            manifest_summary=summary,
            code_signals=[signal],
            findings=findings,
            clean=False,
        )
        md = report_to_pr_comment(report)
        self.assertIn("Drift Guard", md)
        self.assertIn("dynamodb", md)


if __name__ == "__main__":
    unittest.main()
