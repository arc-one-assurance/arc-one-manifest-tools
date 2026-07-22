"""`infra_binding` (MADRE v1.3) — validación estructural + mapeo al payload de registro."""
from __future__ import annotations

import unittest

from arc_one_manifest.gate import _suggest_bump_level  # noqa: F401
from arc_one_manifest.register import manifest_to_registro_payload
from arc_one_manifest.validation.madre_v11 import (
    ManifestValidationError,
    validate_madre_manifest,
)


BASE_MANIFEST = {
    "manifest_version": "1.3",
    "name": "Nova",
    "agent_version": "1.0.0",
    "agent_type": ["conversational"],
    "environment": ["non-productive"],
    "purpose": "Agente de prueba con un proposito suficientemente largo para validar.",
    "technical_owner": "tech@example.com",
    "business_owner": "biz@example.com",
    "target_users": ["internal_employee"],
    "customer_facing": False,
    "agent_origin": "internal",
    "agent_model": "claude-sonnet-5",
    "framework": "custom",
    "deployment_target": "cloud-run/google",
    "regulated_context": ["eu-ai-act/eu"],
    "network_exposure": "private",
    "system_prompt": {"content": "Sos un agente de prueba."},
    "declared_capabilities": {"capabilities": [{"capability": "responder"}]},
    "autonomy_level": "supervised",
    "human_in_the_loop": True,
    "connector": {
        "endpointUrl": "https://example.com/chat",
        "format": "REST_JSON",
        "authType": "NINGUNA",
    },
}


def manifest_with(binding) -> dict:
    m = dict(BASE_MANIFEST)
    if binding is not None:
        m["infra_binding"] = binding
    return m


def errors_for(binding) -> list:
    try:
        validate_madre_manifest(manifest_with(binding))
    except ManifestValidationError as exc:
        return exc.errors
    return []


class InfraBindingValidationTest(unittest.TestCase):
    def test_manifest_sin_infra_binding_sigue_siendo_valido(self) -> None:
        """El bloque es opcional: los agentes ya registrados no se rompen."""
        self.assertEqual(errors_for(None), [])

    def test_version_1_2_sigue_soportada(self) -> None:
        m = manifest_with(None)
        m["manifest_version"] = "1.2"
        validate_madre_manifest(m)

    def test_binding_completo_es_valido(self) -> None:
        self.assertEqual(
            errors_for(
                [
                    {
                        "account": "acme-prod",
                        "scope": {
                            "resource_prefixes": ["nova-"],
                            "regions": ["europe-west1"],
                            "labels": {"app": "nova"},
                        },
                    },
                    {
                        "account": "112233445566",
                        "scope": {"resource_prefixes": ["nova-events-"]},
                    },
                ]
            ),
            [],
        )

    def test_lista_vacia_se_rechaza(self) -> None:
        errors = errors_for([])
        self.assertTrue(any("infra_binding" in e and "omitirse" in e for e in errors), errors)

    def test_no_lista_se_rechaza(self) -> None:
        errors = errors_for({"account": "acme-prod", "scope": {"regions": ["europe-west1"]}})
        self.assertTrue(any(e.startswith("infra_binding:") for e in errors), errors)

    def test_account_duplicado_se_rechaza(self) -> None:
        errors = errors_for(
            [
                {"account": "acme-prod", "scope": {"resource_prefixes": ["nova-"]}},
                {"account": "acme-prod", "scope": {"resource_prefixes": ["abi-"]}},
            ]
        )
        self.assertTrue(any("duplicada" in e for e in errors), errors)

    def test_account_faltante_se_rechaza(self) -> None:
        errors = errors_for([{"scope": {"resource_prefixes": ["nova-"]}}])
        self.assertTrue(any("account" in e for e in errors), errors)

    def test_scope_faltante_se_rechaza(self) -> None:
        errors = errors_for([{"account": "acme-prod"}])
        self.assertTrue(any("scope" in e for e in errors), errors)

    def test_scope_vacio_se_rechaza(self) -> None:
        errors = errors_for([{"account": "acme-prod", "scope": {}}])
        self.assertTrue(any("resource_prefixes" in e or "regions" in e for e in errors), errors)

    def test_scope_solo_labels_se_rechaza_porque_no_recorta(self) -> None:
        """`labels` se acepta en el schema pero todavía no filtra: solo-labels no delimita nada."""
        errors = errors_for([{"account": "acme-prod", "scope": {"labels": {"app": "nova"}}}])
        self.assertTrue(any("labels" in e for e in errors), errors)

    def test_prefijo_no_string_se_rechaza(self) -> None:
        errors = errors_for([{"account": "acme-prod", "scope": {"resource_prefixes": [42]}}])
        self.assertTrue(any("resource_prefixes[0]" in e for e in errors), errors)

    def test_labels_no_mapping_se_rechaza(self) -> None:
        errors = errors_for(
            [
                {
                    "account": "acme-prod",
                    "scope": {"regions": ["europe-west1"], "labels": ["app=nova"]},
                }
            ]
        )
        self.assertTrue(any("labels" in e for e in errors), errors)


