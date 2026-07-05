"""Tests LLM synthesizer for generate."""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from arc_one_manifest.intelligence.generate_synthesizer import synthesize_narrative_fields


class GenerateSynthesizerTest(unittest.TestCase):
    def test_synthesize_with_mock_llm(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "README.md").write_text("# Banking Agent\nRead-only assistant.\n", encoding="utf-8")
            manifest = {
                "agent_model": "anthropic/claude-sonnet-4-7",
                "data_stores": [{"asset_id": "postgresql"}],
                "mcp_servers": [],
            }
            mock_response = json.dumps(
                {
                    "purpose": "Asistente bancario read-only para consultas de saldo y movimientos en entorno PoC.",
                    "system_prompt_content": "Sos un asistente bancario. Respondé en español.",
                    "technical_owner": None,
                    "business_owner": None,
                    "confidence": 0.8,
                }
            )

            class MockClient:
                def complete(self, system: str, user_payload: str) -> str:
                    return mock_response

            with patch.dict("os.environ", {"ARC_ONE_LLM_API_KEY": "sk-test"}):
                with patch(
                    "arc_one_manifest.intelligence.generate_synthesizer.AnthropicJudgeClient",
                    return_value=MockClient(),
                ):
                    patches, fields = synthesize_narrative_fields(
                        root, profile="generic", manifest=manifest, signals_summary=["data_store:postgresql"]
                    )
            self.assertIn("purpose", patches)
            self.assertGreaterEqual(len(patches["purpose"]), 50)
            self.assertIn("system_prompt", patches)
            self.assertIn("purpose", fields)


if __name__ == "__main__":
    unittest.main()
