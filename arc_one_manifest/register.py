#!/usr/bin/env python3
"""
Manifest registration — MADRE v1.1/v1.2 YAML → Arc One registro-completo API.

Kept in sync with apps/api/arc_one_api/cli/agent_manifest.py (sandbox).
"""
from __future__ import annotations

import json
import os
import sys
from typing import Any, Dict, List, Optional

import httpx
import yaml


def _normalize_network_exposure(raw: Any) -> str:
    if raw is None:
        return "private"
    val = str(raw).strip().lower()
    if val in ("public", "public-internet"):
        return "public"
    return "private"


def _attach_manifest_v11_from_yaml(payload: Dict[str, Any], manifest: Dict[str, Any]) -> None:
    identidad = payload.setdefault("identidad", {})
    if not isinstance(identidad, dict):
        return
    exposure_raw = (
        manifest.get("network_exposure")
        or manifest.get("networkExposure")
        or (manifest.get("identity") or {}).get("networkExposure")
        or (manifest.get("identity") or {}).get("network_exposure")
    )
    identidad["networkExposure"] = _normalize_network_exposure(exposure_raw)

    guardrails_raw = manifest.get("required_guardrails") or manifest.get("requiredGuardrails")
    if isinstance(guardrails_raw, list):
        guardrails = []
        for item in guardrails_raw:
            if not isinstance(item, dict):
                continue
            identifier = str(item.get("identifier") or item.get("id") or "").strip()
            category = str(item.get("category") or "").strip()
            if not identifier or not category:
                continue
            gr: Dict[str, Any] = {"identifier": identifier, "category": category}
            provider = str(item.get("provider") or item.get("source") or "").strip()
            if provider:
                gr["provider"] = provider
            notes = str(item.get("notes") or "").strip()
            if notes:
                gr["notes"] = notes
            guardrails.append(gr)
        if guardrails:
            payload["defensas"] = {"requiredGuardrails": guardrails}

    kb_raw = manifest.get("knowledge_bases") or manifest.get("knowledgeBases")
    if isinstance(kb_raw, list):
        kbs = []
        for item in kb_raw:
            if not isinstance(item, dict):
                continue
            identifier = str(item.get("identifier") or item.get("id") or "").strip()
            if not identifier:
                continue
            kb: Dict[str, Any] = {"identifier": identifier}
            provider = str(item.get("provider") or item.get("source") or "").strip()
            if provider:
                kb["provider"] = provider
            notes = str(item.get("notes") or "").strip()
            if notes:
                kb["notes"] = notes
            kbs.append(kb)
        if kbs:
            defensas = payload.setdefault("defensas", {})
            if isinstance(defensas, dict):
                defensas["knowledgeBases"] = kbs


def _require(obj: Dict[str, Any], key: str) -> Any:
    if key not in obj:
        raise SystemExit(f"missing required field: {key}")
    return obj[key]


def _default_internal_owner_user_id() -> str:
    return (
        os.environ.get("ARC_ONE_REGISTRATION_OWNER_USER_ID", "").strip()
        or os.environ.get("ARC_ONE_DEBUG_SUB", "").strip()
        or "dev|user"
    )


def _outbound_token_from_env() -> str:
    return (
        os.environ.get("ARC_ONE_REGISTRATION_OUTBOUND_TOKEN")
        or os.environ.get("MOCKBANK_ASSURANCE_SHARED_TOKEN")
        or ""
    ).strip()


def _attach_outbound_token_from_env(conector: Dict[str, Any]) -> None:
    tipo = str(conector.get("tipoAutenticacion") or "NINGUNA").upper()
    if tipo not in ("BEARER_TOKEN", "API_KEY"):
        return
    tok = _outbound_token_from_env()
    if tok:
        conector["outboundToken"] = tok


