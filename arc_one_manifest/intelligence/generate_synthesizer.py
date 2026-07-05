"""LLM synthesizer para campos narrativos en manifest bootstrap."""

from __future__ import annotations

import json
import os
import re
from pathlib import Path
from typing import Any

from arc_one_manifest.intelligence.generate_models import FieldReport
from arc_one_manifest.intelligence.judge import AnthropicJudgeClient

_PROMPT_PATH = Path(__file__).parent / "prompts" / "generate_synthesizer_v1.txt"


def _readme_excerpt(repo: Path, *, max_chars: int = 3000) -> str:
    readme = repo / "README.md"
    if not readme.is_file():
        return f"Repo: {repo.name}"
    text = readme.read_text(encoding="utf-8", errors="replace")
    return text[:max_chars]


def _extract_json(text: str) -> dict[str, Any]:
    text = text.strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*", "", text)
        text = re.sub(r"\s*```$", "", text)
    parsed = json.loads(text)
    if not isinstance(parsed, dict):
        raise ValueError("Synthesizer response must be a JSON object")
    return parsed


def synthesize_narrative_fields(
    repo: Path,
    *,
    profile: str,
    manifest: dict[str, Any],
    signals_summary: list[str],
) -> tuple[dict[str, Any], dict[str, FieldReport]]:
    """Enriquece purpose y system_prompt vía LLM. Devuelve (patches, field_reports)."""
    api_key = os.environ.get("ARC_ONE_LLM_API_KEY", "").strip()
    if not api_key:
        return {}, {}

    payload = {
        "repo_name": repo.name,
        "profile": profile,
        "readme_excerpt": _readme_excerpt(repo),
        "agent_model": manifest.get("agent_model"),
        "data_stores": [r.get("asset_id") for r in manifest.get("data_stores") or []],
        "mcp_servers": [r.get("mcp_id") for r in manifest.get("mcp_servers") or []],
        "code_signals_summary": signals_summary[:20],
    }
    client = AnthropicJudgeClient(
        api_key=api_key,
        model=os.environ.get("ARC_ONE_LLM_MODEL", "claude-sonnet-4-6"),
    )
    raw = client.complete(_PROMPT_PATH.read_text(encoding="utf-8"), json.dumps(payload, ensure_ascii=False, indent=2))
    data = _extract_json(raw)

    patches: dict[str, Any] = {}
    fields: dict[str, FieldReport] = {}
    confidence = float(data.get("confidence") or 0.7)

    purpose = data.get("purpose")
    if isinstance(purpose, str) and len(purpose.strip()) >= 50:
        patches["purpose"] = purpose.strip()
        fields["purpose"] = FieldReport(value=purpose.strip(), confidence=confidence, evidence="LLM synthesizer", status="inferred")

    sp = data.get("system_prompt_content")
    if isinstance(sp, str) and len(sp.strip()) >= 20:
        patches["system_prompt"] = {
            "transparency_level": "full",
            "content": sp.strip(),
            "notes": "Generado por arc-one-manifest generate (LLM)",
        }
        fields["system_prompt"] = FieldReport(value="(generated)", confidence=confidence, evidence="LLM synthesizer", status="inferred")

    for key in ("technical_owner", "business_owner"):
        val = data.get(key)
        if isinstance(val, str) and "@" in val and val.upper() != "TODO":
            patches[key] = val.strip()
            fields[key] = FieldReport(value=val.strip(), confidence=confidence, evidence="README/LLM", status="inferred")

    return patches, fields
