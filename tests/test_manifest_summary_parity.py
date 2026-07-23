"""Paridad del resumen del manifiesto CLI ↔ platform (Arc Scanner · Fase 2 · Card 2).

La pata 2 de la triangulación compara el resumen del manifiesto **del repo** (que calcula
este CLI) contra el resumen del manifiesto **registrado en Arc One** (que calcula el
platform, en `services/manifest_triangulation.py::summarize_manifest_dict`). Son dos
implementaciones de la misma regla, en dos repos distintos.

Si divergen, Arc One le reporta al cliente un drift que no existe — y nadie se entera,
porque cada repo pasa sus propios tests. Este archivo es la mitad de la red: el mismo
fixture, byte-idéntico, con su checksum, verificado de los dos lados.

🔴 Si tocás `summarize_manifest`, tocás las dos implementaciones y las dos copias del
fixture (y el checksum de los dos tests).
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from arc_one_manifest.intelligence.manifest_summary import summarize_manifest

_FIXTURE = Path(__file__).parent / "fixtures" / "manifest_summary_parity.json"

# sha256 del fixture compartido. La copia del platform tiene que dar EXACTAMENTE esto:
#   arc-one-platform/apps/api/tests/test_manifest_triangulation.py::_PARITY_FIXTURE_SHA256
# Dos valores distintos = las copias se separaron.
_PARITY_FIXTURE_SHA256 = "154caea96af15cd19bf9419b67cfd8278e387a401097bdcb14a726f6e370246a"


def _cases() -> list[dict]:
    return json.loads(_FIXTURE.read_text(encoding="utf-8"))["cases"]


def test_el_fixture_no_se_editó_de_un_solo_lado():
    """Cambiar el fixture acá y no allá es el modo silencioso de romper la paridad."""
    digest = hashlib.sha256(_FIXTURE.read_bytes()).hexdigest()
    assert digest == _PARITY_FIXTURE_SHA256, (
        "el fixture compartido cambió. Sincronizá la copia de arc-one-platform "
        "(apps/api/tests/fixtures/manifest_summary_parity.json) y actualizá el checksum "
        "en LOS DOS tests de paridad."
    )


@pytest.mark.parametrize("case", _cases(), ids=lambda c: c["name"])
def test_resumen_del_cli_coincide_con_el_golden(case):
    assert summarize_manifest(case["manifest"]).to_dict() == case["expected"]