def _mvp_manifest_to_payload(manifest: Dict[str, Any]) -> Dict[str, Any]:
    identidad = _require(manifest, "identity")
    version = _require(manifest, "version")
    connector = _require(manifest, "connector")

    payload: Dict[str, Any] = {
        "identidad": {
            "nombre": str(_require(identidad, "name")),
            "nombreCanonico": str(identidad.get("canonicalName") or "").strip() or None,
            "tipoAgente": str(_require(identidad, "type")),
            "proposito": str(_require(identidad, "purpose")),
            "descripcion": str(identidad.get("description") or "") or None,
            "proceso": str(identidad.get("process") or "") or None,
        },
        "useCase": {
            "nombre": str(manifest.get("useCase", {}).get("name") or "Primary use case"),
            "descripcion": str(
                manifest.get("useCase", {}).get("description") or "Imported from manifest"
            ),
            "nivelRiesgo": str(manifest.get("useCase", {}).get("riskLevel") or "MEDIO"),
            "usuariosAfectados": str(manifest.get("useCase", {}).get("affectedUsers") or "")
            or None,
            "procesoDeNegocio": str(manifest.get("useCase", {}).get("businessProcess") or "")
            or None,
            "dominioRegulatorio": str(manifest.get("useCase", {}).get("regulatoryDomain") or "")
            or None,
            "owners": manifest.get("owners")
            or [
                {
                    "tipo": "PRODUCTO",
                    "esInterno": True,
                    "userId": _default_internal_owner_user_id(),
                }
            ],
        },
        "conector": {
            "numeroVersion": str(_require(version, "number")),
            "modeloBase": str(version.get("baseModel") or "") or None,
            "proveedorModelo": str(version.get("modelProvider") or "") or None,
            "descripcionCambio": str(version.get("changeDescription") or "Initial version"),
            "nombreConnector": str(connector.get("name") or "") or None,
            "endpointUrl": str(_require(connector, "endpointUrl")),
            "formatoConector": str(connector.get("format") or "REST_JSON"),
            "tipoAutenticacion": str(connector.get("authType") or "NINGUNA"),
            "secretRef": str(connector.get("secretRef") or "") or None,
            "campoPromptEnBody": str(connector.get("promptField") or "prompt"),
            "campoRespuestaEnBody": str(connector.get("responseField") or "response"),
            "timeoutMs": int(connector.get("timeoutMs") or 30000),
        },
        "regulatorio": manifest.get("regulatory")
        or {
            "clasificacionRiesgo": "NO_DETERMINADO",
            "rolCorporativo": "NO_DETERMINADO",
            "flagTransparencia": False,
            "flagAltoRiesgoRevisar": False,
            "flagDominioRegulado": False,
            "flagInteraccionHumanos": False,
        },
    }
    sp_snap = manifest.get("systemPromptSnapshot") or manifest.get("system_prompt_snapshot")
    sp_ref = manifest.get("systemPromptRef") or manifest.get("system_prompt_ref")
    if isinstance(sp_ref, dict):
        mod = str(sp_ref.get("module") or "").strip()
        sym = str(sp_ref.get("symbol") or "").strip()
        sp_ref = f"{mod}#{sym}" if (mod or sym) else None
    if sp_snap:
        payload["systemPromptSnapshot"] = str(sp_snap)
    if sp_ref:
        payload["systemPromptRef"] = str(sp_ref)[:1024]
    _attach_outbound_token_from_env(payload["conector"])
    return json.loads(json.dumps(payload))


def _derive_proposito_from_description(desc: Any, fallback: str) -> str:
    if isinstance(desc, str) and desc.strip():
        one_line = " ".join(desc.split())
        if len(one_line) >= 20:
            return one_line[:2000]
    if len(fallback) >= 20:
        return fallback
    return fallback + " — registered from Arc One manifest."


