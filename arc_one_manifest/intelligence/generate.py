"""Orquestador generate — bootstrap arc-one.agent.yaml desde repo."""

from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import yaml

from arc_one_manifest.intelligence.catalog import normalize_catalog_id, resolve_signal_catalog_id
from arc_one_manifest.intelligence.extractors import extract_all_signals
from arc_one_manifest.intelligence.generate_models import FieldReport, GenerationReport
from arc_one_manifest.intelligence.generate_synthesizer import synthesize_narrative_fields
from arc_one_manifest.intelligence.git_diff import DEFAULT_EXCLUDE, DEFAULT_INCLUDE, list_repo_files, read_file_lines
from arc_one_manifest.intelligence.models import CodeSignal
from arc_one_manifest.intelligence.profiles import PROFILE_DEFAULTS, detect_profile
from arc_one_manifest.validation import ManifestValidationError, validate_madre_manifest

_DEFAULT_RELATION = ["READ"]
_QUERY_RELATION = ["QUERY"]


def _infer_repo_name(repo: Path) -> str:
    readme = repo / "README.md"
    if readme.is_file():
        for line in readme.read_text(encoding="utf-8", errors="replace").splitlines():
            line = line.strip()
            if line.startswith("#"):
                title = line.lstrip("#").strip()
                if title:
                    return title[:80]
    return repo.name.replace("-", " ").title()[:80]


def _collect_signals(repo: Path) -> list[CodeSignal]:
    signals: list[CodeSignal] = []
    for file_path in list_repo_files(repo, DEFAULT_INCLUDE, DEFAULT_EXCLUDE):
        rel = file_path.relative_to(repo).as_posix()
        if rel == "arc-one.agent.yaml":
            continue
        lines = read_file_lines(file_path)
        signals.extend(extract_all_signals(rel, lines))
    return signals


def _asset_row(asset_id: str, *, relation: list[str] | None = None) -> dict[str, Any]:
    return {"asset_id": asset_id, "relation_type": relation or _DEFAULT_RELATION}


def _mcp_row(mcp_id: str) -> dict[str, Any]:
    return {"mcp_id": mcp_id}


def _signals_to_manifest_sections(
    signals: list[CodeSignal],
    fields: dict[str, FieldReport],
) -> tuple[dict[str, list[dict[str, Any]]], str, float]:
    data_stores: dict[str, dict[str, Any]] = {}
    integrations: dict[str, dict[str, Any]] = {}
    mcps: dict[str, dict[str, Any]] = {}
    secrets: dict[str, dict[str, Any]] = {}
    agent_model: str | None = None
    confidences: list[float] = []

    for signal in signals:
        if signal.confidence < 0.65:
            continue
        canonical, _known = resolve_signal_catalog_id(signal.inferred_id, signal.manifest_section)
        ev = f"{signal.evidence.file}:{signal.evidence.line}"
        confidences.append(signal.confidence)

        if signal.kind == "data_store":
            rel = _QUERY_RELATION if canonical == "pinecone" else _DEFAULT_RELATION
            data_stores[canonical] = _asset_row(canonical, relation=rel)
            fields[f"data_stores.{canonical}"] = FieldReport(
                value=canonical, confidence=signal.confidence, evidence=ev, status="inferred"
            )
        elif signal.kind == "integration_endpoint":
            integrations[canonical] = _asset_row(canonical)
            fields[f"integration_endpoints.{canonical}"] = FieldReport(
                value=canonical, confidence=signal.confidence, evidence=ev, status="inferred"
            )
        elif signal.kind == "mcp_server":
            mcps[canonical] = _mcp_row(canonical)
            fields[f"mcp_servers.{canonical}"] = FieldReport(
                value=canonical, confidence=signal.confidence, evidence=ev, status="inferred"
            )
        elif signal.kind == "secret" and signal.inferred_id != "llm-api-key":
            secrets[canonical] = _asset_row(canonical)
            fields[f"secrets_required.{canonical}"] = FieldReport(
                value=canonical, confidence=signal.confidence, evidence=ev, status="inferred"
            )
        elif signal.kind == "model_hint":
            model = normalize_catalog_id(signal.inferred_id)
            if "/" not in model:
                model = f"{model}/claude-sonnet-4-7" if "anthropic" in model else f"{model}/gpt-4o"
            agent_model = model
            fields["agent_model"] = FieldReport(
                value=model, confidence=signal.confidence, evidence=ev, status="inferred"
            )

    sections = {
        "data_stores": list(data_stores.values()),
        "integration_endpoints": list(integrations.values()),
        "mcp_servers": list(mcps.values()),
        "secrets_required": list(secrets.values()),
    }
    avg_conf = sum(confidences) / len(confidences) if confidences else 0.35
    return sections, agent_model or "anthropic/claude-sonnet-4-7", avg_conf


