"""MADRE v1.1 manifest structural validation — aligned with Arc One RegistroManifestV2Body."""
from __future__ import annotations

import re
from typing import Any, Dict, List, Optional, Sequence

MANIFEST_VERSION = "1.2"
MANIFEST_VERSIONS = frozenset({"1.1", "1.2"})

AGENT_RELATION_TYPES = frozenset({"INVOKE", "DELEGATE", "COORDINATE"})
MCP_TRANSPORTS = frozenset({"stdio", "sse", "streamable-http"})

EMAIL_RE = re.compile(r"^[^\s@]+@[^\s@]+\.[^\s@]+$")
SEMVER_RE = re.compile(r"^[0-9]+\.[0-9]+\.[0-9]+$")
CONNECTOR_PLACEHOLDER = "__AWS_SERVICE_URL__"

AGENT_TYPES = frozenset(
    {
        "conversational",
        "decision-making",
        "retrieval-augmented",
        "autonomous-action",
        "data-transformation",
        "code-generation",
        "monitoring-alerting",
    }
)
ENVIRONMENTS = frozenset({"productive", "non-productive"})
TARGET_USERS = frozenset(
    {
        "internal_employee",
        "customer",
        "partner",
        "public_anonymous",
        "automated_system",
    }
)
EXTERNAL_TARGET_USERS = frozenset({"customer", "partner", "public_anonymous"})
AGENT_ORIGINS = frozenset({"internal", "third_party"})
TRANSPARENCY_LEVELS = frozenset({"full", "approximation", "unknown"})
AUTONOMY_LEVELS = frozenset({"advisory", "supervised", "autonomous"})
SKILL_CATEGORIES = frozenset(
    {
        "customer-support",
        "transactional",
        "analytical",
        "compliance-and-audit",
        "agent-orchestration-meta",
        "other",
    }
)
GUARDRAIL_CATEGORIES = frozenset(
    {
        "prompt-injection",
        "jailbreak",
        "pii",
        "authority-limit",
        "output-validation",
        "content-safety",
        "audit-trail",
        "other",
    }
)
RELATION_TYPES = frozenset(
    {"READ", "WRITE", "QUERY", "INVOKE", "NOTIFY", "EXECUTE", "PERSIST"}
)
NETWORK_EXPOSURES = frozenset({"private", "public", "public-internet"})
CONNECTOR_FORMATS = frozenset({"REST_JSON", "GRAPHQL", "GRPC", "SSE", "WEBSOCKET"})
CONNECTOR_AUTH = frozenset({"NINGUNA", "BEARER_TOKEN", "API_KEY", "OAUTH2", "MTLS"})


class ManifestValidationError(Exception):
    """Raised when one or more manifest fields fail structural validation."""

    def __init__(self, errors: Sequence[str]) -> None:
        self.errors = list(errors)
        bullet_list = "\n".join(f"  - {e}" for e in self.errors)
        super().__init__(f"Manifest inválido ({len(self.errors)} error(es)):\n{bullet_list}")


def _err(errors: List[str], path: str, message: str) -> None:
    errors.append(f"{path}: {message}")


def _require_str(errors: List[str], obj: Dict[str, Any], key: str, path: str) -> Optional[str]:
    if key not in obj:
        _err(errors, path, f"campo obligatorio faltante `{key}`")
        return None
    val = obj[key]
    if not isinstance(val, str) or not val.strip():
        _err(errors, path, f"`{key}` debe ser un string no vacío")
        return None
    return val.strip()


def _require_bool(errors: List[str], obj: Dict[str, Any], key: str, path: str) -> Optional[bool]:
    if key not in obj:
        _err(errors, path, f"campo obligatorio faltante `{key}`")
        return None
    val = obj[key]
    if not isinstance(val, bool):
        _err(errors, path, f"`{key}` debe ser boolean (true/false)")
        return None
    return val


def _require_list(errors: List[str], obj: Dict[str, Any], key: str, path: str) -> Optional[List[Any]]:
    if key not in obj:
        _err(errors, path, f"campo obligatorio faltante `{key}`")
        return None
    val = obj[key]
    if not isinstance(val, list) or not val:
        _err(errors, path, f"`{key}` debe ser una lista con al menos un elemento")
        return None
    return val


def _validate_email(errors: List[str], value: Optional[str], path: str) -> None:
    if value is None:
        return
    if not EMAIL_RE.match(value):
        _err(errors, path, "email inválido")


def _validate_semver(errors: List[str], value: Optional[str], path: str) -> None:
    if value is None:
        return
    if not SEMVER_RE.match(value):
        _err(errors, path, "debe ser semver MAJOR.MINOR.PATCH (ej. 1.0.1)")


