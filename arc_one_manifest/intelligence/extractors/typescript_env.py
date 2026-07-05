"""Señales conservadoras desde TypeScript/JavaScript — evita falsos positivos de LLM env vars."""

from __future__ import annotations

import re

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
            key = ("secret", "runtime-secret", path)
            if key in seen:
                continue
            seen.add(key)
            signals.append(
                CodeSignal(
                    kind="secret",
                    inferred_id="runtime-secret",
                    confidence=0.72,
                    evidence=Evidence(file=path, line=idx, snippet=line[:160]),
                    manifest_section="secrets_required",
                )
            )

    return signals
