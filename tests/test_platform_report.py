"""Reportar el audit a Arc One (Arc Scanner · Fase 2 · Card 5 · doc 16a §5c).

Lo que se blinda acá:

1. **El scope se manda honesto** — ``full`` sólo con ``--scan-all``. Del otro lado ese dato
   decide si el audit puede archivar Hallazgos; mentirlo cerraría como resueltos hallazgos
   de archivos que nadie abrió.
2. **🔴 Fallar no rompe el CI, pero jamás en silencio** — sin credenciales, con 404, con la
   red caída: el audit sigue y el motivo aparece en el comment del PR. Es el patrón del juez
   que caía a estático sin avisar, que es lo que esta fase vino a cerrar.
3. **Una pata que no se pudo evaluar NO se pinta como limpia** — la distinción es la mitad
   del valor de la triangulación.
"""

from __future__ import annotations

import unittest
from unittest.mock import MagicMock, patch

import httpx

from arc_one_manifest.intelligence.models import (
    AuditReport,
    CodeSignal,
    Evidence,
    ManifestSummary,
)
from arc_one_manifest.intelligence.platform_report import (
    ReportOutcome,
    report_audit_to_platform,
    resolve_agent_id,
    resolve_scope,
)
from arc_one_manifest.intelligence.reporter import triangulation_to_pr_comment

BASE = "https://arc-one.example"
TOKEN = "arc1_deadbeefdeadbeef"


def _report() -> AuditReport:
    return AuditReport(
        manifest_path="arc-one.agent.yaml",
        base_ref="origin/main",
        static_only=True,
        manifest_summary=ManifestSummary(
            agent_model="anthropic/claude-sonnet-4-6",
            data_stores={"postgresql"},
            integration_endpoints=set(),
            secrets_required=set(),
            mcp_servers=set(),
            knowledge_bases=set(),
        ),
        code_signals=[
            CodeSignal(
                kind="data_store",
                inferred_id="dynamodb",
                confidence=0.92,
                evidence=Evidence(file="src/x.py", line=7, snippet="boto3"),
                manifest_section="data_stores",
            )
        ],
        findings=[],
        clean=True,
    )


def _response(status: int, payload=None, text: str = "") -> MagicMock:
    res = MagicMock()
    res.status_code = status
    res.text = text
    if payload is None:
        res.json.side_effect = ValueError("no json")
    else:
        res.json.return_value = payload
    return res


def _triangulation(**over) -> dict:
    base = {
        "reportId": "mar_abc123",
        "scope": "full",
        "signalsEvaluated": 1,
        "catalog": {"governedElements": 12, "empty": False},
        "reconcile": {"allowed": True, "legs": ["codigo_vs_arc_one"]},
        "legs": [
            {
                "leg": "codigo_vs_manifiesto_repo",
                "available": False,
                "reason": "el reporte no trajo el resumen del manifiesto del repo",
                "findings": [],
            },
            {"leg": "manifiesto_repo_vs_arc_one", "available": True, "findings": []},
            {
                "leg": "codigo_vs_arc_one",
                "available": True,
                "findings": [
                    {"inferredId": "dynamodb", "section": "dataStores", "matchMode": "catalog"},
                    {"inferredId": "cosa-rara", "section": "dataStores", "matchMode": "unresolved"},
                ],
            },
        ],
    }
    base.update(over)
    return base


# ── El scope se manda honesto ────────────────────────────────────────────────────────────


class ScopeTest(unittest.TestCase):
    def test_scan_all_es_full_y_el_diff_es_diff(self) -> None:
        self.assertEqual(resolve_scope(scan_all=True), "full")
        self.assertEqual(resolve_scope(scan_all=False), "diff")

    def test_el_scope_viaja_tal_cual_en_el_body(self) -> None:
        with patch("arc_one_manifest.intelligence.platform_report.httpx.post") as post:
            post.return_value = _response(201, _triangulation())
            report_audit_to_platform(
                _report(),
                repo=".",
                base_url=BASE,
                token=TOKEN,
                scope="diff",
                agent_id="agt_nova",
            )
        body = post.call_args.kwargs["json"]
        self.assertEqual(body["scope"], "diff")
        self.assertEqual(body["manifestSummary"]["dataStores"], ["postgresql"])
        self.assertEqual(len(body["codeSignals"]), 1)
        url = post.call_args.args[0]
        self.assertTrue(url.endswith("/api/agentes/agt_nova/manifest-intelligence/audit-result"))


# ── 🔴 Fallar no rompe el CI, pero jamás en silencio ─────────────────────────────────────