def _build_manifest(
    repo: Path,
    profile: str,
    signals: list[CodeSignal],
) -> tuple[dict[str, Any], dict[str, FieldReport], float]:
    fields: dict[str, FieldReport] = {}
    sections, agent_model, signal_conf = _signals_to_manifest_sections(signals, fields)
    defaults = PROFILE_DEFAULTS.get(profile, PROFILE_DEFAULTS["generic"])
    name = _infer_repo_name(repo)

    fields["name"] = FieldReport(value=name, confidence=0.6 if name != repo.name else 0.4, evidence="README.md or repo name")
    fields["agent_model"] = fields.get(
        "agent_model",
        FieldReport(value=agent_model, confidence=0.5, evidence="default", status="inferred"),
    )

    manifest: dict[str, Any] = {
        "manifest_version": "1.3",
        "name": name,
        "agent_version": "0.1.0",
        "agent_type": ["conversational"],
        "environment": ["non-productive"],
        "purpose": "TODO — describir propósito operativo del agente (mín. 50 caracteres).",
        "technical_owner": "TODO",
        "business_owner": "TODO",
        "target_users": ["internal_employee"],
        "customer_facing": False,
        "agent_origin": "internal",
        "agent_model": fields["agent_model"].value,
        "framework": defaults["framework"],
        "deployment_target": defaults["deployment_target"],
        "regulated_context": ["eu-ai-act/eu"],
        "network_exposure": "private",
        "system_prompt": {
            "transparency_level": "full",
            "content": "TODO — system prompt del agente.",
            "notes": "Generado por arc-one-manifest generate",
        },
        "declared_capabilities": {
            "transparency_level": "full",
            "capabilities": [{"capability": "communication.respond-to-user"}],
        },
        "required_guardrails": [
            {
                "identifier": "arc-one/pii-output-redaction-v1",
                "provider": "custom",
                "category": "pii",
            }
        ],
        "agent_skills": [{"id": "general-assistance", "category": "customer-support"}],
        "autonomy_level": "supervised",
        "human_in_the_loop": True,
        "data_stores": sections["data_stores"],
        "integration_endpoints": sections["integration_endpoints"],
        "mcp_servers": sections["mcp_servers"],
        "knowledge_bases": [],
        "connector": {
            "name": f"{name} connector",
            "endpointUrl": "https://TODO.example.com/converse",
            "format": "REST_JSON",
            "authType": "NINGUNA",
            "promptField": "prompt",
            "responseField": "response",
            "timeoutMs": 30000,
        },
    }

    if sections["secrets_required"]:
        manifest["secrets_required"] = sections["secrets_required"]

    todo_fields = (
        "purpose",
        "technical_owner",
        "business_owner",
        "system_prompt",
        "connector",
    )
    for key in todo_fields:
        fields[key] = FieldReport(value=None, confidence=0.0, status="TODO")

    overall = min(0.95, (signal_conf * 0.6) + (0.25 if sections["data_stores"] else 0.1) + 0.05)
    return manifest, fields, overall


_ACCOUNT_ENV_KEYS = (
    "GOOGLE_CLOUD_PROJECT",
    "GCLOUD_PROJECT",
    "GCP_PROJECT",
    "GCP_PROJECT_ID",
    "AWS_ACCOUNT_ID",
)
# Valores que son el placeholder del ejemplo, no la cuenta real del cliente.
_PLACEHOLDER_RE = re.compile(
    r"^(|x+|your[-_].*|my[-_].*|<.*>|\$\{.*\}|change[-_]?me|todo|tbd|example.*|.*-project|123456789012)$",
    re.IGNORECASE,
)


def _suggest_account(repo: Path) -> str | None:
    """Una cuenta de nube visible en el repo, si el repo la revela de verdad.

    `generate` NO puede saber la cuenta (rara vez está en el código) y **jamás la
    inventa**: si no hay una lectura inequívoca, el bloque sale con placeholders y el
    cliente la completa. Un `account` fabricado haría que el readiness reportara
    `sin_conexion` sobre una cuenta que nadie declaró.
    """
    for file_path in list_repo_files(repo, DEFAULT_INCLUDE, DEFAULT_EXCLUDE):
        rel = file_path.relative_to(repo).as_posix().lower()
        if "env" not in rel:
            continue
        for raw in read_file_lines(file_path):
            line = raw.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, _, value = line.partition("=")
            if key.strip().upper() not in _ACCOUNT_ENV_KEYS:
                continue
            value = value.strip().strip("\"'")
            if value and not _PLACEHOLDER_RE.match(value):
                return value
    return None


