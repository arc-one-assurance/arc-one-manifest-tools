"""La regla ÚNICA para derivar el id de un servicio externo desde una URL en el código.

⭐ Por qué existe este módulo y no dos copias de la misma regex.

El extractor de Python detectaba servicios externos y el de TypeScript no (WS180 · el Q/A
en frío lo midió sobre el repo real de Nova: **0 señales**). Al portarlo, la tentación era
copiar las seis líneas al otro extractor. **Ese es exactamente el error que la WS179 pagó
con `resolve_agent_id`:** dos implementaciones de la misma regla en el mismo repo, y la
segunda no podía acertar nunca porque nadie las enfrentó.

Así que la regla vive acá, una sola vez, y la consumen los dos extractores. El test
`test_http_urls.py` los **enfrenta**: la misma URL tiene que producir el mismo id en
Python y en TypeScript, o el sistema estaría diciendo dos cosas distintas del mismo hecho
según en qué lenguaje esté escrito el agente.

⚠️ **Alcance honesto** (doc 99 §4.2): esto detecta URLs **literales** en el código. Una URL
armada por concatenación o traída de una variable de entorno no se ve. Es detección
conservadora, no análisis semántico — y por eso la confianza es 0.68 y no más.
"""

from __future__ import annotations

import re

HTTP_URL = re.compile(r"""https?://[^\s'"]+""")

# Nada de esto describe un servicio externo del agente: es desarrollo local o placeholder
# de documentación. Reportarlo sería drift inventado.
_SKIP_HOSTS = ("localhost", "127.0.0.1", "example.com")

# Cuando hay URL pero no se pudo derivar un host utilizable. No es un placeholder de
# "no sé qué es" (esos viven en `UNIDENTIFIED_SIGNAL_IDS`): acá sí sabemos que es un
# endpoint HTTP, sólo que sin host legible.
FALLBACK_ENDPOINT_ID = "http-endpoint"

ENDPOINT_CONFIDENCE = 0.68


def endpoint_id_from_url(url: str) -> str | None:
    """El id de catálogo que se infiere de una URL, o ``None`` si no hay que reportarla.

    Se queda con el **host**: es lo único estable de una URL (el path cambia por llamada;
    el host es el servicio con el que el agente habla, que es lo que el Manifiesto declara).
    """
    if any(skip in url for skip in _SKIP_HOSTS):
        return None
    host = re.sub(r"^https?://", "", url).split("/")[0].lower()
    slug = re.sub(r"[^a-z0-9.-]+", "-", host)[:48]
    return slug or FALLBACK_ENDPOINT_ID
