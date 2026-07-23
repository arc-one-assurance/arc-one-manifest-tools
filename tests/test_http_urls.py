"""La regla de servicios externos es UNA, y los dos extractores tienen que decir lo mismo.

Precedente que justifica este archivo (WS179 · `resolve_agent_id`): dos implementaciones de
la misma regla en el mismo repo, y la del reporte no podía acertar nunca porque **ningún test
las enfrentaba**. Acá el test no comprueba que cada extractor "ande": comprueba que **los dos
coincidan sobre el mismo hecho**.
"""

from __future__ import annotations

import pytest

from arc_one_manifest.intelligence.extractors.http_urls import (
    FALLBACK_ENDPOINT_ID,
    endpoint_id_from_url,
)
from arc_one_manifest.intelligence.extractors.python_ast import extract_python_ast_signals
from arc_one_manifest.intelligence.extractors.typescript_env import extract_typescript_signals


def _endpoints(signals):
    return sorted(s.inferred_id for s in signals if s.kind == "integration_endpoint")


# Mismo hecho, escrito en los dos lenguajes. El id inferido no puede depender del lenguaje.
PARES = [
    (
        'resp = requests.get("https://api.tercero.com/v1/clientes")',
        'const resp = await fetch("https://api.tercero.com/v1/clientes");',
        "api.tercero.com",
    ),
    (
        'URL = "https://payments.acme.io:8443/charge"',
        'const URL = "https://payments.acme.io:8443/charge";',
        "payments.acme.io-8443",
    ),
    (
        'r = httpx.post("http://data-lake.internal/ingest")',
        'await axios.post("http://data-lake.internal/ingest");',
        "data-lake.internal",
    ),
]


@pytest.mark.parametrize("py_line, ts_line, esperado", PARES)
def test_los_dos_extractores_infieren_el_mismo_id(py_line, ts_line, esperado):
    desde_python = _endpoints(extract_python_ast_signals("src/app.py", [py_line]))
    desde_ts = _endpoints(extract_typescript_signals("src/app.ts", [ts_line]))

    assert desde_python == [esperado]
    # El corazón del test: no es que cada uno acierte, es que **coincidan**.
    assert desde_python == desde_ts


@pytest.mark.parametrize(
    "url",
    ["http://localhost:3000/health", "http://127.0.0.1:8000/x", "https://example.com/docs"],
)
def test_ninguno_reporta_desarrollo_local_ni_placeholders(url):
    """Reportar `localhost` sería drift inventado: no es un servicio externo del agente."""
    py_line = f'requests.get("{url}")'
    ts_line = f'fetch("{url}");'

    assert _endpoints(extract_python_ast_signals("src/app.py", [py_line])) == []
    assert _endpoints(extract_typescript_signals("src/app.ts", [ts_line])) == []
    assert endpoint_id_from_url(url) is None


def test_el_contrapeso_una_url_de_verdad_si_se_reporta():
    """Sin esto, el test de arriba pasaría con un extractor que no reporta NUNCA nada.

    Es la regla del golden con contrapeso (WS177 · regla 7) aplicada a un filtro: hay que
    probar que el filtro **deja pasar** lo que no filtra.
    """
    assert _endpoints(extract_python_ast_signals("src/a.py", ['get("https://real.io/x")'])) == [
        "real.io"
    ]
    assert _endpoints(extract_typescript_signals("src/a.ts", ['fetch("https://real.io/x")'])) == [
        "real.io"
    ]


def test_el_id_sale_del_HOST_no_del_path():
    """El path cambia por llamada; el host es el servicio que el Manifiesto declara."""
    a = endpoint_id_from_url("https://api.tercero.com/v1/clientes")
    b = endpoint_id_from_url("https://api.tercero.com/v2/pedidos?x=1")
    assert a == b == "api.tercero.com"


def test_una_url_sin_host_legible_cae_al_fallback_y_no_a_un_id_vacio():
    assert endpoint_id_from_url("https://///") == FALLBACK_ENDPOINT_ID


def test_el_comentario_no_produce_senal_en_ts():
    """El extractor de TS ya salteaba comentarios; que sumar URLs no lo rompa."""
    assert _endpoints(extract_typescript_signals("src/a.ts", ['// ver https://docs.acme.io'])) == []
