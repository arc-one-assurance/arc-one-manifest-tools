"""Extractores estáticos — Capa 1 de Manifest Intelligence."""

from __future__ import annotations

from arc_one_manifest.intelligence.extractors.env_example import extract_env_example_signals
from arc_one_manifest.intelligence.extractors.python_ast import extract_python_ast_signals
from arc_one_manifest.intelligence.extractors.python_deps import extract_python_deps_signals
from arc_one_manifest.intelligence.models import CodeSignal

__all__ = [
    "extract_all_signals",
    "extract_env_example_signals",
    "extract_python_ast_signals",
    "extract_python_deps_signals",
]


def extract_all_signals(path_str: str, lines: list[str]) -> list[CodeSignal]:
    rel = path_str.replace("\\", "/")
    lower = rel.lower()
    signals: list[CodeSignal] = []

    if lower.endswith((".py",)) or "/src/" in lower or lower.startswith("src/"):
        signals.extend(extract_python_ast_signals(rel, lines))

    if lower.endswith((".txt",)) and "requirements" in lower:
        signals.extend(extract_python_deps_signals(rel, lines))
    if lower == "pyproject.toml":
        signals.extend(extract_python_deps_signals(rel, lines))

    if lower.endswith(".example") or lower == ".env.example" or "env.example" in lower:
        signals.extend(extract_env_example_signals(rel, lines))

    return signals
