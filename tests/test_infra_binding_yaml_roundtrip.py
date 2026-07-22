"""Round-trip repo ↔ Arc One, partiendo de YAML REAL.

**Por qué este archivo existe.** Los 23 tests de `test_infra_binding.py` construyen los
manifiestos como diccionarios de Python. Eso saltea la única capa donde nace el bug más
caro del bloque: **el parser de YAML**. Un `account` de AWS son 12 dígitos y sin comillas
`yaml.safe_load` devuelve un `int`, no un `str` — y el platform lo guarda como `str`.

Con el hash del gate calculado sobre la forma cruda, los dos lados nunca coincidían:
el CI del cliente fallaba en cada push con "manifest content changed" sobre un
manifiesto que no cambió, y **no convergía** (bumpear no arregla nada, porque el
platform sigue guardando el string y el repo sigue leyendo el entero).

Todo lo de acá parte de texto YAML, como en el repo del cliente.
"""
from __future__ import annotations

import copy

import yaml

from arc_one_manifest.gate import _normalize_for_drift, _stable_hash, _suggest_bump_level
from arc_one_manifest.infra_binding import bindings_to_payload, canonical_bindings
from arc_one_manifest.validation.madre_v11 import (
    ManifestValidationError,
    validate_madre_manifest,
)


def _yaml(text: str) -> dict:
    return yaml.safe_load(text)


def _errores(manifest: dict) -> list:
    """Los errores de validación como lista.

    `validate_madre_manifest` levanta en vez de devolver; los manifiestos de acá son
    parciales a propósito (sólo el bloque que se está probando), así que siempre hay
    errores de campos faltantes — lo que se afirma es que ADEMÁS esté el del binding.
    """
    try:
        validate_madre_manifest(manifest, require_connector=False)
    except ManifestValidationError as exc:
        return list(exc.errors)
    return []


def _as_registered(repo: dict) -> dict:
    """Simula lo que devuelve el export de Arc One tras ingerir el manifiesto.

    El platform normaliza al guardar (`coerce_account` / `clean_str_list` /
    `coerce_labels` de `manifest_v2_schemas.py`) y el export emite snake_case con las
    claves vacías omitidas (`manifest_export._infra_binding_for_export`).
    """
    out = copy.deepcopy(repo)
    canon = canonical_bindings(repo)
    out.pop("infraBinding", None)
    if canon:
        out["infra_binding"] = canon
    else:
        out.pop("infra_binding", None)
    return out


def _same_hash(repo: dict, registered: dict) -> bool:
    return _stable_hash(_normalize_for_drift(repo)) == _stable_hash(
        _normalize_for_drift(registered)
    )


# ---------------------------------------------------------------------------------
# El bloqueante: el account numérico
# ---------------------------------------------------------------------------------

_ACCOUNT_SIN_COMILLAS = """
name: nova
agent_version: 1.0.0
manifest_version: "1.3"
purpose: |
  Un agente de prueba.
infra_binding:
  - account: 112233445566
    scope:
      resource_prefixes: [nova-]
"""


def test_account_numerico_no_marca_drift_falso():
    repo = _yaml(_ACCOUNT_SIN_COMILLAS)
    assert isinstance(repo["infra_binding"][0]["account"], int), (
        "el fixture perdió el punto: YAML tiene que entregar un int acá"
    )

    assert _same_hash(repo, _as_registered(repo)), (
        "el account numérico marca drift falso — el CI del cliente queda bloqueado y "
        "bumpear la versión no lo resuelve"
    )


def test_account_numerico_convergiria_tras_bumpear():
    """El corazón del bloqueante: antes, bumpear y registrar NO arreglaba nada."""
    repo = _yaml(_ACCOUNT_SIN_COMILLAS)
    registered = _as_registered(repo)

    repo["agent_version"] = "1.0.1"
    registered["agent_version"] = "1.0.1"

    assert _same_hash(repo, registered)


def test_validate_pide_comillas_en_el_account_numerico():
    """Se ataja en el punto más barato, con un mensaje que se entiende."""
    errores = _errores(_yaml(_ACCOUNT_SIN_COMILLAS))
    assert any("comillas" in e for e in errores), errores


# ---------------------------------------------------------------------------------
# Las otras tres asimetrías con el platform
# ---------------------------------------------------------------------------------


def test_prefijos_duplicados_no_marcan_drift():
    repo = _yaml(
        """
        name: nova
        infra_binding:
          - account: acme-prod
            scope:
              resource_prefixes: [nova-, nova-, " nova-otro "]
        """
    )
    assert _same_hash(repo, _as_registered(repo))
    canon = canonical_bindings(repo)
    assert canon[0]["scope"]["resource_prefixes"] == ["nova-", "nova-otro"]


def test_labels_con_valor_numerico_no_marcan_drift():
    repo = _yaml(
        """
        name: nova
        infra_binding:
          - account: acme-prod
            scope:
              resource_prefixes: [nova-]
              labels: {app: 3}
        """
    )
    assert _same_hash(repo, _as_registered(repo))
    assert canonical_bindings(repo)[0]["scope"]["labels"] == {"app": "3"}


