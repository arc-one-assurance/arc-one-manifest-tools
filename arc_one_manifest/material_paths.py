"""Campos materiales del manifest — compartidos entre gate y manifest intelligence."""

from __future__ import annotations

MATERIAL_PATHS = frozenset(
    {
        "system_prompt",
        "declared_capabilities",
        "required_guardrails",
        "agent_skills",
        "agent_model",
        "autonomy_level",
        "integration_endpoints",
        "data_stores",
        "secrets_required",
        "knowledge_bases",
        "agent_dependencies",
        "mcp_servers",
        "purpose",
        "regulated_context",
        "network_exposure",
        "connector",
    }
)
