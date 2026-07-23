"""El nombre del secreto se guarda, no se tira (WS179).

El bug que estos tests fijan: los extractores matcheaban `SECRET|TOKEN|PASSWORD` en la
línea y emitían la constante ``runtime-secret``, **con el nombre escrito adelante**. El
Hallazgo resultante —*"el código usa el secreto «runtime-secret»"*— no lo puede accionar
nadie: no existe nada que declarar con ese nombre.
"""
from __future__ import annotations

import unittest
from pathlib import Path

from arc_one_manifest.intelligence.audit import run_audit
from arc_one_manifest.intelligence.git_diff import DEFAULT_EXCLUDE

from arc_one_manifest.intelligence.extractors.env_names import (
    LLM_API_KEY_ID,
    UNIDENTIFIED_SECRET_ID,
    secret_id_from_line,
)
from arc_one_manifest.intelligence.extractors.python_ast import extract_python_ast_signals
from arc_one_manifest.intelligence.extractors.typescript_env import extract_typescript_signals


class SecretIdTest(unittest.TestCase):
    def test_captura_las_formas_de_leer_el_entorno(self) -> None:
        casos = {
            'const token = process.env.CRM_API_SECRET;': "crm-api-secret",
            'process.env["PAYMENTS_TOKEN"]': "payments-token",
            'token=os.environ.get("ARC_ONE_BEARER_TOKEN", "")': "arc-one-bearer-token",
            'os.environ["DB_PASSWORD"]': "db-password",
            'os.getenv("STRIPE_SECRET")': "stripe-secret",
        }
        for linea, esperado in casos.items():
            self.assertEqual(secret_id_from_line(linea), esperado, linea)

    def test_la_key_del_proveedor_colapsa_al_id_que_ya_se_trata_aparte(self) -> None:
        """No es un secreto suelto: está implícita en el `agent_model` declarado.

        Si capturáramos `anthropic-api-key` a secas, `_is_declared` (CLI) y el
        `SignalMatch` (platform) dejarían de reconocerla y volvería a reportarse como
        secreto sin declarar en todo agente que use un modelo de un proveedor.
        """
        for linea in (
            "process.env.ANTHROPIC_API_KEY",
            'os.environ.get("OPENAI_API_KEY")',
            'os.getenv("AZURE_OPENAI_API_KEY")',
        ):
            self.assertEqual(secret_id_from_line(linea), LLM_API_KEY_ID, linea)

    def test_lo_que_no_se_puede_capturar_devuelve_vacio(self) -> None:
        """El caso honesto: hay un secreto y no se sabe cuál. Es el hueco del juez LLM."""
        self.assertEqual(secret_id_from_line("SECRET = load_from_vault()"), "")
        self.assertEqual(secret_id_from_line("token = get_token()"), "")


class ExtractorTest(unittest.TestCase):
    def test_typescript_guarda_el_nombre(self) -> None:
        señales = extract_typescript_signals(
            "src/lib/crm.ts", ["const token = process.env.CRM_API_SECRET;"]
        )
        self.assertEqual(len(señales), 1)
        self.assertEqual(señales[0].inferred_id, "crm-api-secret")

    def test_python_guarda_el_nombre(self) -> None:
        señales = extract_python_ast_signals(
            "scripts/x.py", ['token = os.environ.get("PAYMENTS_API_TOKEN", "")']
        )
        secretos = [s for s in señales if s.kind == "secret"]
        self.assertEqual(len(secretos), 1)
        self.assertEqual(secretos[0].inferred_id, "payments-api-token")

    def test_sin_nombre_capturable_queda_el_id_de_no_se_cual_es(self) -> None:
        señales = extract_python_ast_signals("scripts/x.py", ["os.environ.update(SECRET_MAP)"])
        secretos = [s for s in señales if s.kind == "secret"]
        self.assertEqual(len(secretos), 1)
        self.assertEqual(secretos[0].inferred_id, UNIDENTIFIED_SECRET_ID)
        # 🔴 Y con MENOS certeza que el identificado: es el dato que la Fase 2bis usa para
        # decidir a qué mandarle el juez.
        self.assertLess(secretos[0].confidence, 0.8)

    def test_el_identificado_no_cruza_el_piso_del_bloque_estatico(self) -> None:
        """Contrapeso: capturar el nombre no puede volverse un finding de severidad alta.

        Sin esto, el cambio inundaría el comment de todos los clientes con secretos que
        antes no aparecían — y un secreto nunca resuelve contra el catálogo gobernado,
        así que afirmarlo fuerte es justo lo que la precisión honesta prohíbe.
        """
        señales = extract_typescript_signals(
            "src/lib/crm.ts", ["const token = process.env.CRM_API_SECRET;"]
        )
        self.assertLess(señales[0].confidence, 0.85)


if __name__ == "__main__":  # pragma: no cover
    unittest.main()


class ExcludeFlagTest(unittest.TestCase):
    """`--exclude`: código que está en el repo pero no es del agente.

    El caso que lo motivó (WS179): Nova tiene en `scripts/` su propia integración CON Arc
    One, que lee `ARC_ONE_BEARER_TOKEN`. Escanearla hacía que Arc One le reportara a Nova
    **sus propios tokens** como secretos sin declarar. El default sigue incluyendo
    `scripts/**` —donde suele revelar comportamiento real— y el recorte es del cliente.
    """

    FIXTURE = Path(__file__).parent / "fixtures" / "audit_scenarios" / "mcp-drift"

    def test_sin_exclude_lo_ve(self) -> None:
        report = run_audit(
            self.FIXTURE / "arc-one.agent.yaml",
            repo=self.FIXTURE,
            scan_all=True,
            static_only=True,
        )
        self.assertFalse(report.clean)

    def test_con_exclude_no_lo_mira(self) -> None:
        report = run_audit(
            self.FIXTURE / "arc-one.agent.yaml",
            repo=self.FIXTURE,
            scan_all=True,
            static_only=True,
            exclude=DEFAULT_EXCLUDE + ("src/**",),
        )
        self.assertTrue(report.clean)
        self.assertEqual(report.code_signals, [])