class InfraBindingPayloadTest(unittest.TestCase):
    def test_mapea_a_identidad_infra_binding_en_camel_case(self) -> None:
        payload = manifest_to_registro_payload(
            manifest_with(
                [
                    {
                        "account": "acme-prod",
                        "scope": {
                            "resource_prefixes": ["nova-"],
                            "regions": ["europe-west1"],
                            "labels": {"app": "nova"},
                        },
                    }
                ]
            )
        )
        self.assertEqual(
            payload["identidad"]["infraBinding"],
            [
                {
                    "account": "acme-prod",
                    "scope": {
                        "resourcePrefixes": ["nova-"],
                        "regions": ["europe-west1"],
                        "labels": {"app": "nova"},
                    },
                }
            ],
        )

    def test_sin_binding_el_payload_no_trae_la_clave(self) -> None:
        """Si el repo no declara nada, el payload no manda el campo (evita drift falso)."""
        payload = manifest_to_registro_payload(manifest_with(None))
        self.assertNotIn("infraBinding", payload["identidad"])

    def test_propaga_manifest_version(self) -> None:
        payload = manifest_to_registro_payload(manifest_with(None))
        self.assertEqual(payload["identidad"]["manifestVersion"], "1.3")

    def test_multi_nube_conserva_el_orden(self) -> None:
        payload = manifest_to_registro_payload(
            manifest_with(
                [
                    {"account": "acme-prod", "scope": {"resource_prefixes": ["nova-"]}},
                    {"account": "112233445566", "scope": {"regions": ["eu-west-1"]}},
                ]
            )
        )
        self.assertEqual(
            [b["account"] for b in payload["identidad"]["infraBinding"]],
            ["acme-prod", "112233445566"],
        )


class InfraBindingBumpSuggestionTest(unittest.TestCase):
    """La regla acordada: mudarse es minor, reacomodar el scope es patch."""

    def _registered(self, **overrides) -> dict:
        base = {
            "deployment_target": "cloud-run/google",
            "infra_binding": [{"account": "acme-prod", "scope": {"resource_prefixes": ["nova-"]}}],
        }
        base.update(overrides)
        return base

    def test_cambiar_de_cuenta_sugiere_minor(self) -> None:
        repo = self._registered(
            infra_binding=[{"account": "acme-dev", "scope": {"resource_prefixes": ["nova-"]}}]
        )
        self.assertEqual(_suggest_bump_level(repo, self._registered()), "minor")

    def test_agregar_una_segunda_nube_sugiere_minor(self) -> None:
        repo = self._registered(
            infra_binding=[
                {"account": "acme-prod", "scope": {"resource_prefixes": ["nova-"]}},
                {"account": "112233445566", "scope": {"regions": ["eu-west-1"]}},
            ]
        )
        self.assertEqual(_suggest_bump_level(repo, self._registered()), "minor")

    def test_cambiar_de_plataforma_sugiere_minor(self) -> None:
        repo = self._registered(deployment_target="lambda/aws")
        self.assertEqual(_suggest_bump_level(repo, self._registered()), "minor")

    def test_reacomodar_el_scope_en_la_misma_cuenta_sugiere_patch(self) -> None:
        repo = self._registered(
            infra_binding=[
                {
                    "account": "acme-prod",
                    "scope": {"resource_prefixes": ["nova-", "nova-events-"]},
                }
            ]
        )
        self.assertEqual(_suggest_bump_level(repo, self._registered()), "patch")

    def test_sin_binding_en_ninguno_de_los_dos_lados_sigue_siendo_patch(self) -> None:
        self.assertEqual(_suggest_bump_level({}, {}), "patch")


if __name__ == "__main__":
    unittest.main()


class GateNormalizationTest(unittest.TestCase):
    """El salto de línea final de YAML no puede contar como cambio material.

    Los bloques `|` de YAML agregan un `\n` al final; el hash de drift lo normaliza,
    pero la sugerencia de bump no lo hacía → sugería `minor` siempre, en cualquier
    manifiesto real, y la regla de infra nunca llegaba a ejecutarse.
    """

    def test_un_salto_de_linea_final_no_es_cambio_material(self) -> None:
        registered = {
            "purpose": "Un proposito cualquiera.",
            "system_prompt": {"content": "Sos un agente."},
            "deployment_target": "cloud-run/google",
            "infra_binding": [{"account": "acme", "scope": {"resource_prefixes": ["nova-"]}}],
        }
        repo = {
            **registered,
            "purpose": "Un proposito cualquiera.\n",
            "system_prompt": {"content": "Sos un agente.\n"},
        }
        self.assertEqual(_suggest_bump_level(repo, registered), "patch")

    def test_con_el_ruido_de_yaml_la_regla_de_infra_sigue_valiendo(self) -> None:
        registered = {
            "purpose": "Un proposito cualquiera.",
            "deployment_target": "cloud-run/google",
            "infra_binding": [{"account": "acme", "scope": {"resource_prefixes": ["nova-"]}}],
        }
        mudanza = {
            **registered,
            "purpose": "Un proposito cualquiera.\n",
            "infra_binding": [{"account": "otra-cuenta", "scope": {"resource_prefixes": ["nova-"]}}],
        }
        self.assertEqual(_suggest_bump_level(mudanza, registered), "minor")
