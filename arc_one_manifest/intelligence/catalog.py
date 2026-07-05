"""Catálogo embebido — mapeo de señales a IDs Arc One conocidos."""

from __future__ import annotations

# Aliases comunes → ID canónico en catálogo Arc One (sync manual con sandbox).
_CATALOG_IDS: dict[str, str] = {
    "dynamodb": "dynamodb",
    "aws-s3": "aws-s3",
    "aws-sqs": "aws-sqs",
    "aws-sns": "aws-sns",
    "aws-secrets-manager": "aws-secrets-manager",
    "postgresql": "postgresql",
    "postgres": "postgresql",
    "redis": "redis",
    "pinecone": "pinecone",
    "core-banking-postgres": "core-banking-postgres",
    "core-banking-mcp": "core-banking-mcp",
    "anthropic": "anthropic/claude-sonnet-4-7",
    "openai": "openai/gpt-4o",
}

_DATA_STORES = frozenset(
    {
        "dynamodb",
        "aws-s3",
        "aws-sqs",
        "aws-sns",
        "aws-secrets-manager",
        "postgresql",
        "redis",
        "pinecone",
    }
)

_MCP_SERVERS = frozenset({"core-banking-mcp", "payments-mcp", "core-banking-test-2"})


def normalize_catalog_id(raw: str) -> str:
    slug = raw.strip().lower().replace("_", "-")
    return _CATALOG_IDS.get(slug, slug)


def is_known_catalog_id(catalog_id: str, *, section: str) -> bool:
    cid = normalize_catalog_id(catalog_id)
    if section == "data_stores":
        return cid in _DATA_STORES
    if section == "mcp_servers":
        return cid in _MCP_SERVERS or cid.endswith("-mcp")
    if section == "integration_endpoints":
        return True
    return cid in _CATALOG_IDS.values()


def resolve_signal_catalog_id(inferred_id: str, manifest_section: str) -> tuple[str, bool]:
    """Devuelve (id canónico, conocido en catálogo embebido)."""
    canonical = normalize_catalog_id(inferred_id)
    known = is_known_catalog_id(canonical, section=manifest_section)
    return canonical, known
