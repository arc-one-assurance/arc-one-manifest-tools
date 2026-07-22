"""Tests manifest bootstrap — generate."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from arc_one_manifest.intelligence.generate import run_generate, write_generate_outputs
from arc_one_manifest.intelligence.profiles import detect_profile


class GenerateTest(unittest.TestCase):
    def test_detect_profile_generic(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "src").mkdir()
            (root / "src" / "app.py").write_text("print('hi')\n", encoding="utf-8")
            self.assertEqual(detect_profile(root), "generic")

    def test_generate_from_banking_like_repo(self) -> None:
        fixtures = Path(__file__).parent / "fixtures" / "audit_scenarios" / "clean-banking"
        manifest, report = run_generate(fixtures, profile="generic")
        ids = {row["asset_id"] for row in manifest.get("data_stores") or []}
        self.assertIn("postgresql", ids)
        self.assertIn("pinecone", ids)
        self.assertEqual(report.profile, "generic")
        self.assertFalse(report.validation.get("ok"))

    def test_generate_dry_run_has_todo_fields(self) -> None:
        fixtures = Path(__file__).parent / "fixtures" / "audit_scenarios" / "clean-banking"
        manifest, _report = run_generate(fixtures)
        self.assertIn("TODO", manifest["purpose"])
        self.assertEqual(manifest["technical_owner"], "TODO")

    def test_generate_declara_manifest_version_1_3(self) -> None:
        fixtures = Path(__file__).parent / "fixtures" / "audit_scenarios" / "clean-banking"
        manifest, _report = run_generate(fixtures, profile="generic")
        self.assertEqual(manifest["manifest_version"], "1.3")

    def test_el_yaml_generado_trae_el_bloque_infra_binding_comentado(self) -> None:
        """Descubribilidad: el bloque tiene que llegar al archivo que la gente edita.

        Va COMENTADO: `generate` no puede saber la cuenta, así que propone y el cliente
        confirma — nada se registra hasta que él lo descomente.
        """
        fixtures = Path(__file__).parent / "fixtures" / "audit_scenarios" / "clean-banking"
        manifest, report = run_generate(fixtures, profile="generic")
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / "arc-one.agent.yaml"
            write_generate_outputs(
                manifest, report, output=out, report_path=Path(tmp) / "report.json"
            )
            texto = out.read_text(encoding="utf-8")
        self.assertIn("# infra_binding:", texto)
        self.assertIn("#       all: true", texto)
        # Comentado = el manifiesto sigue siendo válido sin que nadie lo toque.
        self.assertNotIn("\ninfra_binding:", texto)

    def test_la_cuenta_se_sugiere_solo_si_el_repo_la_revela(self) -> None:
        """Nunca inventa: sin lectura inequívoca, placeholder. Un account fabricado
        haría que el readiness reporte `sin_conexion` sobre una cuenta que nadie declaró."""
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "src").mkdir()
            (root / "src" / "app.py").write_text("print('hi')\n", encoding="utf-8")
            (root / ".env.example").write_text(
                "GOOGLE_CLOUD_PROJECT=acme-nova-prod\nOPENAI_API_KEY=sk-xxx\n", encoding="utf-8"
            )
            _manifest, report = run_generate(root, profile="generic", skip_llm=True)
            self.assertEqual(report.infra_account_suggestion, "acme-nova-prod")

    def test_un_placeholder_no_cuenta_como_cuenta(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "src").mkdir()
            (root / "src" / "app.py").write_text("print('hi')\n", encoding="utf-8")
            (root / ".env.example").write_text(
                "GOOGLE_CLOUD_PROJECT=your-project-id\n", encoding="utf-8"
            )
            _manifest, report = run_generate(root, profile="generic", skip_llm=True)
            self.assertIsNone(report.infra_account_suggestion)


if __name__ == "__main__":
    unittest.main()