def _validate_system_prompt(errors: List[str], sp: Any, path: str = "system_prompt") -> None:
    if not isinstance(sp, dict):
        _err(errors, path, "debe ser un objeto YAML")
        return
    tl = str(sp.get("transparency_level") or sp.get("transparencyLevel") or "full").strip()
    if tl not in TRANSPARENCY_LEVELS:
        _err(errors, f"{path}.transparency_level", f"valor inválido `{tl}`")
        return
    content = str(sp.get("content") or "").strip()
    reference = str(sp.get("reference") or "").strip()
    notes = str(sp.get("notes") or "").strip()
    if tl in ("full", "approximation"):
        if len(content) < 20 and len(reference) < 8:
            _err(
                errors,
                path,
                "requiere `content` (20+ caracteres) o `reference` (ARN/URI, 8+ caracteres)",
            )
    elif tl == "unknown" and len(notes) < 50:
        _err(errors, f"{path}.notes", "requiere al menos 50 caracteres si transparency es unknown")


def _validate_declared_capabilities(errors: List[str], caps: Any, path: str = "declared_capabilities") -> None:
    if not isinstance(caps, dict):
        _err(errors, path, "debe ser un objeto YAML")
        return
    tl = str(caps.get("transparency_level") or caps.get("transparencyLevel") or "full").strip()
    if tl not in TRANSPARENCY_LEVELS:
        _err(errors, f"{path}.transparency_level", f"valor inválido `{tl}`")
        return
    raw_caps = caps.get("capabilities")
    if not isinstance(raw_caps, list):
        _err(errors, f"{path}.capabilities", "debe ser una lista")
        return
    if tl in ("full", "approximation") and not raw_caps:
        _err(errors, f"{path}.capabilities", "requiere al menos una capability")
    notes = str(caps.get("notes") or "").strip()
    if tl == "unknown" and len(notes) < 50:
        _err(
            errors,
            f"{path}.notes",
            "requiere al menos 50 caracteres si transparency es unknown",
        )
    for idx, item in enumerate(raw_caps):
        if isinstance(item, dict):
            cap_id = str(item.get("capability") or "").strip()
            if not cap_id:
                _err(errors, f"{path}.capabilities[{idx}]", "falta `capability`")
        elif isinstance(item, str) and item.strip():
            continue
        else:
            _err(errors, f"{path}.capabilities[{idx}]", "entrada inválida")


def _validate_guardrails(errors: List[str], items: Any, path: str) -> None:
    if items is None:
        return
    if not isinstance(items, list):
        _err(errors, path, "debe ser una lista")
        return
    for idx, item in enumerate(items):
        if not isinstance(item, dict):
            _err(errors, f"{path}[{idx}]", "debe ser un objeto")
            continue
        identifier = str(item.get("identifier") or item.get("id") or "").strip()
        category = str(item.get("category") or "").strip()
        if not identifier:
            _err(errors, f"{path}[{idx}]", "falta `identifier`")
        if not category:
            _err(errors, f"{path}[{idx}]", "falta `category`")
        elif category not in GUARDRAIL_CATEGORIES:
            _err(errors, f"{path}[{idx}].category", f"valor inválido `{category}`")


def _validate_skills(errors: List[str], items: Any, path: str = "agent_skills") -> None:
    if items is None:
        return
    if not isinstance(items, list):
        _err(errors, path, "debe ser una lista")
        return
    for idx, item in enumerate(items):
        if not isinstance(item, dict):
            _err(errors, f"{path}[{idx}]", "debe ser un objeto")
            continue
        skill_id = str(item.get("id") or "").strip()
        category = str(item.get("category") or "").strip()
        if not skill_id:
            _err(errors, f"{path}[{idx}]", "falta `id`")
        if not category:
            _err(errors, f"{path}[{idx}]", "falta `category`")
        elif category not in SKILL_CATEGORIES:
            _err(errors, f"{path}[{idx}].category", f"valor inválido `{category}`")


def _validate_context_assets(errors: List[str], items: Any, path: str) -> None:
    if items is None:
        return
    if not isinstance(items, list):
        _err(errors, path, "debe ser una lista")
        return
    for idx, item in enumerate(items):
        if not isinstance(item, dict):
            _err(errors, f"{path}[{idx}]", "debe ser un objeto")
            continue
        asset_id = str(item.get("asset_id") or item.get("assetId") or "").strip()
        rel = item.get("relation_type") or item.get("relationType")
        if not asset_id:
            _err(errors, f"{path}[{idx}]", "falta `asset_id`")
        if not isinstance(rel, list) or not rel:
            _err(errors, f"{path}[{idx}].relation_type", "debe ser una lista no vacía")
            continue
        for rt in rel:
            rt_str = str(rt).strip()
            if rt_str not in RELATION_TYPES:
                _err(errors, f"{path}[{idx}].relation_type", f"valor inválido `{rt_str}`")


