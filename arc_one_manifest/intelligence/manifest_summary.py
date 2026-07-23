"""Resumen de recursos declarados en el manifest."""

from __future__ import annotations

from typing import Any

from arc_one_manifest.intelligence.models import ManifestSummary


def _asset_ids(rows: Any) -> set[str]:
    if not isinstance(rows, list):
        return set()
    out: set[str] = set()
    for row in rows:
        if not isinstance(row, dict):
            continue
        aid = row.get("asset_id") or row.get("assetId") or row.get("id")
        if isinstance(aid, str) and aid.strip():
            out.add(aid.strip())
    return out


def _identifiers(rows: Any, *keys: str) -> set[str]:
    if not isinstance(rows, list):
        return set()
    out: set[str] = set()
    for row in rows:
        if not isinstance(row, dict):
            continue
        for key in keys:
            val = row.get(key)
            if isinstance(val, str) and val.strip():
                out.add(val.strip())
                break
    return out


def summarize_manifest(manifest: dict[str, Any]) -> ManifestSummary:
    model = manifest.get("agent_model") or manifest.get("agentModel")
    return ManifestSummary(
        agent_model=model.strip() if isinstance(model, str) and model.strip() else None,
        data_stores=_asset_ids(manifest.get("data_stores") or manifest.get("dataStores")),
        integration_endpoints=_asset_ids(
            manifest.get("integration_endpoints") or manifest.get("integrationEndpoints")
        ),
        secrets_required=_identifiers(
            manifest.get("secrets_required") or manifest.get("secretsRequired"),
            # 🔴 `asset_id` PRIMERO y no opcional: es la **única** clave que el schema MADRE
            # acepta para esta sección (`_validate_secrets`), la que emite la plantilla
            # canónica y la que exporta el platform. Sin ella acá, todo agente que declare
            # secretos como manda la plantilla recibía un Hallazgo falso —"registrado en Arc
            # One y ya no declarado en el repo"— y encima con certeza ALTA, porque la pata 2
            # compara dos documentos declarados y presume no tener inferencia. (WS180)
            #
            # ⚠️ El fixture de paridad tenía las dos implementaciones **de acuerdo en algo
            # falso**, así que la red no podía cazarlo: por eso el caso `asset_id` es ahora
            # explícito en `manifest_summary_parity.json`.
            "asset_id",
            "assetId",
            "identifier",
            "id",
            "name",
        ),
        mcp_servers=_identifiers(
            manifest.get("mcp_servers") or manifest.get("mcpServers"),
            "mcp_id",
            "mcpId",
            "mcp_catalog_id",
            "mcpCatalogId",
            "id",
        ),
        knowledge_bases=_identifiers(
            manifest.get("knowledge_bases") or manifest.get("knowledgeBases"),
            "identifier",
            "id",
        ),
    )


def declared_ids_for_section(summary: ManifestSummary, section: str) -> set[str]:
    if section == "data_stores":
        return summary.data_stores
    if section == "integration_endpoints":
        return summary.integration_endpoints
    if section == "secrets_required":
        return summary.secrets_required
    if section == "mcp_servers":
        return summary.mcp_servers
    if section == "knowledge_bases":
        return summary.knowledge_bases
    if section == "agent_model":
        return {summary.agent_model} if summary.agent_model else set()
    return set()