class NuncaEnSilencioTest(unittest.TestCase):
    def test_sin_credenciales_no_entrega_y_dice_por_que(self) -> None:
        out = report_audit_to_platform(
            _report(), repo=".", base_url="", token="", scope="full"
        )
        self.assertFalse(out.delivered)
        self.assertIn("ARC_ONE_API_BASE_URL", out.reason or "")

    def test_un_404_no_levanta_excepcion(self) -> None:
        with patch("arc_one_manifest.intelligence.platform_report.httpx.post") as post:
            post.return_value = _response(404, {})
            out = report_audit_to_platform(
                _report(), repo=".", base_url=BASE, token=TOKEN, scope="full", agent_id="agt_x"
            )
        self.assertFalse(out.delivered)
        self.assertIn("404", out.reason or "")

    def test_la_red_caida_no_rompe_el_audit(self) -> None:
        """El audit ya corrió: que no se pueda entregar no puede tumbar el CI."""
        with patch(
            "arc_one_manifest.intelligence.platform_report.httpx.post",
            side_effect=httpx.ConnectError("sin red"),
        ):
            out = report_audit_to_platform(
                _report(), repo=".", base_url=BASE, token=TOKEN, scope="full", agent_id="agt_x"
            )
        self.assertFalse(out.delivered)
        self.assertIn("sin red", out.reason or "")

    def test_el_comment_del_pr_grita_el_fallo(self) -> None:
        md = triangulation_to_pr_comment(
            ReportOutcome(delivered=False, reason="faltan credenciales")
        )
        self.assertIn("No se pudo reportar a Arc One", md)
        self.assertIn("faltan credenciales", md)
        self.assertIn("no llegó a Arc One", md)


# ── La triangulación en el comment ───────────────────────────────────────────────────────


class ComentarioTest(unittest.TestCase):
    def setUp(self) -> None:
        self.md = triangulation_to_pr_comment(
            ReportOutcome(
                delivered=True,
                agent_id="agt_nova",
                report_id="mar_abc123",
                triangulation=_triangulation(),
            )
        )

    def test_estan_las_tres_patas_con_su_significado(self) -> None:
        self.assertIn("El código hace algo que tu Manifiesto no declara", self.md)
        self.assertIn("Tu Manifiesto cambió y no se registró en Arc One", self.md)
        self.assertIn("Lo que Arc One gobierna no es lo que el agente hace", self.md)

    def test_una_pata_que_no_corrio_no_se_pinta_como_limpia(self) -> None:
        self.assertIn("no se pudo evaluar", self.md)
        self.assertIn("el reporte no trajo el resumen del manifiesto del repo", self.md)
        # …y la que sí corrió sin diferencias, sí:
        self.assertIn("sin diferencias", self.md)

    def test_lo_no_resuelto_va_marcado(self) -> None:
        """El determinístico no afirma sobre lo que no puede identificar."""
        self.assertIn("cosa-rara", self.md)
        self.assertIn("sin resolver contra el catálogo", self.md)

    def _sin_cerrar(self, motivo: str) -> str:
        """La forma REAL que manda el servidor desde WS180: `reconcile` trae su `reason`."""
        return triangulation_to_pr_comment(
            ReportOutcome(
                delivered=True,
                triangulation=_triangulation(
                    scope="diff",
                    reconcile={"allowed": False, "legs": [], "reason": motivo},
                ),
            )
        )

    def test_un_diff_avisa_que_no_cierra_nada_CON_EL_MOTIVO_DEL_SERVIDOR(self) -> None:
        """🔴 El motivo lo manda el que materializa, no lo adivina el CLI (WS180).

        Antes el CLI escribía siempre "este audit miró sólo los archivos del cambio
        (`diff`)". Ya no es cierto: un `full` también deja de cerrar si no abrió archivos o
        si el recorte de rutas cambió. Inventar el motivo **en el lugar donde se explica por
        qué no se cerró nada** es el mismo pecado que la fase persigue, dado vuelta.
        """
        md = self._sin_cerrar(
            "el audit miró sólo los archivos del cambio (`diff`), así que no cierra "
            "diferencias que ya no se ven — para eso hace falta `--scan-all`"
        )
        self.assertIn("No se cerró ninguna diferencia anterior", md)
        self.assertIn("--scan-all", md)

    def test_el_motivo_de_un_FULL_que_no_cierra_tambien_llega_entero(self) -> None:
        """El contrapeso: el mensaje no puede seguir hablando de `diff` cuando no lo es."""
        md = self._sin_cerrar(
            "el recorte de rutas cambió desde la corrida anterior: esta corrida no cierra nada"
        )
        self.assertIn("el recorte de rutas cambió", md)
        self.assertNotIn("--scan-all", md)

    def test_sin_motivo_no_se_inventa_uno_falso(self) -> None:
        """Si el servidor no lo manda (contrato viejo), se dice lo genérico y verdadero."""
        md = self._sin_cerrar("")
        self.assertIn("no tiene alcance para cerrar diferencias anteriores", md)

    def test_un_diff_limpio_no_es_un_veredicto_sobre_el_agente(self) -> None:
        """🔴 Un `diff` sin señales leyó los archivos del cambio y nada más.

        Pintar ✅ "sin diferencias" en las patas que parten del código convierte *no haber
        mirado* en *estar bien* — el mismo silencio que la fase vino a cerrar, un nivel
        más adentro. La pata 2 compara dos documentos declarados enteros: ésa sí puede
        cerrar en verde con cualquier alcance.
        """
        md = triangulation_to_pr_comment(
            ReportOutcome(
                delivered=True,
                triangulation=_triangulation(
                    scope="diff",
                    signalsEvaluated=0,
                    reconcile={"allowed": False, "legs": []},
                    legs=[
                        {"leg": "codigo_vs_manifiesto_repo", "available": True, "findings": []},
                        {"leg": "manifiesto_repo_vs_arc_one", "available": True, "findings": []},
                        {"leg": "codigo_vs_arc_one", "available": True, "findings": []},
                    ],
                ),
            )
        )
        self.assertEqual(md.count("en los archivos de este cambio"), 2)
        self.assertIn("el resto del repositorio no se miró", md)
        # La pata 2 no depende del alcance: es la única que conserva su ✅.
        self.assertEqual(md.count("✅"), 1)
        self.assertIn("✅ **Tu Manifiesto cambió y no se registró en Arc One**", md)

    def test_el_mismo_estado_con_full_si_cierra_en_verde(self) -> None:
        """El contrapeso: sin el `diff`, las tres patas vuelven a poder decir ✅."""
        md = triangulation_to_pr_comment(
            ReportOutcome(
                delivered=True,
                triangulation=_triangulation(
                    scope="full",
                    signalsEvaluated=0,
                    legs=[
                        {"leg": "codigo_vs_manifiesto_repo", "available": True, "findings": []},
                        {"leg": "manifiesto_repo_vs_arc_one", "available": True, "findings": []},
                        {"leg": "codigo_vs_arc_one", "available": True, "findings": []},
                    ],
                ),
            )
        )
        self.assertEqual(md.count("✅"), 3)
        self.assertNotIn("en los archivos de este cambio", md)

    def test_sin_catalogo_gobernado_se_avisa(self) -> None:
        md = triangulation_to_pr_comment(
            ReportOutcome(
                delivered=True,
                triangulation=_triangulation(catalog={"governedElements": 0, "empty": True}),
            )
        )
        self.assertIn("no tiene catálogo gobernado", md)

    def test_sin_reporte_no_hay_seccion(self) -> None:
        self.assertEqual(triangulation_to_pr_comment(None), "")


