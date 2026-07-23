"""El nombre de la variable de entorno que la línea realmente lee.

🔴 **Por qué existe** (WS179): los extractores de Python y TS matcheaban `SECRET|TOKEN|
PASSWORD` en la línea y después emitían la constante ``runtime-secret``, **tirando el
nombre que tenían escrito adelante**. `const token = process.env.CRM_API_SECRET` producía
un Hallazgo que decía *"el código usa el secreto «runtime-secret»"* — algo que nadie puede
declarar ni corregir. No era que el determinístico no pudiera identificarlo: lo
identificaba y lo descartaba.

Recuperar el nombre es lo que vuelve accionable al Hallazgo, **y sin LLM**: pedirle a un
juez que deduzca `CRM_API_SECRET` de un snippet que dice `CRM_API_SECRET` sería taparle
el agujero a un grupo de captura. Es el delta B otra vez (*el LLM tapando la falta de un
vocabulario que ya existe*), corrido de lugar.

Lo que **sí** queda para el juez es el caso honesto: una variable que no se pudo capturar.
Ahí se devuelve ``""`` y quien llama decide — hoy, un Hallazgo que dice que no se pudo
identificar, con certeza baja; después de la Fase 2bis, el mismo Hallazgo con el juez
completando la identidad.
"""

from __future__ import annotations

import re

# `process.env.NAME` · `process.env["NAME"]` · `os.environ["NAME"]` ·
# `os.environ.get("NAME"…)` · `os.getenv("NAME"…)`
_ENV_NAME_PATTERNS = (
    re.compile(r"""process\.env\.([A-Za-z_][A-Za-z0-9_]*)"""),
    re.compile(r"""process\.env\s*\[\s*['"]([^'"]+)['"]"""),
    re.compile(r"""os\.environ\s*\[\s*['"]([^'"]+)['"]"""),
    re.compile(r"""os\.environ\.get\s*\(\s*['"]([^'"]+)['"]"""),
    re.compile(r"""os\.getenv\s*\(\s*['"]([^'"]+)['"]"""),
)

# La key del proveedor del modelo NO es un secreto aparte: ya está implícita en el
# `agent_model` declarado. Colapsan al id que el CLI y el platform ya tratan como tal
# (`_is_declared` acá, `SignalMatch` allá) — capturar el nombre real no puede romper eso.
_LLM_KEY_NAMES = re.compile(
    r"^(OPENAI|ANTHROPIC|AZURE_OPENAI|GOOGLE|GEMINI|VERTEX)_?(AI_)?API_KEY$",
    re.I,
)

LLM_API_KEY_ID = "llm-api-key"
# El que dice "vi un secreto y no sé cuál". Sigue existiendo, pero ahora es la EXCEPCIÓN.
UNIDENTIFIED_SECRET_ID = "runtime-secret"


def env_var_name(line: str) -> str:
    """El nombre de la variable leída en esta línea, o ``""`` si no se pudo capturar."""
    for pattern in _ENV_NAME_PATTERNS:
        match = pattern.search(line)
        if match:
            return match.group(1).strip()
    return ""


def secret_id_from_line(line: str) -> str:
    """``inferred_id`` para una señal de secreto. ``""`` cuando no se pudo identificar."""
    name = env_var_name(line)
    if not name:
        return ""
    if _LLM_KEY_NAMES.match(name):
        return LLM_API_KEY_ID
    slug = re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")
    return slug or ""
