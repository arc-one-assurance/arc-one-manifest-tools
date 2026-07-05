"""Register payload mapping for MADRE v1.2 fields."""
from __future__ import annotations

import unittest

from arc_one_manifest.register import manifest_to_registro_payload


MINIMAL_MANIFEST = {
    "manifest_version": "1.2",
    "name": "Test Agent",
    "agent_version": "1.0.0",
    "agent_type": ["conversational"],
    "environment": ["non-productive"],
    "purpose": "Purpose with enough characters for validation rules.",
    "technical_owner": "tech@example.com",
    "business_owner": "biz@example.com",
    "system_prompt": {"content": "You are a test agent."},
    "declared_capabilities": {"capabilities": []},
    "connector": {
        "endpointUrl": "https://example.com/chat",
        "format": "REST_JSON",
        "authType": "NINGUNA",
    },
}


class RegisterV12MappingTest(unittest.TestCase):
    def test_maps_mcp_servers_and_agent_dependencies(self) -> None:
        manifest = {
            **MINIMAL_MANIFEST,
            "agent_dependencies": [
                {
                    "agent_id": "arc-agent-other",
                    "relation_type": ["INVOKE"],
                    "notes": "delegates billing",
                }
            ],
            "mcp_servers": [
                {
                    "mcp_id": "arc-one/core-banking-mcp",
                    "backed_by_assets": ["core-banking-postgres"],
                    "notes": "read-only",
                }
            ],
        }
        payload = manifest_to_registro_payload(manifest)
        ctx = payload["contexto"]
        self.assertEqual(
            ctx["agentDependencies"],
            [
                {
                    "agentId": "arc-agent-other",
                    "relationType": ["INVOKE"],
                    "notes": "delegates billing",
                }
            ],
        )
        self.assertEqual(
            ctx["mcpServers"],
            [
                {
                    "mcpId": "arc-one/core-banking-mcp",
                    "backedByAssets": ["core-banking-postgres"],
                    "notes": "read-only",
                }
            ],
        )

    def test_v11_without_v12_fields_still_maps(self) -> None:
        manifest = {**MINIMAL_MANIFEST, "manifest_version": "1.1"}
        payload = manifest_to_registro_payload(manifest)
        ctx = payload["contexto"]
        self.assertEqual(ctx.get("agentDependencies"), [])
        self.assertEqual(ctx.get("mcpServers"), [])


if __name__ == "__main__":
    unittest.main()