def _v2_manifest_to_payload(manifest: Dict[str, Any]) -> Dict[str, Any]:
    agent_id = str(manifest.get("agent_id") or manifest.get("agentId") or "").strip()
    name = str(manifest.get("name") or agent_id or "agent").strip()
    desc = manifest.get("description")
    desc_str = desc.strip() if isinstance(desc, str) else ""
    proposito = _derive_proposito_from_description(desc, name)

    ver = str(manifest.get("version") or "1.0.0").strip()
    model = manifest.get("model") or {}
    modelo_base = str(model.get("family") or model.get("model") or "") or None
    proveedor = str(model.get("provider") or "") or None

    contract = manifest.get("contract") or {}
    endpoint_path = str(contract.get("endpoint") or "/api/v1/chat")
    auth = str(contract.get("auth") or "").lower()
    base = str(
        manifest.get("connectorBaseUrl")
        or manifest.get("connector_base_url")
        or os.getenv("ARC_ONE_MANIFEST_CONNECTOR_BASE", "http://127.0.0.1:8000")
    ).rstrip("/")
    if endpoint_path.startswith("http://") or endpoint_path.startswith("https://"):
        endpoint_url = endpoint_path
    else:
        ep = endpoint_path if endpoint_path.startswith("/") else f"/{endpoint_path}"
        endpoint_url = f"{base}{ep}"

    tipo_auth = "NINGUNA"
    if "bearer" in auth:
        tipo_auth = "BEARER_TOKEN"
    elif "api" in auth or "key" in auth:
        tipo_auth = "API_KEY"

    spr = manifest.get("system_prompt_ref") or manifest.get("systemPromptRef")
    ref_str: Optional[str] = None
    if isinstance(spr, dict):
        mod = str(spr.get("module") or "").strip()
        sym = str(spr.get("symbol") or "").strip()
        ref_str = f"{mod}#{sym}" if (mod or sym) else None
    elif isinstance(spr, str) and spr.strip():
        ref_str = spr.strip()[:1024]

    snap_raw = manifest.get("system_prompt_snapshot") or manifest.get("systemPromptSnapshot")
    snapshot = str(snap_raw).strip() if snap_raw is not None else ""

    dc = manifest.get("data_classes") or manifest.get("dataClasses")
    dom_reg = None
    if isinstance(dc, list) and dc:
        dom_reg = ", ".join(str(x) for x in dc[:12])

    rp = manifest.get("risk_profile") or {}
    criticality_high = False
    if isinstance(rp, dict):
        criticality_high = str(rp.get("criticality") or "").lower() == "critical"

    rev = manifest.get("revalidation") or {}
    rationale = rev.get("rationale") if isinstance(rev, dict) else None
    cambio_desc = str(rationale or "Manifest v2 import")[:2000]

    payload: Dict[str, Any] = {
        "identidad": {
            "nombre": name,
            "nombreCanonico": agent_id or None,
            "tipoAgente": "CONVERSACIONAL",
            "proposito": proposito,
            "descripcion": desc_str or None,
            "proceso": str(manifest.get("owner") or "") or None,
        },
        "useCase": {
            "nombre": f"{name} — primary",
            "descripcion": desc_str[:2000] if desc_str else "Imported from manifest v2.",
            "nivelRiesgo": "ALTO" if criticality_high else "MEDIO",
            "dominioRegulatorio": dom_reg,
            "owners": manifest.get("owners")
            or [
                {
                    "tipo": "PRODUCTO",
                    "esInterno": True,
                    "userId": _default_internal_owner_user_id(),
                }
            ],
        },
        "conector": {
            "numeroVersion": ver,
            "modeloBase": modelo_base,
            "proveedorModelo": proveedor,
            "descripcionCambio": cambio_desc,
            "nombreConnector": f"{agent_id or 'agent'} connector",
            "endpointUrl": endpoint_url,
            "formatoConector": "REST_JSON",
            "tipoAutenticacion": tipo_auth,
            "secretRef": str(manifest.get("secretRef") or manifest.get("secret_ref") or "") or None,
            "campoPromptEnBody": "prompt",
            "campoRespuestaEnBody": "response",
            "timeoutMs": 30000,
        },
        "regulatorio": {
            "clasificacionRiesgo": "NO_DETERMINADO",
            "rolCorporativo": "NO_DETERMINADO",
            "flagTransparencia": True,
            "flagAltoRiesgoRevisar": criticality_high,
            "flagDominioRegulado": bool(dom_reg),
            "flagInteraccionHumanos": True,
            "dominiosRegulatoriosAplicables": dom_reg,
            "notasClasificacion": (str(rationale)[:2000] if rationale else None),
        },
    }
    if snapshot:
        payload["systemPromptSnapshot"] = snapshot[:500_000]
    if ref_str:
        payload["systemPromptRef"] = ref_str

    _attach_outbound_token_from_env(payload["conector"])
    return json.loads(json.dumps(payload))


def _infra_binding_to_payload(manifest: Dict[str, Any]) -> Optional[List[Dict[str, Any]]]:
    """Map `infra_binding` (YAML snake_case) → identidad.infraBinding (payload camelCase).

    Coordenadas, nunca secretos: la credencial de la nube vive en la conexión del
    workspace. El provider no se declara — Arc One lo deriva de la cuenta.
    """
    raw = manifest.get("infra_binding")
    if raw is None:
        raw = manifest.get("infraBinding")
    if not isinstance(raw, list) or not raw:
        return None

    bindings: List[Dict[str, Any]] = []
    for item in raw:
        if not isinstance(item, dict):
            continue
        scope = item.get("scope") if isinstance(item.get("scope"), dict) else {}
        mapped_scope: Dict[str, Any] = {}
        prefixes = scope.get("resource_prefixes") or scope.get("resourcePrefixes")
        if prefixes:
            mapped_scope["resourcePrefixes"] = list(prefixes)
        if scope.get("regions"):
            mapped_scope["regions"] = list(scope["regions"])
        if scope.get("labels"):
            mapped_scope["labels"] = dict(scope["labels"])
        bindings.append({"account": item.get("account"), "scope": mapped_scope})
    return bindings or None


