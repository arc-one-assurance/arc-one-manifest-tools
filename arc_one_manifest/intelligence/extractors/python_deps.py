"""Señales desde requirements.txt / pyproject.toml."""

from __future__ import annotations

import re

from arc_one_manifest.intelligence.models import CodeSignal, Evidence

_PKG_HINTS: dict[str, tuple[str, str, float]] = {
    "anthropic": ("model_hint", "anthropic", 0.78),
    "openai": ("model_hint", "openai", 0.78),
    "boto3": ("data_store", "aws-sdk", 0.65),
    "pinecone": ("data_store", "pinecone", 0.82),
    "redis": ("data_store", "redis", 0.82),
    "psycopg": ("data_store", "postgresql", 0.82),
    "psycopg2": ("data_store", "postgresql", 0.82),
    "sqlalchemy": ("data_store", "postgresql", 0.6),
}


def extract_python_deps_signals(path: str, lines: list[str]) -> list[CodeSignal]:
    signals: list[CodeSignal] = []
    seen: set[tuple[str, str]] = set()

    for idx, raw in enumerate(lines, start=1):
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        pkg = re.split(r"[<>=!~\[]", line, maxsplit=1)[0].strip().lower()
        if not pkg:
            continue
        hint = _PKG_HINTS.get(pkg)
        if hint is None:
            continue
        kind, inferred_id, confidence = hint
        key = (kind, inferred_id)
        if key in seen:
            continue
        seen.add(key)
        section = "agent_model" if kind == "model_hint" else "data_stores"
        signals.append(
            CodeSignal(
                kind=kind,  # type: ignore[arg-type]
                inferred_id=inferred_id,
                confidence=confidence,
                evidence=Evidence(file=path, line=idx, snippet=line[:160]),
                manifest_section=section,
            )
        )
    return signals
