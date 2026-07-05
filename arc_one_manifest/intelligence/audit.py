"""Orquestador audit — Capa 1 estática (sin LLM)."""

from __future__ import annotations

import json
from pathlib import Path

import yaml

from arc_one_manifest.intelligence.extractors import extract_all_signals
from arc_one_manifest.intelligence.git_diff import (
    DEFAULT_EXCLUDE,
    DEFAULT_INCLUDE,
    changed_files,
    list_repo_files,
    read_file_lines,
)
from arc_one_manifest.intelligence.judge import run_judge
from arc_one_manifest.intelligence.manifest_summary import declared_ids_for_section, summarize_manifest
from arc_one_manifest.intelligence.models import AuditFinding, AuditReport, CodeSignal, ManifestSummary


def _normalize_id(value: str) -> str:
    return value.strip().lower().replace("_", "-")


def _declared_ids_for_signal(signal: CodeSignal, summary: ManifestSummary) -> set[str]:
    """IDs del manifest que satisfacen la señal (incluye secciones relacionadas)."""
    primary = declared_ids_for_section(summary, signal.manifest_section)
    if signal.kind == "data_store":
        primary = primary | declared_ids_for_section(summary, "integration_endpoints")
    elif signal.kind == "integration_endpoint":
        primary = primary | declared_ids_for_section(summary, "data_stores")
    return primary


def _is_declared(signal: CodeSignal, summary: ManifestSummary) -> bool:
    if signal.kind == "secret" and signal.inferred_id == "llm-api-key":
        model = (summary.agent_model or "").lower()
        if model and any(p in model for p in ("anthropic", "openai", "azure", "google", "gemini")):
            return True

    declared = _declared_ids_for_signal(signal, summary)
    inferred = _normalize_id(signal.inferred_id)
    if not declared:
        return False

    normalized_declared = {_normalize_id(d) for d in declared}

    if inferred in normalized_declared:
        return True

    for did in normalized_declared:
        if inferred in did or did in inferred:
            return True

    if signal.kind == "model_hint":
        model = summary.agent_model or ""
        return inferred in _normalize_id(model)

    return False


def _finding_title(signal: CodeSignal) -> str:
    labels = {
        "data_store": "Datastore",
        "integration_endpoint": "Endpoint de integración",
        "mcp_server": "Servidor MCP",
        "secret": "Secreto",
        "model_hint": "Modelo LLM",
        "knowledge_base": "Knowledge base",
    }
    label = labels.get(signal.kind, signal.kind)
    return f"{label} `{signal.inferred_id}` detectado en código, no declarado en manifest"


def static_findings(
    signals: list[CodeSignal],
    summary: ManifestSummary,
    *,
    min_confidence: float,
) -> list[AuditFinding]:
    findings: list[AuditFinding] = []
    seen: set[tuple[str, str]] = set()

    for signal in signals:
        if signal.confidence < min_confidence:
            continue
        if _is_declared(signal, summary):
            continue
        key = (signal.kind, signal.inferred_id)
        if key in seen:
            continue
        seen.add(key)

        severity = "high" if signal.confidence >= 0.85 else "medium"
        findings.append(
            AuditFinding(
                code="MANIFEST_STALE",
                severity=severity,
                confidence=signal.confidence,
                title=_finding_title(signal),
                detail=(
                    f"Se detectó uso de `{signal.inferred_id}` en `{signal.evidence.file}:{signal.evidence.line}` "
                    f"pero no aparece en `{signal.manifest_section}` del manifest."
                ),
                manifest_section=signal.manifest_section,
                suggested_catalog_id=signal.inferred_id,
                evidence=[signal.evidence],
            )
        )
    return findings


def run_audit(
    manifest_path: str | Path,
    *,
    repo: str | Path = ".",
    base_ref: str = "origin/main",
    static_only: bool = True,
    min_confidence: float = 0.85,
    scan_all: bool = False,
    include: tuple[str, ...] = DEFAULT_INCLUDE,
    exclude: tuple[str, ...] = DEFAULT_EXCLUDE,
    judge_client: object | None = None,
) -> AuditReport:
    repo_path = Path(repo).resolve()
    manifest_file = Path(manifest_path).resolve()

    with manifest_file.open(encoding="utf-8") as fh:
        manifest_raw = yaml.safe_load(fh)
    if not isinstance(manifest_raw, dict):
        raise ValueError(f"{manifest_file}: manifest must be a YAML mapping")

    summary = summarize_manifest(manifest_raw)

    if scan_all or base_ref in ("", "HEAD"):
        targets = list_repo_files(repo_path, include, exclude)
    else:
        targets = changed_files(repo_path, base_ref, include, exclude)

    signals: list[CodeSignal] = []
    for file_path in targets:
        if file_path.resolve() == manifest_file:
            continue
        rel = file_path.relative_to(repo_path).as_posix()
        lines = read_file_lines(file_path)
        signals.extend(extract_all_signals(rel, lines))

    findings = static_findings(signals, summary, min_confidence=min_confidence)
    judge_model: str | None = None
    clean = len(findings) == 0

    if not static_only and signals:
        try:
            judge_min = min(min_confidence, 0.7)
            findings, clean, judge_model = run_judge(
                manifest_path=str(manifest_file),
                summary=summary,
                signals=signals,
                client=judge_client,  # type: ignore[arg-type]
                min_confidence=judge_min,
            )
        except ValueError:
            findings = static_findings(signals, summary, min_confidence=min_confidence)
            clean = len(findings) == 0
            static_only = True

    return AuditReport(
        manifest_path=str(manifest_file),
        base_ref=base_ref,
        static_only=static_only,
        manifest_summary=summary,
        code_signals=signals,
        findings=findings,
        clean=clean,
        judge_model=judge_model,
    )


def report_to_json(report: AuditReport) -> str:
    return json.dumps(report.to_dict(), indent=2, ensure_ascii=False)


def report_to_markdown(report: AuditReport) -> str:
    lines = [
        "## Manifest Drift Guard",
        "",
        f"- Manifest: `{report.manifest_path}`",
        f"- Base ref: `{report.base_ref}`",
        f"- Modo: {'estático' if report.static_only else 'LLM judge'}",
        f"- Señales: {len(report.code_signals)} · Findings: {len(report.findings)}",
        "",
    ]
    if report.clean:
        lines.append("✅ Sin drift detectado entre código y manifest.")
        return "\n".join(lines)

    lines.append("| Severidad | Finding | Evidencia |")
    lines.append("|-----------|---------|-----------|")
    for f in report.findings:
        ev = f.evidence[0] if f.evidence else None
        loc = f"{ev.file}:{ev.line}" if ev else "—"
        lines.append(f"| {f.severity} | {f.title} | `{loc}` |")
    lines.append("")
    lines.append("Actualizá `arc-one.agent.yaml` y bump de `agent_version` antes de mergear.")
    return "\n".join(lines)
