"""El nombre canónico de un agente, derivado de su Manifiesto.

⚠️ **Esta regla vive en tres lugares y tiene que decir lo mismo en los tres:**
acá, en el ``gate`` y en ``_slugify`` de ``manifest_registration_v2.py`` del platform
(que es quien lo escribe en la DB al registrar). El Manifiesto MADRE **no** trae una
clave ``nombre_canonico``: trae ``name``, y el canónico se deriva. Quien lo busque
como clave del YAML no lo va a encontrar nunca — ése fue el bug de WS179.

No levanta: devolver ``""`` deja que cada llamador decida. El ``gate`` **es** una
compuerta y corta; el reporte del audit avisa y sigue.
"""
from __future__ import annotations

import re
import unicodedata
from typing import Any, Dict


def canonical_name(manifest: Dict[str, Any]) -> str:
    """``name`` del Manifiesto → slug. ``""`` si no hay nombre."""
    name = str(manifest.get("name") or "").strip()
    if not name:
        return ""
    s = name.lower()
    s = unicodedata.normalize("NFD", s)
    s = "".join(ch for ch in s if unicodedata.category(ch) != "Mn")
    s = re.sub(r"[^a-z0-9]+", "-", s)
    s = re.sub(r"(^-+|-+$)", "", s)
    return s or "agent"
