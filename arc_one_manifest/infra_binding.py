"""Forma canónica de `infra_binding` — un solo normalizador para todo el CLI.

**Por qué existe este módulo.** El `gate` decide si hay drift comparando el HASH del
manifiesto del repo contra el HASH del manifiesto registrado en Arc One. El platform
normaliza el bloque al ingerirlo (un `account` numérico pasa a string, los prefijos se
deduplican y se limpian, los valores de `labels` se vuelven strings). Si el CLI hashea
la forma CRUDA del YAML, los dos lados nunca coinciden.

El caso que lo hace grave es el más natural de todos: un accountId de AWS son 12
dígitos, y en YAML sin comillas se parsea como entero.

    infra_binding:
      - account: 112233445566      # int, no string

`validate` pasa. `register` pasa (el platform coerce). Y a partir de ahí el `gate`
falla en CADA push con "manifest content changed" sobre un manifiesto que no cambió —
y **no converge**: el cliente bumpea la versión, registra, y al push siguiente vuelve a
fallar, porque el platform sigue guardando el string y el repo sigue leyendo el entero.
El pipeline queda muerto con un mensaje que miente.

La regla: **el CLI canoniza exactamente igual que el platform, y en un solo lugar.**
Cualquier campo nuevo del bloque se agrega ACÁ, no en `gate.py` y `register.py` por
separado.

Referencia del otro lado: `arc-one-platform` · `services/manifest_v2_schemas.py`
(`InfraBindingV2` / `InfraBindingScopeV2`) y `services/manifest_export.py`
(`_infra_binding_for_export`).
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional

# Las dos formas en que el bloque puede venir en el YAML.
_TOP_LEVEL_KEYS = ("infra_binding", "infraBinding")


def _clean_str_list(value: Any) -> List[str]:
    """Strip + descarte de vacíos + dedupe preservando orden.

    Espeja `InfraBindingScopeV2.clean_str_list` del platform. Los items que no son
    string se ignoran (el validador ya los reportó como error legible).
    """
    if not isinstance(value, list):
        return []
    return list(
        dict.fromkeys(item.strip() for item in value if isinstance(item, str) and item.strip())
    )


def _clean_labels(value: Any) -> Dict[str, str]:
    """Claves y valores a string. Espeja `coerce_labels` del platform.

    `app: 3` en YAML llega como int; el platform lo guarda como `"3"`.
    """
    if not isinstance(value, dict):
        return {}
    return {str(k).strip(): str(v).strip() for k, v in value.items() if str(k).strip()}


def _clean_account(value: Any) -> str:
    """Numérico → string, y strip. Espeja `coerce_account` + `clean_account`."""
    if isinstance(value, bool):  # antes que int: en Python `bool` ES `int`
        return ""
    if isinstance(value, (int, float)):
        return str(value)
    if isinstance(value, str):
        return value.strip()
    return ""


def raw_infra_binding(manifest: Dict[str, Any]) -> Any:
    """El bloque tal como vino del YAML, mirando las dos formas de la clave."""
    for key in _TOP_LEVEL_KEYS:
        if key in manifest:
            return manifest.get(key)
    return None


def normalized_bindings(manifest: Dict[str, Any]) -> Optional[List[Dict[str, Any]]]:
    """La forma normalizada en snake_case, **en el orden que la escribió el cliente**.

    Las claves vacías del scope se OMITEN, igual que en el export del platform: un repo
    que sólo declara `resource_prefixes` no escribe `regions: []`.

    Es la forma que se GUARDA (el orden del autor es suyo). Para comparar contenido, ver
    `canonical_bindings`.
    """
    raw = raw_infra_binding(manifest)
    if not isinstance(raw, list) or not raw:
        return None

    bindings: List[Dict[str, Any]] = []
    for item in raw:
        if not isinstance(item, dict):
            continue
        account = _clean_account(item.get("account"))
        scope_raw = item.get("scope") if isinstance(item.get("scope"), dict) else {}

        scope: Dict[str, Any] = {}
        prefixes = _clean_str_list(
            scope_raw.get("resource_prefixes")
            if scope_raw.get("resource_prefixes") is not None
            else scope_raw.get("resourcePrefixes")
        )
        if prefixes:
            scope["resource_prefixes"] = prefixes
        regions = _clean_str_list(scope_raw.get("regions"))
        if regions:
            scope["regions"] = regions
        labels = _clean_labels(scope_raw.get("labels"))
        if labels:
            scope["labels"] = labels

        bindings.append({"account": account, "scope": scope})

    return bindings or None


def canonical_bindings(manifest: Dict[str, Any]) -> Optional[List[Dict[str, Any]]]:
    """La forma normalizada **ordenada por cuenta** — la que se usa para COMPARAR.

    El orden de la lista no tiene significado (doc 16a §2.3: "una cuenta, un binding"),
    así que reordenar dos bindings en el YAML no puede contar como cambio material.
    Antes de esto, mover el binding de AWS arriba del de GCP hacía fallar el CI y
    obligaba a bumpear una versión por un cambio de líneas.

    Ojo con la distinción: se ordena para HASHEAR, no para guardar. El registro manda el
    orden que escribió el cliente (`normalized_bindings`) — es su archivo. Ordenar sólo
    en la comparación deja las dos cosas bien: el orden se respeta y no es contenido.
    """
    norm = normalized_bindings(manifest)
    if not norm:
        return None
    return sorted(norm, key=lambda b: b["account"])


def bindings_to_payload(manifest: Dict[str, Any]) -> Optional[List[Dict[str, Any]]]:
    """La forma normalizada en camelCase, para `identidad.infraBinding` del registro.

    Mismo normalizador que el hash, sólo cambian los nombres de clave. Que salgan de la
    MISMA función es el punto: si el registro mandara algo distinto de lo que el gate
    compara, volvemos al drift falso por otra puerta.
    """
    norm = normalized_bindings(manifest)
    if not norm:
        return None

    out: List[Dict[str, Any]] = []
    for item in norm:
        scope = item["scope"]
        mapped: Dict[str, Any] = {}
        if scope.get("resource_prefixes"):
            mapped["resourcePrefixes"] = list(scope["resource_prefixes"])
        if scope.get("regions"):
            mapped["regions"] = list(scope["regions"])
        if scope.get("labels"):
            mapped["labels"] = dict(scope["labels"])
        out.append({"account": item["account"], "scope": mapped})
    return out


def binding_accounts(manifest: Dict[str, Any]) -> set:
    """Las cuentas declaradas (ignora el scope). Insumo de la sugerencia de bump."""
    canon = canonical_bindings(manifest) or []
    return {b["account"] for b in canon if b["account"]}
