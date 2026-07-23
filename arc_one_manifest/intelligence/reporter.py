"""Reporter — markdown para PR comments y artifacts."""

from __future__ import annotations

from typing import Any, Dict, Optional

from arc_one_manifest.intelligence.models import AuditFinding, AuditReport
from arc_one_manifest.intelligence.platform_report import ReportOutcome
from arc_one_manifest.intelligence.verdict import (
    clean_verdict_line,
    triangulation_found_differences as _triangulation_found_differences,
)

_SEVERITY_EMOJI = {"high": "🔴", "medium": "🟡", "low": "🟢"}

# Las tres patas, en el orden en que se leen: qué comparó cada una y qué te está diciendo.
# El valor de la triangulación es poder distinguirlas — un "hay drift" pelado obliga a la
# persona a re-hacer la investigación que el sistema ya hizo.
_LEG_TITLE = {
    "codigo_vs_manifiesto_repo": "El código hace algo que tu Manifiesto no declara",
    "manifiesto_repo_vs_arc_one": "Tu Manifiesto cambió y no se registró en Arc One",
    "codigo_vs_arc_one": "Lo que Arc One gobierna no es lo que el agente hace",
}

# 🔴 Las patas que parten de SEÑAL DEL CÓDIGO. Un audit de alcance `diff` sólo leyó los
# archivos del cambio, así que "cero diferencias" en estas dos NO es un veredicto sobre el
# agente: es el resultado de no haber mirado. La pata 2 no está acá porque compara dos
# documentos declarados enteros — es independiente del alcance y su ✅ sí vale.
_CODE_DERIVED_LEGS = frozenset({"codigo_vs_manifiesto_repo", "codigo_vs_arc_one"})


def _format_evidence(finding: AuditFinding) -> str:
    if not finding.evidence:
        return "—"
    ev = finding.evidence[0]
    if ev.file:
        return f"`{ev.file}:{ev.line}`"
    return "—"


def report_to_pr_comment(report: AuditReport, outcome: Optional[ReportOutcome] = None) -> str:
    """Markdown para comentario de PR (Manifest Drift Guard).

    ``outcome`` es lo que Arc One **efectivamente registró**. Se pasa para una sola cosa,
    y es importante: este bloque no puede declarar "limpio" cuando la triangulación —que
    es la que materializa Hallazgos— encontró diferencias. Ver la nota abajo.
    """
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
        # La regla vive en `verdict.py`, compartida con el `--format markdown` (WS180):
        # el veredicto no puede depender del formato de salida.
        lines.append(clean_verdict_line(report, outcome))
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


def _leg_lines(leg: Dict[str, Any], scope: str = "") -> list[str]:
    leg_id = str(leg.get("leg") or "")
    titulo = _LEG_TITLE.get(leg_id, leg_id)

    if not leg.get("available"):
        # 🔴 "No se pudo mirar" NO es "está limpio". Decirlo es la mitad del valor.
        motivo = str(leg.get("reason") or "no hubo insumo para esta comparación")
        return [f"- ⚪ **{titulo}** — no se pudo evaluar: {motivo}"]

    filas = leg.get("findings") or []
    if not filas:
        # 🔴 Mismo principio que arriba, un nivel más adentro: un `diff` limpio en una pata
        # que parte del código no puede pintarse como el ✅ de un `full`. Lo que no se miró
        # no es lo que está bien.
        if scope == "diff" and leg_id in _CODE_DERIVED_LEGS:
            return [
                f"- ⚪ **{titulo}** — sin diferencias **en los archivos de este cambio**; "
                "el resto del repositorio no se miró"
            ]
        return [f"- ✅ **{titulo}** — sin diferencias"]

    out = [f"- 🔎 **{titulo}** — {len(filas)} diferencia(s):"]
    for fila in filas[:10]:
        nombre = str(fila.get("inferredId") or fila.get("id") or "—")
        detalle = str(fila.get("section") or fila.get("direction") or "")
        # `unresolved` = el determinístico no pudo identificar QUÉ es. Se muestra igual,
        # pero marcado: es información con menos certeza, no una afirmación fuerte.
        marca = " · _sin resolver contra el catálogo_" if fila.get("matchMode") == "unresolved" else ""
        out.append(f"  - `{nombre}`{f' ({detalle})' if detalle else ''}{marca}")
    if len(filas) > 10:
        out.append(f"  - …y {len(filas) - 10} más")
    return out


def triangulation_to_pr_comment(outcome: Optional[ReportOutcome]) -> str:
    """La sección de Arc One del comment: las 3 patas + qué se archivó y qué no.

    Si el reporte **no** se pudo entregar, esto lo dice fuerte y con el motivo. Es la regla
    que gobierna el módulo: el CI no se rompe, pero *jamás en silencio* — un comment que no
    menciona el problema hace que "todo en orden" y "no pude reportar" se vean igual.
    """
    if outcome is None:
        return ""

    if not outcome.delivered:
        return "\n".join(
            [
                "",
                "### ⚠️ No se pudo reportar a Arc One",
                "",
                f"El audit corrió, pero el resultado **no llegó a Arc One**: {outcome.reason}",
                "",
                "_El CI no se frena por esto (Arc One detecta y avisa, no bloquea), pero "
                "hasta que se resuelva Arc One no está viendo el estado real de este repositorio._",
            ]
        )

    tri = outcome.triangulation or {}
    legs = [leg for leg in (tri.get("legs") or []) if isinstance(leg, dict)]
    reconcile = tri.get("reconcile") or {}
    scope = str(tri.get("scope") or "")

    lines = [
        "",
        "### 🔺 Triangulación de Arc One",
        "",
        f"- Alcance del audit: `{scope}` · Señales evaluadas: {tri.get('signalsEvaluated', 0)}",
    ]

    catalogo = tri.get("catalog") or {}
    if catalogo.get("empty"):
        # Sin catálogo gobernado casi todo cae a `unresolved`: que se vea, en vez de leerse
        # como "no hubo diferencias".
        lines.append(
            "- ⚠️ Este workspace no tiene catálogo gobernado cargado: las señales no se "
            "pueden identificar con precisión."
        )

    lines.append("")
    for leg in legs:
        lines.extend(_leg_lines(leg, scope))

    if scope and not reconcile.get("allowed"):
        lines.extend(
            [
                "",
                "_Este audit miró sólo los archivos del cambio (`diff`), así que **no cierra** "
                "diferencias anteriores: informa lo que ve. Para reconciliar el estado "
                "completo, corré el audit con `--scan-all`._",
            ]
        )

    if outcome.report_id:
        lines.extend(["", f"_Reporte registrado en Arc One: `{outcome.report_id}`_"])
    return "\n".join(lines)