# ── A qué agente pertenece este repositorio ──────────────────────────────────────────────


class ResolucionDeAgenteTest(unittest.TestCase):
    def test_el_explicito_gana(self) -> None:
        aid, motivo = resolve_agent_id(
            base_url=BASE, token=TOKEN, debug_sub="", explicit="agt_explicito"
        )
        self.assertEqual(aid, "agt_explicito")
        self.assertIsNone(motivo)

    def test_se_resuelve_por_el_nombre_del_manifiesto(self) -> None:
        """🔴 El insumo es ``name`` — la clave que un Manifiesto MADRE realmente tiene.

        Hasta WS179 esta función buscaba una clave ``nombre_canonico`` en el YAML, y el
        test se la pasaba: fixture y código compartían una forma que **ningún Manifiesto
        real produce**, así que el camino nunca se probó de verdad. Contra un repo sin
        ``agent_id`` en el YAML (audit-lab) el reporte no salía nunca.
        """
        with patch("arc_one_manifest.intelligence.platform_report.httpx.get") as get:
            get.return_value = _response(
                200, [{"id": "agt_nova", "nombreCanonico": "nova-lumen"}]
            )
            aid, motivo = resolve_agent_id(
                base_url=BASE,
                token=TOKEN,
                debug_sub="",
                manifest={"name": "Nova Lumen"},
            )
        self.assertEqual(aid, "agt_nova")
        self.assertIsNone(motivo)

    def test_el_canonico_es_el_mismo_que_deriva_el_gate(self) -> None:
        """La regla vive en un solo lugar: si diverge, el reporte apunta a otro agente."""
        from arc_one_manifest.canonical import canonical_name
        from arc_one_manifest.gate import _canonical_name

        for nombre in ("Nova Lumen", "Audit Lab Agent", "Agente Ñandú  v2", "  Núñez-AI  "):
            self.assertEqual(canonical_name({"name": nombre}), _canonical_name({"name": nombre}))

    def test_sin_pistas_lo_dice_en_cristiano(self) -> None:
        aid, motivo = resolve_agent_id(base_url=BASE, token=TOKEN, debug_sub="", manifest={})
        self.assertIsNone(aid)
        self.assertIn("--agent-id", motivo or "")

    def test_un_agente_no_registrado_no_se_inventa(self) -> None:
        with patch("arc_one_manifest.intelligence.platform_report.httpx.get") as get:
            get.return_value = _response(200, [{"id": "agt_otro", "nombreCanonico": "otro"}])
            aid, motivo = resolve_agent_id(
                base_url=BASE,
                token=TOKEN,
                debug_sub="",
                manifest={"name": "Nova Lumen"},
            )
        self.assertIsNone(aid)
        self.assertIn("no está registrado", motivo or "")


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