def _validate_secrets(errors: List[str], items: Any, path: str = "secrets_required") -> None:
    if items is None:
        return
    if not isinstance(items, list):
        _err(errors, path, "debe ser una lista")
        return
    for idx, item in enumerate(items):
        if not isinstance(item, dict):
            _err(errors, f"{path}[{idx}]", "debe ser un objeto")
            continue
        asset_id = str(item.get("asset_id") or item.get("assetId") or "").strip()
        if not asset_id:
            _err(errors, f"{path}[{idx}]", "falta `asset_id`")


def _validate_knowledge_bases(errors: List[str], items: Any, path: str = "knowledge_bases") -> None:
    if items is None:
        return
    if not isinstance(items, list):
        _err(errors, path, "debe ser una lista")
        return
    for idx, item in enumerate(items):
        if isinstance(item, str):
            if not item.strip():
                _err(errors, f"{path}[{idx}]", "identifier vacío")
            continue
        if not isinstance(item, dict):
            _err(errors, f"{path}[{idx}]", "debe ser un objeto o string identifier")
            continue
        identifier = str(item.get("identifier") or item.get("id") or "").strip()
        if not identifier:
            _err(errors, f"{path}[{idx}]", "falta `identifier`")


def _validate_connector(
    errors: List[str],
    connector: Any,
    *,
    allow_endpoint_placeholder: bool,
    path: str = "connector",
) -> None:
    if connector is None:
        _err(errors, path, "campo obligatorio faltante (requerido para assurance)")
        return
    if not isinstance(connector, dict):
        _err(errors, path, "debe ser un objeto YAML")
        return
    endpoint = str(connector.get("endpointUrl") or connector.get("endpoint_url") or "").strip()
    if not endpoint:
        _err(errors, f"{path}.endpointUrl", "campo obligatorio faltante")
    elif allow_endpoint_placeholder and CONNECTOR_PLACEHOLDER in endpoint:
        pass
    elif not endpoint.startswith(("http://", "https://")):
        _err(errors, f"{path}.endpointUrl", "debe empezar con http:// o https://")
    fmt = str(connector.get("format") or connector.get("formatoConector") or "REST_JSON").strip()
    if fmt not in CONNECTOR_FORMATS:
        _err(errors, f"{path}.format", f"valor inválido `{fmt}`")
    auth = str(connector.get("authType") or connector.get("tipoAutenticacion") or "NINGUNA").strip()
    if auth not in CONNECTOR_AUTH:
        _err(errors, f"{path}.authType", f"valor inválido `{auth}`")
    timeout = connector.get("timeoutMs")
    if timeout is not None:
        try:
            timeout_int = int(timeout)
        except (TypeError, ValueError):
            _err(errors, f"{path}.timeoutMs", "debe ser un entero")
        else:
            if timeout_int < 1000 or timeout_int > 120_000:
                _err(errors, f"{path}.timeoutMs", "debe estar entre 1000 y 120000")


def _validate_mcp_servers(errors: List[str], items: Any, path: str = "mcp_servers") -> None:
    if items is None:
        return
    if not isinstance(items, list):
        _err(errors, path, "debe ser una lista")
        return
    for idx, item in enumerate(items):
        if not isinstance(item, dict):
            _err(errors, f"{path}[{idx}]", "debe ser un objeto")
            continue
        mcp_id = str(
            item.get("mcp_id")
            or item.get("mcpId")
            or item.get("identifier")
            or item.get("id")
            or ""
        ).strip()
        if not mcp_id:
            _err(errors, f"{path}[{idx}]", "falta `mcp_id` o `identifier`")
        transport = str(item.get("transport") or "").strip()
        if transport and transport not in MCP_TRANSPORTS:
            _err(errors, f"{path}[{idx}].transport", f"valor inválido `{transport}`")
        backed = item.get("backed_by_assets") or item.get("backedByAssets")
        if backed is not None and not isinstance(backed, list):
            _err(errors, f"{path}[{idx}].backed_by_assets", "debe ser una lista")


