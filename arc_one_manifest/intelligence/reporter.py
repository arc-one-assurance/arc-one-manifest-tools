"""Reporter — markdown para PR comments y artifacts."""

from __future__ import annotations

from arc_one_manifest.intelligence.models import AuditFinding, AuditReport

_SEVERITY_EMOJI = {"high": "🔴", "medium": "🟡", "low": "🟢"}


def _format_evidence(finding: AuditFinding) -> str:
    if not finding.evidence:
        return "—"
    ev = finding.evidence[0]
    if ev.file:
        return f"`{ev.file}:{ev.line}`"
    return "—"


def report_to_pr_comment(report: AuditReport) -> str:
    """Markdown para comentario de PR (Manifest Drift Guard)."""
    lines = [
        "## ⚠️ Manifest Drift Guard",
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

    lines.extend(
        [
            "| Severidad | Finding | Evidencia |",
            "|-----------|---------|-----------|",
        ]
    )
    for f in report.findings:
        emoji = _SEVERITY_EMOJI.get(f.severity, "⚪")
        lines.append(f"| {emoji} {f.severity} | {f.title} | {_format_evidence(f)} |")

    lines.extend(["", "### Acción sugerida", ""])
    for f in report.findings:
        if f.code != "MANIFEST_STALE":
            continue
        lines.append(f"- Agregar `{f.suggested_catalog_id}` bajo `{f.manifest_section}` en `arc-one.agent.yaml`")
        lines.append(f"  - Bump de `agent_version` antes de mergear")
        break

    lines.append("")
    lines.append("_Generado por `arc-one-manifest audit` · Manifest Intelligence_")
    return "\n".join(lines)
