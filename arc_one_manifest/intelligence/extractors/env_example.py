"""Señales desde .env.example y similares."""

from __future__ import annotations

import re

from arc_one_manifest.intelligence.models import CodeSignal, Evidence

_ENV_PATTERNS: list[tuple[re.Pattern[str], str, str, float]] = [
    (re.compile(r"^(OPENAI|ANTHROPIC|AZURE_OPENAI)_API_KEY", re.I), "secret", "llm-api-key", 0.88),
    (re.compile(r"^DATABASE_URL", re.I), "data_store", "postgresql", 0.85),
    (re.compile(r"^REDIS(_URL)?", re.I), "data_store", "redis", 0.85),
    (re.compile(r"^PINECONE", re.I), "data_store", "pinecone", 0.85),
    (re.compile(r"^DYNAMODB", re.I), "data_store", "dynamodb", 0.85),
    (re.compile(r"^MCP_.*(URL|HOST|SERVER)", re.I), "mcp_server", "custom-mcp", 0.7),
]


def extract_env_example_signals(path: str, lines: list[str]) -> list[CodeSignal]:
    signals: list[CodeSignal] = []
    seen: set[tuple[str, str]] = set()

    for idx, raw in enumerate(lines, start=1):
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key = line.split("=", 1)[0].strip()
        for pattern, kind, inferred_id, confidence in _ENV_PATTERNS:
            if not pattern.search(key):
                continue
            section = {
                "secret": "secrets_required",
                "data_store": "data_stores",
                "mcp_server": "mcp_servers",
            }[kind]
            dedupe = (kind, inferred_id)
            if dedupe in seen:
                break
            seen.add(dedupe)
            signals.append(
                CodeSignal(
                    kind=kind,  # type: ignore[arg-type]
                    inferred_id=inferred_id,
                    confidence=confidence,
                    evidence=Evidence(file=path, line=idx, snippet=f"{key}=…"),
                    manifest_section=section,
                )
            )
            break
    return signals
