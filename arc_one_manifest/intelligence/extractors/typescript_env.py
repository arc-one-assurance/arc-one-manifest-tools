"""Señales conservadoras desde TypeScript/JavaScript — evita falsos positivos de LLM env vars."""

from __future__ import annotations

import re

from arc_one_manifest.intelligence.extractors.env_names import (
    UNIDENTIFIED_SECRET_ID,
    secret_id_from_line,
)
from arc_one_manifest.intelligence.extractors.http_urls import (
    ENDPOINT_CONFIDENCE,
    HTTP_URL,
    endpoint_id_from_url,
)
from arc_one_manifest.intelligence.models import CodeSignal, Evidence

_MCP_PATTERNS = (
    re.compile(r"""mcp\.connect\s*\(\s*['"]([^'"]+)['"]""", re.I),
    re.compile(r"""mcpServer[s]?\s*[:=]\s*['"]([^'"]+)['"]""", re.I),
)

# Infra estándar de agentes demo — no elevar a finding de secrets_required.
_KNOWN_LLM_ENV = re.compile(
    r"process\.env\.(ANTHROPIC_API_KEY|OPENAI_API_KEY|AZURE_OPENAI_API_KEY|ARC_ONE_DEMO_TOKEN)",
    re.I,
)


def extract_typescript_signals(path: str, lines: list[str]) -> list[CodeSignal]:
    signals: list[CodeSignal] = []
    seen: set[tuple[str, str, str]] = set()

    for idx, raw in enumerate(lines, start=1):
        line = raw.strip()
        if not line or line.startswith("//") or line.startswith("*"):
            continue

        if _KNOWN_LLM_ENV.search(line):
            continue

        for pattern in _MCP_PATTERNS:
            match = pattern.search(line)
            if not match:
                continue
            slug = re.sub(r"[^a-z0-9-]+", "-", match.group(1).lower()).strip("-")
            key = ("mcp_server", slug or "custom-mcp", path)
            if key in seen:
                break
            seen.add(key)
            signals.append(
                CodeSignal(
                    kind="mcp_server",
                    inferred_id=slug or "custom-mcp",
                    confidence=0.85,
                    evidence=Evidence(file=path, line=idx, snippet=line[:160]),
                    manifest_section="mcp_servers",
                )
            )
            break

        if "process.env" in line and re.search(r"SECRET|TOKEN|PASSWORD", line, re.I):
            if _KNOWN_LLM_ENV.search(line):
                continue
            # El nombre está escrito en la línea: guardarlo es lo que vuelve accionable al
            # Hallazgo. Sólo si no se pudo capturar cae al id de "no sé cuál es".
            secret_id = secret_id_from_line(line) or UNIDENTIFIED_SECRET_ID
            key = ("secret", secret_id, path)
            if key in seen:
                continue
            seen.add(key)
            signals.append(
                CodeSignal(
                    kind="secret",
                    inferred_id=secret_id,
                    # Ver la nota gemela en `python_ast`: la certeza sube, pero no cruza el
                    # piso de 0.85 del bloque estático.
                    confidence=0.8 if secret_id != UNIDENTIFIED_SECRET_ID else 0.5,
                    evidence=Evidence(file=path, line=idx, snippet=line[:160]),
                    manifest_section="secrets_required",
                )
            )

        # ⭐ Servicios externos (WS180 · decisión de Tomás). Faltaba entero: el Q/A midió el
        # repo real de Nova con alcance completo y dio **0 señales**, porque el caso más
        # intuitivo del brazo código —"el agente empezó a hablar con un tercero que nadie
        # declaró"— no se buscaba en TypeScript. La regla es la MISMA que la de Python
        # (`http_urls.py`): el mismo hecho no puede tener dos ids según el lenguaje.
        for url_match in HTTP_URL.finditer(line):
            endpoint_id = endpoint_id_from_url(url_match.group(0))
            if endpoint_id is None:
                continue
            key = ("integration_endpoint", endpoint_id, path)
            if key in seen:
                continue
            seen.add(key)
            signals.append(
                CodeSignal(
                    kind="integration_endpoint",
                    inferred_id=endpoint_id,
                    confidence=ENDPOINT_CONFIDENCE,
                    evidence=Evidence(file=path, line=idx, snippet=line[:160]),
                    manifest_section="integration_endpoints",
                )
            )

    return signals
