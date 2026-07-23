"""La frase que dice "está limpio" — una sola vez, para todos los formatos de salida.

⭐ Por qué existe este módulo (WS180).

*"Limpio" es una afirmación, y sólo vale sobre lo que se miró* (regla 12 · WS179). Esa regla
se implementó en el `--format pr-comment` y **el `--format markdown` quedó afuera**, pintando
`✅ Sin drift` con sólo mirar `report.clean`. No es un detalle: `markdown` es el formato que
usan el workflow de Nova y el reusable `manifest-register.yml` — o sea, **el camino que
reporta y materializa**. El comment del PR era honesto y el resumen del push mentía.

Peor: en ese camino se le concatena abajo la triangulación devuelta por el servidor, así que
con las mismas señales el mismo texto podía decir `✅ Sin drift` arriba y `🔎 2 diferencias`
catorce líneas después.

Las dos reglas que gobiernan la frase, ahora en un solo lugar:

1. **Cuando dos capas responden la misma pregunta con distinta vara, manda la que
   materializa.** El bloque estático local filtra por `--min-confidence` (0.85); la
   triangulación del servidor no filtra nada (allá la confianza elige severidad). Si Arc One
   registró diferencias, el veredicto local no puede decir que no hay.
2. **El ✅ pleno exige haber mirado todo.** Un audit de alcance `diff` leyó los archivos del
   cambio y nada más.
"""

from __future__ import annotations

from typing import Optional

from arc_one_manifest.intelligence.models import AuditReport
from arc_one_manifest.intelligence.platform_report import ReportOutcome


def triangulation_found_differences(outcome: Optional[ReportOutcome]) -> bool:
    """¿Arc One registró diferencias en esta corrida? Sólo cuenta lo que se entregó.

    Un reporte que no se pudo entregar no es evidencia de nada — ni a favor ni en contra.
    """
    if outcome is None or not outcome.delivered:
        return False
    triangulation = outcome.triangulation or {}
    legs = triangulation.get("legs") or []
    for leg in legs:
        if not isinstance(leg, dict) or not leg.get("available"):
            continue
        # `count` y `findings` dicen lo mismo del lado del servidor, pero se leen los dos:
        # si mañana una de las dos claves deja de viajar, el veredicto no se vuelve ciego.
        if int(leg.get("count") or len(leg.get("findings") or [])):
            return True
    return False


def clean_verdict_line(report: AuditReport, outcome: Optional[ReportOutcome] = None) -> str:
    """La línea de veredicto cuando el bloque estático local no encontró nada."""
    if triangulation_found_differences(outcome):
        return (
            "⚪ Sin drift **por encima del umbral de este chequeo**, pero Arc One sí "
            "registró diferencias — están detalladas abajo."
        )
    if report.scan_all:
        return "✅ Sin drift detectado entre código y manifest."
    return (
        "⚪ Sin drift en los archivos de este cambio. El resto del repositorio no se miró "
        "— para revisarlo entero, corré el audit con `--scan-all`."
    )