def _infra_binding_stanza(account: str | None) -> str:
    """El bloque `infra_binding` comentado, para que el cliente lo descubra y lo complete.

    Va como texto (no como clave del dict) a propósito: comentado no se registra nada
    hasta que el cliente lo revise, y el YAML dumpeado no puede llevar comentarios.
    Mismo copy que la plantilla que sirve el platform — se escribe una sola vez.
    """
    cuenta = f'"{account}"' if account else '"tu-cuenta"'
    sugerido = "  # ← detectada en el repo, confirmala" if account else ""
    return (
        "\n"
        "# --- Infraestructura vinculada (opcional) -----------------------------------\n"
        "# En qué cuenta de nube vive el agente y qué recursos de esa cuenta son suyos.\n"
        "# No lleva credenciales: esas se cargan una sola vez en Conectividad → Nubes.\n"
        "# No cambia la criticidad del agente — cambia la precisión con la que Arc One\n"
        "# valida lo declarado contra lo que existe de verdad en tu nube. Sin este\n"
        "# bloque, los recursos se identifican por similitud de nombre.\n"
        "#\n"
        "# infra_binding:\n"
        f"#   - account: {cuenta}{sugerido}\n"
        "#     scope:\n"
        "#       all: true                 # la cuenta es dedicada a este agente…\n"
        "#       # …o, si la comparte con otros, declarar el recorte en vez de `all`:\n"
        "#       # resource_prefixes: [mi-agente-]\n"
        "#       # regions: [europe-west1]\n"
    )


def _manifest_yaml_with_header(
    manifest: dict[str, Any],
    *,
    confidence: float,
    profile: str,
    infra_account: str | None = None,
) -> str:
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    header = (
        f"# GENERATED by arc-one-manifest generate · {today}\n"
        f"# Confidence: {confidence:.0%} · profile: {profile}\n"
        f"# Revisar campos TODO antes de registrar · Report: manifest-generation-report.json\n"
        "#\n"
    )
    body = yaml.safe_dump(manifest, sort_keys=False, allow_unicode=True)
    return header + body + _infra_binding_stanza(infra_account)


def run_generate(
    repo: str | Path,
    *,
    profile: str = "auto",
    skip_llm: bool = False,
) -> tuple[dict[str, Any], GenerationReport]:
    repo_path = Path(repo).resolve()
    if not repo_path.is_dir():
        raise ValueError(f"{repo_path}: not a directory")

    detected = detect_profile(repo_path, profile)
    signals = _collect_signals(repo_path)
    manifest, fields, confidence = _build_manifest(repo_path, detected, signals)

    if not skip_llm:
        signal_labels = [f"{s.kind}:{s.inferred_id}" for s in signals[:30]]
        patches, synth_fields = synthesize_narrative_fields(
            repo_path, profile=detected, manifest=manifest, signals_summary=signal_labels
        )
        manifest.update({k: v for k, v in patches.items() if k != "system_prompt"})
        if "system_prompt" in patches:
            manifest["system_prompt"] = patches["system_prompt"]
        fields.update(synth_fields)
        if synth_fields:
            confidence = min(0.95, confidence + 0.1)

    validation: dict[str, Any] = {"ok": False, "errors": []}
    try:
        validate_madre_manifest(manifest, allow_connector_placeholder=True)
        validation["ok"] = True
    except ManifestValidationError as exc:
        validation["errors"] = str(exc).splitlines()

    report = GenerationReport(
        generated_at=datetime.now(timezone.utc).isoformat(),
        profile=detected,
        confidence=confidence,
        fields=fields,
        validation=validation,
        infra_account_suggestion=_suggest_account(repo_path),
    )
    return manifest, report


def write_generate_outputs(
    manifest: dict[str, Any],
    report: GenerationReport,
    *,
    output: Path,
    report_path: Path,
) -> None:
    yaml_text = _manifest_yaml_with_header(
        manifest,
        confidence=report.confidence,
        profile=report.profile,
        infra_account=report.infra_account_suggestion,
    )
    output.write_text(yaml_text, encoding="utf-8")
    report.manifest_path = str(output)
    report.report_path = str(report_path)
    report_path.write_text(json.dumps(report.to_dict(), indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def report_to_json(report: GenerationReport) -> str:
    return json.dumps(report.to_dict(), indent=2, ensure_ascii=False)