def test_account_con_espacios_no_marca_drift():
    repo = _yaml(
        """
        name: nova
        infra_binding:
          - account: "  acme-prod  "
            scope:
              resource_prefixes: [nova-]
        """
    )
    assert _same_hash(repo, _as_registered(repo))


def test_alias_camelcase_no_marca_drift():
    """El validador acepta `infraBinding` / `resourcePrefixes`; el export emite snake."""
    repo = _yaml(
        """
        name: nova
        infraBinding:
          - account: acme-prod
            scope:
              resourcePrefixes: [nova-]
        """
    )
    assert _same_hash(repo, _as_registered(repo))


# ---------------------------------------------------------------------------------
# El orden de la lista no es contenido
# ---------------------------------------------------------------------------------


def test_reordenar_la_lista_no_es_drift():
    """Mover el binding de AWS arriba del de GCP no es un cambio material.

    Antes hacía fallar el CI y obligaba a bumpear una versión por un cambio de líneas.
    """
    base = """
        name: nova
        infra_binding:
          - account: acme-prod
            scope:
              resource_prefixes: [nova-]
          - account: "112233445566"
            scope:
              resource_prefixes: [nova-events-]
        """
    reordenado = """
        name: nova
        infra_binding:
          - account: "112233445566"
            scope:
              resource_prefixes: [nova-events-]
          - account: acme-prod
            scope:
              resource_prefixes: [nova-]
        """
    assert _same_hash(_yaml(base), _yaml(reordenado))
    assert _suggest_bump_level(_yaml(base), _yaml(reordenado)) == "patch"


# ---------------------------------------------------------------------------------
# Bump: agregar, quitar y reacomodar
# ---------------------------------------------------------------------------------


def _con_bindings(bloque: str) -> dict:
    return _yaml(f"name: nova\nagent_version: 1.0.0\n{bloque}")


_UNA_CUENTA = """
infra_binding:
  - account: acme-prod
    scope:
      resource_prefixes: [nova-]
"""
_DOS_CUENTAS = """
infra_binding:
  - account: acme-prod
    scope:
      resource_prefixes: [nova-]
  - account: "112233445566"
    scope:
      resource_prefixes: [nova-events-]
"""


def test_agregar_una_nube_sugiere_minor():
    assert _suggest_bump_level(_con_bindings(_DOS_CUENTAS), _con_bindings(_UNA_CUENTA)) == "minor"


def test_quitar_una_nube_sugiere_minor():
    """El caso inverso, que no tenía test: dejar de operar en una cuenta es material."""
    assert _suggest_bump_level(_con_bindings(_UNA_CUENTA), _con_bindings(_DOS_CUENTAS)) == "minor"


def test_quitar_el_bloque_entero_sugiere_minor():
    sin_bloque = _yaml("name: nova\nagent_version: 1.0.0\n")
    assert _suggest_bump_level(sin_bloque, _con_bindings(_UNA_CUENTA)) == "minor"


def test_reacomodar_el_scope_sugiere_patch():
    otro_scope = """
infra_binding:
  - account: acme-prod
    scope:
      resource_prefixes: [nova-, nova-batch-]
"""
    assert _suggest_bump_level(_con_bindings(otro_scope), _con_bindings(_UNA_CUENTA)) == "patch"


# ---------------------------------------------------------------------------------
# Nada de declaración muerta silenciosa
# ---------------------------------------------------------------------------------


def test_infra_bindings_en_plural_se_rechaza():
    """El typo más natural. Antes validaba OK y el bloque se ignoraba entero."""
    errores = _errores(
        _yaml(
            """
            name: nova
            infra_bindings:
              - account: acme-prod
                scope:
                  resource_prefixes: [nova-]
            """
        )
    )
    assert any("infra_binding" in e and "infra_bindings" in e for e in errores), errores


def test_clave_desconocida_en_el_scope_se_rechaza_con_sugerencia():
    errores = _errores(
        _yaml(
            """
            name: nova
            infra_binding:
              - account: acme-prod
                scope:
                  resource_prefix: [nova-]
                  regions: [europe-west1]
            """
        )
    )
    assert any("resource_prefixes" in e and "resource_prefix" in e for e in errores), errores


def test_provider_declarado_se_rechaza():
    """El doc es explícito: el provider se DERIVA de la cuenta, no se declara."""
    errores = _errores(
        _yaml(
            """
            name: nova
            infra_binding:
              - account: acme-prod
                provider: aws
                scope:
                  resource_prefixes: [nova-]
            """
        )
    )
    assert any("provider" in e for e in errores), errores


# ---------------------------------------------------------------------------------
# El payload del registro sale del MISMO normalizador que el hash
# ---------------------------------------------------------------------------------


def test_el_payload_del_registro_manda_la_forma_canonica():
    """Si el registro mandara algo distinto de lo que el gate hashea, el drift vuelve."""
    repo = _yaml(_ACCOUNT_SIN_COMILLAS)
    payload = bindings_to_payload(repo)

    assert payload == [{"account": "112233445566", "scope": {"resourcePrefixes": ["nova-"]}}]
    assert isinstance(payload[0]["account"], str)


def test_sin_bloque_el_payload_es_none():
    """Omitir ≠ mandar null: el export tampoco lo emite, y el hash tiene que cerrar."""
    assert bindings_to_payload(_yaml("name: nova\n")) is None