def ci_provenance_headers() -> Dict[str, str]:
    """De qué repo y qué corrida viene esta llamada.

    Arc One nunca entra al repo del cliente (push puro, por diseño), así que estos dos
    headers son la ÚNICA forma de que sepa qué repositorio está reportando y cuándo. Sin
    esto, un repo que dejó de reportar es indistinguible de uno que nunca se conectó.

    Se leen de las variables que GitHub Actions ya define; nada que el cliente configure.
    """
    out: Dict[str, str] = {}
    repo = os.environ.get("ARC_ONE_REPO") or os.environ.get("GITHUB_REPOSITORY") or ""
    if repo.strip():
        out["X-Arc-One-Repo"] = repo.strip()[:256]
    run = os.environ.get("ARC_ONE_RUN_REF") or os.environ.get("GITHUB_RUN_ID") or ""
    if run.strip():
        out["X-Arc-One-Run"] = run.strip()[:256]
    return out


def _madre_manifest_v2_to_payload(manifest: Dict[str, Any]) -> Dict[str, Any]:
    """Map MADRE v1.1/v1.2/v1.3 YAML (export from wizard) → RegistroManifestV2Body JSON."""
    sp = manifest.get("system_prompt") or {}
    caps = manifest.get("declared_capabilities") or {}

    conectividad = None
    connector = manifest.get("connector")
    if isinstance(connector, dict):
        conectividad = {
            "endpointUrl": connector.get("endpointUrl") or connector.get("endpoint_url"),
            "formatoConector": connector.get("format") or connector.get("formatoConector") or "REST_JSON",
            "tipoAutenticacion": connector.get("authType") or connector.get("tipoAutenticacion") or "NINGUNA",
            "secretRef": connector.get("secretRef"),
            "campoPromptEnBody": connector.get("promptField") or "prompt",
            "campoRespuestaEnBody": connector.get("responseField") or "response",
            "timeoutMs": int(connector.get("timeoutMs") or 30000),
            "nombreConnector": connector.get("name"),
        }

    payload: Dict[str, Any] = {
        "identidad": {
            "name": manifest["name"],
            "manifestVersion": str(
                manifest.get("manifest_version") or manifest.get("manifestVersion") or ""
            ).strip()
            or None,
            "agentVersion": manifest.get("agent_version") or manifest.get("agentVersion") or "1.0.0",
            "agentType": manifest.get("agent_type") or manifest.get("agentType") or ["conversational"],
            "environment": manifest.get("environment") or ["non-productive"],
            "purpose": manifest["purpose"],
            "technicalOwner": manifest["technical_owner"],
            "businessOwner": manifest["business_owner"],
            "targetUsers": manifest.get("target_users") or [],
            "customerFacing": bool(manifest.get("customer_facing")),
            "agentOrigin": manifest.get("agent_origin") or "internal",
            "agentModel": manifest.get("agent_model"),
            "thirdPartyIdentifier": manifest.get("third_party_identifier"),
            "framework": manifest.get("framework"),
            "deploymentTarget": manifest.get("deployment_target") or "custom/internal-infra",
            "regulatedContext": manifest.get("regulated_context") or ["eu-ai-act/eu"],
            "networkExposure": manifest.get("network_exposure") or "private",
        },
        "comportamiento": {
            "systemPrompt": {
                "transparencyLevel": sp.get("transparency_level") or "full",
                "content": sp.get("content"),
                "notes": sp.get("notes"),
            },
            "declaredCapabilities": {
                "transparencyLevel": caps.get("transparency_level") or "full",
                "capabilities": [
                    {
                        "capability": c.get("capability") if isinstance(c, dict) else c,
                        **({"notes": c.get("notes")} if isinstance(c, dict) and c.get("notes") else {}),
                    }
                    for c in (caps.get("capabilities") or [])
                ],
                "notes": caps.get("notes"),
            },
            "requiredGuardrails": manifest.get("required_guardrails") or [],
            "agentSkills": [
                {
                    "id": s.get("id"),
                    "category": s.get("category"),
                    **({"notes": s.get("notes")} if s.get("notes") else {}),
                }
                for s in (manifest.get("agent_skills") or [])
            ],
            "autonomyLevel": manifest.get("autonomy_level") or "supervised",
            "humanInTheLoop": manifest.get("human_in_the_loop", True),
        },
        "contexto": {
            "integrationEndpoints": [
                {
                    "assetId": e.get("asset_id"),
                    "relationType": e.get("relation_type") or [],
                    **({"notes": e.get("notes")} if e.get("notes") else {}),
                }
                for e in (manifest.get("integration_endpoints") or [])
            ],
            "dataStores": [
                {
                    "assetId": d.get("asset_id"),
                    "relationType": d.get("relation_type") or [],
                    **({"notes": d.get("notes")} if d.get("notes") else {}),
                }
                for d in (manifest.get("data_stores") or [])
            ],
            "secretsRequired": [
                {
                    "assetId": s.get("asset_id"),
                    **({"notes": s.get("notes")} if s.get("notes") else {}),
                }
                for s in (manifest.get("secrets_required") or [])
            ],
            "knowledgeBases": manifest.get("knowledge_bases") or manifest.get("knowledgeBases") or [],
            "agentDependencies": [
                {
                    "agentId": d.get("agent_id") or d.get("agentId"),
                    "relationType": d.get("relation_type") or d.get("relationType") or [],
                    **({"notes": d.get("notes")} if d.get("notes") else {}),
                }
                for d in (manifest.get("agent_dependencies") or manifest.get("agentDependencies") or [])
            ],
            "mcpServers": [
                {
                    "mcpId": m.get("mcp_id") or m.get("mcpId") or m.get("identifier") or m.get("id"),
                    "backedByAssets": m.get("backed_by_assets") or m.get("backedByAssets") or [],
                    **({"notes": m.get("notes")} if m.get("notes") else {}),
                }
                for m in (manifest.get("mcp_servers") or manifest.get("mcpServers") or [])
            ],
        },
    }
    infra_binding = _infra_binding_to_payload(manifest)
    if infra_binding:
        payload["identidad"]["infraBinding"] = infra_binding

    if conectividad and conectividad.get("endpointUrl"):
        payload["conectividad"] = conectividad
        _attach_outbound_token_from_env(payload["conectividad"])
    return json.loads(json.dumps(payload))


