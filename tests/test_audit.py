"""Tests Manifest Intelligence — audit estático (Fase 1)."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

import yaml

from arc_one_manifest.intelligence.audit import run_audit, static_findings
from arc_one_manifest.intelligence.extractors.env_example import extract_env_example_signals
from arc_one_manifest.intelligence.extractors.python_ast import extract_python_ast_signals
from arc_one_manifest.intelligence.git_diff import in_scope, DEFAULT_INCLUDE, DEFAULT_EXCLUDE
from arc_one_manifest.intelligence.manifest_summary import summarize_manifest
from arc_one_manifest.intelligence.models import CodeSignal, Evidence


MINIMAL_MANIFEST = {
    "manifest_version": "1.2",
    "name": "Test",
    "agent_version": "1.0.0",
    "agent_model": "anthropic/claude-sonnet-4-7",
    "data_stores": [
        {"asset_id": "postgresql", "relation_type": ["READ"]},
        {"asset_id": "pinecone", "relation_type": ["QUERY"]},
    ],
    "integration_endpoints": [],
    "mcp_servers": [],
}


class PythonAstExtractorTest(unittest.TestCase):
    def test_detects_boto3_dynamodb(self) -> None:
        lines = ['client = boto3.client("dynamodb", region_name="eu-west-1")']
        signals = extract_python_ast_signals("src/storage.py", lines)
        kinds = {s.inferred_id for s in signals}
        self.assertIn("dynamodb", kinds)

    def test_detects_mcp_connect(self) -> None:
        lines = ['mcp.connect("core-banking-mcp")']
        signals = extract_python_ast_signals("src/agent.py", lines)
        self.assertTrue(any(s.kind == "mcp_server" for s in signals))

    def test_detects_redis_client(self) -> None:
        lines = ['cache = redis.Redis(host="localhost")']
        signals = extract_python_ast_signals("src/worker.py", lines)
        self.assertTrue(any(s.inferred_id == "redis" for s in signals))


class EnvExampleExtractorTest(unittest.TestCase):
    def test_dotenv_example_in_scope(self) -> None:
        self.assertTrue(in_scope(".env.example", DEFAULT_INCLUDE, DEFAULT_EXCLUDE))

    def test_detects_dynamodb_env_var(self) -> None:
        lines = ["DYNAMODB_TABLE=sessions"]
        signals = extract_env_example_signals(".env.example", lines)
        self.assertTrue(any(s.inferred_id == "dynamodb" for s in signals))


class StaticFindingsTest(unittest.TestCase):
    def test_flags_undeclared_dynamodb(self) -> None:
        summary = summarize_manifest(MINIMAL_MANIFEST)
        signal = CodeSignal(
            kind="data_store",
            inferred_id="dynamodb",
            confidence=0.92,
            evidence=Evidence(file="src/storage.py", line=1, snippet="boto3.client('dynamodb')"),
            manifest_section="data_stores",
        )
        findings = static_findings([signal], summary, min_confidence=0.85)
        self.assertEqual(len(findings), 1)
        self.assertEqual(findings[0].code, "MANIFEST_STALE")

    def test_ignores_declared_postgresql(self) -> None:
        summary = summarize_manifest(MINIMAL_MANIFEST)
        signal = CodeSignal(
            kind="data_store",
            inferred_id="postgresql",
            confidence=0.92,
            evidence=Evidence(file="src/db.py", line=3, snippet="psycopg.connect"),
            manifest_section="data_stores",
        )
        findings = static_findings([signal], summary, min_confidence=0.85)
        self.assertEqual(findings, [])

    def test_ignores_llm_api_key_when_model_declared(self) -> None:
        summary = summarize_manifest(MINIMAL_MANIFEST)
        signal = CodeSignal(
            kind="secret",
            inferred_id="llm-api-key",
            confidence=0.88,
            evidence=Evidence(file=".env.example", line=1, snippet="ANTHROPIC_API_KEY=…"),
            manifest_section="secrets_required",
        )
        findings = static_findings([signal], summary, min_confidence=0.85)
        self.assertEqual(findings, [])


class RunAuditIntegrationTest(unittest.TestCase):
    def test_scan_all_finds_drift_in_temp_repo(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            manifest_path = root / "arc-one.agent.yaml"
            manifest_path.write_text(yaml.safe_dump(MINIMAL_MANIFEST), encoding="utf-8")
            src = root / "src"
            src.mkdir()
            (src / "storage.py").write_text(
                'import boto3\nclient = boto3.client("dynamodb")\n',
                encoding="utf-8",
            )

            report = run_audit(
                manifest_path,
                repo=root,
                scan_all=True,
                static_only=True,
                min_confidence=0.85,
            )
            self.assertFalse(report.clean)
            codes = {f.code for f in report.findings}
            self.assertIn("MANIFEST_STALE", codes)
            self.assertTrue(any("dynamodb" in f.suggested_catalog_id for f in report.findings))


if __name__ == "__main__":
    unittest.main()
