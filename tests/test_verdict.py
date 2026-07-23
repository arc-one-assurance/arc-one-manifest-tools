"""El veredicto de "limpio" no puede depender del formato de salida.

Contexto (WS180): la regla *"limpio" es una afirmación, y sólo vale sobre lo que se miró*
(WS179 · regla 12) se implementó en `--format pr-comment` y el `--format markdown` quedó
afuera, pintando `✅ Sin drift` con sólo mirar `report.clean`. Y `markdown` es el formato del
camino que **reporta y materializa** (el workflow de Nova y `manifest-register.yml`): el
comment del PR era honesto y el resumen del push mentía.

El Q/A en frío también marcó que ese cableado no tenía **ni un test**. Éste es ese test.
"""

from __future__ import annotations

import pytest

from arc_one_manifest.intelligence.audit import report_to_markdown
from arc_one_manifest.intelligence.manifest_summary import summarize_manifest
from arc_one_manifest.intelligence.models import AuditReport
from arc_one_manifest.intelligence.platform_report import ReportOutcome
from arc_one_manifest.intelligence.reporter import report_to_pr_comment


def _report(*, clean: bool = True, scan_all: bool = False) -> AuditReport:
    return AuditReport(
        manifest_path="arc-one.agent.yaml",
        base_ref="origin/main",
        static_only=True,
        # ⚠️ El resumen se pide a `summarize_manifest`, no se construye a mano: el fixture
        # tiene que tener la forma que produce el sistema real (regla 11 · WS179).
        manifest_summary=summarize_manifest({}),
        code_signals=[],
        findings=[],
        clean=clean,
        scan_all=scan_all,
    )


def _outcome_con_diferencias(n: int = 2) -> ReportOutcome:
    """La forma REAL que devuelve el platform: `count` y `findings` viajan los dos."""
    filas = [{"inferredId": f"cosa-{i}", "section": "data_stores"} for i in range(n)]
    return ReportOutcome(
        delivered=True,
        report_id="rep_x",
        triangulation={
            "scope": "full",
            "legs": [{"leg": "codigo_vs_arc_one", "available": True, "count": n, "findings": filas}],
        },
    )


def test_markdown_no_puede_afirmar_limpio_sobre_lo_que_no_miro():
    """Un audit de alcance `diff` leyó los archivos del cambio, no el repositorio."""
    salida = report_to_markdown(_report(scan_all=False))
    assert "✅" not in salida
    assert "no se miró" in salida


def test_markdown_con_scan_all_si_puede_afirmar_limpio():
    """El contrapeso: si miró todo y no encontró nada, el ✅ es legítimo."""
    salida = report_to_markdown(_report(scan_all=True))
    assert "✅ Sin drift detectado" in salida


def test_markdown_no_se_contradice_con_la_triangulacion_que_lleva_abajo():
    """🔴 El defecto original: "✅ Sin drift" arriba y "🔎 2 diferencias" catorce líneas después.

    El bloque estático filtra por `--min-confidence`; la triangulación del servidor no filtra
    nada. Con las mismas señales, uno queda vacío y el otro no. **Manda el que materializa.**
    """
    salida = report_to_markdown(_report(scan_all=True), _outcome_con_diferencias())
    assert "✅ Sin drift detectado" not in salida
    assert "Arc One sí registró diferencias" in salida


@pytest.mark.parametrize("scan_all", [True, False])
@pytest.mark.parametrize("con_diferencias", [True, False])
def test_los_dos_formatos_dan_EL_MISMO_veredicto(scan_all, con_diferencias):
    """El corazón del archivo: la afirmación de limpieza no depende de dónde se imprima.

    Es la misma forma que `test_http_urls.py`: no se comprueba que cada salida "ande", se
    comprueba que **coincidan**. Una regla con dos implementaciones diverge; con una sola y
    dos consumidores, no puede.
    """
    report = _report(scan_all=scan_all)
    outcome = _outcome_con_diferencias() if con_diferencias else None

    md = report_to_markdown(report, outcome)
    pr = report_to_pr_comment(report, outcome)

    # La última línea de cada bloque limpio es el veredicto.
    assert md.strip().splitlines()[-1] == pr.strip().splitlines()[-1]


def test_el_alcance_se_dice_en_el_encabezado_no_solo_en_el_veredicto():
    """`clean` sin alcance es ambiguo. Quien lee el resumen del push tiene que ver cuánto se miró."""
    assert "archivos del cambio" in report_to_markdown(_report(scan_all=False))
    assert "repositorio completo" in report_to_markdown(_report(scan_all=True))


def test_un_reporte_no_entregado_no_es_evidencia_de_nada():
    """Si no se pudo entregar, la triangulación no existe: el veredicto vuelve al alcance.

    Sin esto, un fallo de red se leería como "Arc One no encontró diferencias".
    """
    caido = ReportOutcome(delivered=False, reason="connection refused")
    salida = report_to_markdown(_report(scan_all=True), caido)
    assert "✅ Sin drift detectado" in salida


def test_una_pata_NO_disponible_no_cuenta_como_diferencia_ni_como_limpieza():
    outcome = ReportOutcome(
        delivered=True,
        triangulation={
            "scope": "full",
            "legs": [{"leg": "codigo_vs_arc_one", "available": False, "reason": "sin insumo"}],
        },
    )
    salida = report_to_markdown(_report(scan_all=True), outcome)
    assert "Arc One sí registró diferencias" not in salida


def test_el_veredicto_lee_findings_cuando_no_viene_count():
    """Robustez del contrato: `count` y `findings` dicen lo mismo, pero se leen los dos.

    La versión anterior miraba **sólo** `count`. Si esa clave dejara de viajar, el comment
    volvería a contradecirse y ningún test se enteraría.
    """
    outcome = ReportOutcome(
        delivered=True,
        triangulation={
            "scope": "full",
            "legs": [{"leg": "codigo_vs_arc_one", "available": True, "findings": [{"inferredId": "x"}]}],
        },
    )
    salida = report_to_markdown(_report(scan_all=True), outcome)
    assert "Arc One sí registró diferencias" in salida