def manifest_to_registro_payload(manifest: Dict[str, Any]) -> Dict[str, Any]:
    if manifest.get("manifest_version") and manifest.get("name") and (
        manifest.get("agent_type") is not None or manifest.get("technical_owner")
    ):
        return _madre_manifest_v2_to_payload(manifest)
    if isinstance(manifest.get("identity"), dict):
        legacy = _mvp_manifest_to_payload(manifest)
        _attach_manifest_v11_from_yaml(legacy, manifest)
        raise SystemExit(
            "Legacy MVP manifest format is no longer supported by registro-completo. "
            "Re-export from the Manifest v2 wizard or use MADRE v1.1 YAML."
        )
    if "agent_id" in manifest or (
        manifest.get("contract") is not None
        and (
            manifest.get("system_prompt_ref") is not None
            or manifest.get("systemPromptRef") is not None
        )
    ):
        raise SystemExit(
            "Experimental v2 contract manifest is deprecated. Use MADRE v1.1 export from Arc One wizard."
        )
    raise SystemExit(
        "Unsupported manifest: expected MADRE v1.1 keys (manifest_version, name, agent_type, purpose, …)."
    )


def apply(
    path: str,
    *,
    base_url: str,
    dry_run: bool,
    token: str,
    debug_sub: str,
) -> None:
    manifest = yaml.safe_load(open(path, encoding="utf-8"))
    if not isinstance(manifest, dict):
        raise SystemExit("manifest must be a YAML mapping")
    payload = manifest_to_registro_payload(manifest)
    intent = os.environ.get("ARC_ONE_REGISTRATION_INTENT", "").strip()
    if not intent:
        agent_id = str(manifest.get("agent_id") or manifest.get("agentId") or "").strip()
        intent = "version" if agent_id.startswith("arc-agent-") else "create"
    url = base_url.rstrip("/") + f"/api/agentes/registro-completo?registrationIntent={intent}"
    if dry_run:
        url += "&dryRun=true"
    headers: Dict[str, str] = {"Content-Type": "application/json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    if debug_sub:
        headers["X-ArcOne-Debug-Sub"] = debug_sub
    headers.update(ci_provenance_headers())

    r = httpx.post(url, headers=headers, json=payload, timeout=120.0)
    if not (200 <= r.status_code < 300):
        print(r.text, file=sys.stderr)
        raise SystemExit(f"API error {r.status_code}")
    print(json.dumps(r.json(), indent=2, ensure_ascii=False))