def _validate_agent_dependencies(errors: List[str], items: Any, path: str = "agent_dependencies") -> None:
    if items is None:
        return
    if not isinstance(items, list):
        _err(errors, path, "debe ser una lista")
        return
    for idx, item in enumerate(items):
        if not isinstance(item, dict):
            _err(errors, f"{path}[{idx}]", "debe ser un objeto")
            continue
        agent_id = str(item.get("agent_id") or item.get("agentId") or "").strip()
        rel = item.get("relation_type") or item.get("relationType")
        if not agent_id:
            _err(errors, f"{path}[{idx}]", "falta `agent_id`")
        if not isinstance(rel, list) or not rel:
            _err(errors, f"{path}[{idx}].relation_type", "debe ser una lista no vacía")
            continue
        for rt in rel:
            rt_str = str(rt).strip().upper()
            if rt_str not in AGENT_RELATION_TYPES:
                _err(errors, f"{path}[{idx}].relation_type", f"valor inválido `{rt_str}`")


def validate_madre_manifest(
    manifest: Dict[str, Any],
    *,
    allow_connector_placeholder: bool = True,
    require_connector: bool = True,
) -> None:
    """Validate manifest YAML structure (v1.1 / v1.2). Raises ManifestValidationError on failure."""
    errors: List[str] = []

    if not isinstance(manifest, dict):
        raise ManifestValidationError(["root: el manifest debe ser un mapping YAML"])

    mv = str(manifest.get("manifest_version") or manifest.get("manifestVersion") or "").strip()
    if not mv:
        _err(errors, "manifest_version", "campo obligatorio faltante")
    elif mv not in MANIFEST_VERSIONS:
        _err(errors, "manifest_version", f"debe ser una versión soportada ({', '.join(sorted(MANIFEST_VERSIONS))}) (recibido `{mv}`)")

    name = _require_str(errors, manifest, "name", "name")
    if name and len(name) > 128:
        _err(errors, "name", "máximo 128 caracteres")

    version = _require_str(errors, manifest, "agent_version", "agent_version")
    if version is None:
        version = _require_str(errors, manifest, "agentVersion", "agent_version")
    _validate_semver(errors, version, "agent_version")

    agent_types = manifest.get("agent_type") or manifest.get("agentType")
    if not isinstance(agent_types, list) or not agent_types:
        _err(errors, "agent_type", "debe ser una lista con al menos un valor")
    else:
        cleaned_types = list(dict.fromkeys(str(t).strip() for t in agent_types if str(t).strip()))
        if not cleaned_types:
            _err(errors, "agent_type", "requiere al menos un valor")
        for t in cleaned_types:
            if t not in AGENT_TYPES:
                _err(errors, "agent_type", f"valor inválido `{t}`")

    environments = manifest.get("environment")
    if not isinstance(environments, list) or not environments:
        _err(errors, "environment", "debe ser una lista con al menos un valor")
    else:
        cleaned_env = list(dict.fromkeys(str(e).strip() for e in environments if str(e).strip()))
        for e in cleaned_env:
            if e not in ENVIRONMENTS:
                _err(errors, "environment", f"valor inválido `{e}`")

    purpose = _require_str(errors, manifest, "purpose", "purpose")
    if purpose:
        if len(purpose) < 50:
            _err(errors, "purpose", f"requiere al menos 50 caracteres (tiene {len(purpose)})")
        elif len(purpose) > 500:
            _err(errors, "purpose", "máximo 500 caracteres")

    tech_owner = _require_str(errors, manifest, "technical_owner", "technical_owner")
    biz_owner = _require_str(errors, manifest, "business_owner", "business_owner")
    _validate_email(errors, tech_owner, "technical_owner")
    _validate_email(errors, biz_owner, "business_owner")

    target_users = manifest.get("target_users") or manifest.get("targetUsers")
    if not isinstance(target_users, list) or not target_users:
        _err(errors, "target_users", "debe ser una lista con al menos un valor")
    else:
        cleaned_targets = list(dict.fromkeys(str(t).strip() for t in target_users if str(t).strip()))
        for t in cleaned_targets:
            if t not in TARGET_USERS and not t.startswith("custom/"):
                _err(errors, "target_users", f"valor inválido `{t}`")

    customer_facing = _require_bool(errors, manifest, "customer_facing", "customer_facing")
    if customer_facing is None:
        customer_facing = _require_bool(errors, manifest, "customerFacing", "customer_facing")

    agent_origin = _require_str(errors, manifest, "agent_origin", "agent_origin")
    if agent_origin is None:
        agent_origin = _require_str(errors, manifest, "agentOrigin", "agent_origin")
    if agent_origin and agent_origin not in AGENT_ORIGINS:
        _err(errors, "agent_origin", f"debe ser `internal` o `third_party` (recibido `{agent_origin}`)")

    deployment_target = _require_str(errors, manifest, "deployment_target", "deployment_target")
    if deployment_target is None:
        deployment_target = _require_str(errors, manifest, "deploymentTarget", "deployment_target")

    regulated = manifest.get("regulated_context") or manifest.get("regulatedContext")
    if not isinstance(regulated, list) or not regulated:
        _err(errors, "regulated_context", "debe ser una lista con al menos un marco regulatorio")
    else:
        cleaned_reg = list(dict.fromkeys(str(r).strip() for r in regulated if str(r).strip()))
        if not cleaned_reg:
            _err(errors, "regulated_context", "requiere al menos un marco")

    exposure = str(
        manifest.get("network_exposure") or manifest.get("networkExposure") or "private"
    ).strip()
    if exposure not in NETWORK_EXPOSURES:
        _err(errors, "network_exposure", f"valor inválido `{exposure}`")

    if isinstance(target_users, list) and customer_facing is not None:
        has_external = any(str(t).strip() in EXTERNAL_TARGET_USERS for t in target_users)
        if has_external and not customer_facing:
            _err(
                errors,
                "customer_facing",
                "debe ser true cuando target_users incluye customer, partner o public_anonymous",
            )
        if not has_external and customer_facing:
            _err(
                errors,
                "customer_facing",
                "debe ser false cuando target_users es solo interno/automatizado",
            )

    agent_model = str(manifest.get("agent_model") or manifest.get("agentModel") or "").strip()
    framework = str(manifest.get("framework") or "").strip()
    third_party_id = str(
        manifest.get("third_party_identifier") or manifest.get("thirdPartyIdentifier") or ""
    ).strip()
    if agent_origin == "internal":
        if not agent_model:
            _err(errors, "agent_model", "obligatorio para agentes internal")
        if not framework:
            _err(errors, "framework", "obligatorio para agentes internal")
    elif agent_origin == "third_party" and not third_party_id:
        _err(errors, "third_party_identifier", "obligatorio para agentes third_party")

    sp = manifest.get("system_prompt") or manifest.get("systemPrompt")
    if sp is None:
        _err(errors, "system_prompt", "campo obligatorio faltante")
    else:
        _validate_system_prompt(errors, sp)

    caps = manifest.get("declared_capabilities") or manifest.get("declaredCapabilities")
    if caps is None:
        _err(errors, "declared_capabilities", "campo obligatorio faltante")
    else:
        _validate_declared_capabilities(errors, caps)

    _validate_guardrails(
        errors,
        manifest.get("required_guardrails") or manifest.get("requiredGuardrails"),
        "required_guardrails",
    )
    _validate_skills(errors, manifest.get("agent_skills") or manifest.get("agentSkills"))
    _validate_context_assets(
        errors,
        manifest.get("integration_endpoints") or manifest.get("integrationEndpoints"),
        "integration_endpoints",
    )
    _validate_context_assets(
        errors,
        manifest.get("data_stores") or manifest.get("dataStores"),
        "data_stores",
    )
    _validate_secrets(errors, manifest.get("secrets_required") or manifest.get("secretsRequired"))
    _validate_knowledge_bases(
        errors,
        manifest.get("knowledge_bases") or manifest.get("knowledgeBases"),
    )
    _validate_agent_dependencies(
        errors,
        manifest.get("agent_dependencies") or manifest.get("agentDependencies"),
    )
    _validate_mcp_servers(
        errors,
        manifest.get("mcp_servers") or manifest.get("mcpServers"),
    )

    autonomy = str(manifest.get("autonomy_level") or manifest.get("autonomyLevel") or "").strip()
    if not autonomy:
        _err(errors, "autonomy_level", "campo obligatorio faltante")
    elif autonomy not in AUTONOMY_LEVELS:
        _err(errors, "autonomy_level", f"valor inválido `{autonomy}`")

    hitl_raw = manifest.get("human_in_the_loop")
    if hitl_raw is None:
        hitl_raw = manifest.get("humanInTheLoop")
    if hitl_raw is None:
        _err(errors, "human_in_the_loop", "campo obligatorio faltante")
    elif not isinstance(hitl_raw, bool):
        _err(errors, "human_in_the_loop", "debe ser boolean (true/false)")
    elif autonomy == "autonomous" and hitl_raw:
        _err(errors, "human_in_the_loop", "no puede ser true cuando autonomy_level es autonomous")

    if require_connector:
        _validate_connector(
            errors,
            manifest.get("connector"),
            allow_endpoint_placeholder=allow_connector_placeholder,
        )

    if errors:
        raise ManifestValidationError(errors)
