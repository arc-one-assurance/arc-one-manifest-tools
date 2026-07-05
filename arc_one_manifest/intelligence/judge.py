"""Capa 2 — LLM Judge para Manifest Intelligence."""

from __future__ import annotations

import json
import os
import re
from pathlib import Path
from typing import Any, Protocol

import httpx

from arc_one_manifest.intelligence.catalog import resolve_signal_catalog_id
from arc_one_manifest.intelligence.models import AuditFinding, CodeSignal, Evidence, ManifestSummary
from arc_one_manifest.material_paths import MATERIAL_PATHS

_PROMPT_PATH = Path(__file__).parent / "prompts" / "audit_judge_v1.txt"
_DEFAULT_MODEL = "claude-sonnet-4-20250514"
_ANTHROPIC_URL = "https://api.anthropic.com/v1/messages"


class JudgeClient(Protocol):
    def complete(self, system: str, user_payload: str) -> str: ...


class AnthropicJudgeClient:
    def __init__(
        self,
        *,
        api_key: str,
        model: str = _DEFAULT_MODEL,
        timeout: float = 60.0,
    ) -> None:
        self._api_key = api_key
        self._model = model
        self._timeout = timeout

    def complete(self, system: str, user_payload: str) -> str:
        with httpx.Client(timeout=self._timeout) as client:
            resp = client.post(
                _ANTHROPIC_URL,
                headers={
                    "x-api-key": self._api_key,
                    "anthropic-version": "2023-06-01",
                    "content-type": "application/json",
                },
                json={
                    "model": self._model,
                    "max_tokens": 2048,
                    "system": system,
                    "messages": [{"role": "user", "content": user_payload}],
                },
            )
            resp.raise_for_status()
            data = resp.json()
        blocks = data.get("content") or []
        text_parts = [b.get("text", "") for b in blocks if b.get("type") == "text"]
        return "".join(text_parts).strip()


def _load_system_prompt() -> str:
    return _PROMPT_PATH.read_text(encoding="utf-8")


def build_judge_payload(
    *,
    manifest_path: str,
    summary: ManifestSummary,
    signals: list[CodeSignal],
    manifest_changed_in_pr: bool = False,
) -> dict[str, Any]:
    return {
        "manifest_path": manifest_path,
        "manifest_summary": summary.to_dict(),
        "code_signals": [s.to_dict() for s in signals],
        "manifest_changed_in_pr": manifest_changed_in_pr,
        "material_paths": sorted(MATERIAL_PATHS),
    }


def _extract_json(text: str) -> dict[str, Any]:
    text = text.strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*", "", text)
        text = re.sub(r"\s*```$", "", text)
    parsed = json.loads(text)
    if not isinstance(parsed, dict):
        raise ValueError("Judge response must be a JSON object")
    return parsed


def _parse_finding(row: dict[str, Any]) -> AuditFinding | None:
    code = str(row.get("code") or "MANIFEST_STALE")
    if code not in ("MANIFEST_STALE", "UNCERTAIN", "CATALOG_UNKNOWN"):
        code = "MANIFEST_STALE"
    severity = row.get("severity") or "medium"
    if severity not in ("high", "medium", "low"):
        severity = "medium"
    confidence = float(row.get("confidence") or 0.7)
    title = str(row.get("title") or "Drift detectado")
    detail = str(row.get("detail") or title)
    section = str(row.get("manifestSection") or row.get("manifest_section") or "data_stores")
    catalog_id = str(row.get("suggestedCatalogId") or row.get("suggested_catalog_id") or "unknown")
    evidence_rows = row.get("evidence") or []
    evidence: list[Evidence] = []
    if isinstance(evidence_rows, list):
        for ev in evidence_rows:
            if not isinstance(ev, dict):
                continue
            evidence.append(
                Evidence(
                    file=str(ev.get("file") or ""),
                    line=int(ev.get("line") or 0),
                    snippet=str(ev.get("snippet") or "")[:160],
                )
            )
    return AuditFinding(
        code=code,  # type: ignore[arg-type]
        severity=severity,  # type: ignore[arg-type]
        confidence=confidence,
        title=title,
        detail=detail,
        manifest_section=section,
        suggested_catalog_id=catalog_id,
        evidence=evidence,
    )


def parse_judge_response(text: str) -> tuple[list[AuditFinding], bool]:
    data = _extract_json(text)
    rows = data.get("findings") or []
    clean = bool(data.get("clean", False))
    findings: list[AuditFinding] = []
    if isinstance(rows, list):
        for row in rows:
            if isinstance(row, dict):
                finding = _parse_finding(row)
                if finding is not None:
                    findings.append(finding)
    if not findings and not clean:
        clean = True
    return findings, clean


def enrich_findings_with_catalog(findings: list[AuditFinding]) -> list[AuditFinding]:
    out: list[AuditFinding] = []
    for f in findings:
        canonical, known = resolve_signal_catalog_id(f.suggested_catalog_id, f.manifest_section)
        if not known and f.code == "MANIFEST_STALE":
            out.append(
                AuditFinding(
                    code="CATALOG_UNKNOWN",
                    severity=f.severity,
                    confidence=f.confidence,
                    title=f.title,
                    detail=f"{f.detail} (ID `{canonical}` no está en catálogo embebido.)",
                    manifest_section=f.manifest_section,
                    suggested_catalog_id=canonical,
                    evidence=f.evidence,
                )
            )
            continue
        if canonical != f.suggested_catalog_id:
            out.append(
                AuditFinding(
                    code=f.code,
                    severity=f.severity,
                    confidence=f.confidence,
                    title=f.title,
                    detail=f.detail,
                    manifest_section=f.manifest_section,
                    suggested_catalog_id=canonical,
                    evidence=f.evidence,
                )
            )
        else:
            out.append(f)
    return out


def run_judge(
    *,
    manifest_path: str,
    summary: ManifestSummary,
    signals: list[CodeSignal],
    manifest_changed_in_pr: bool = False,
    client: JudgeClient | None = None,
    min_confidence: float = 0.7,
) -> tuple[list[AuditFinding], bool, str | None]:
    """Ejecuta el judge LLM. Devuelve (findings, clean, model_used)."""
    if not signals:
        return [], True, None

    api_key = os.environ.get("ARC_ONE_LLM_API_KEY", "").strip()
    judge_client = client
    if judge_client is None:
        if not api_key:
            raise ValueError("ARC_ONE_LLM_API_KEY required when audit runs without --static-only")
        judge_client = AnthropicJudgeClient(api_key=api_key, model=os.environ.get("ARC_ONE_LLM_MODEL", _DEFAULT_MODEL))

    payload = build_judge_payload(
        manifest_path=manifest_path,
        summary=summary,
        signals=signals,
        manifest_changed_in_pr=manifest_changed_in_pr,
    )
    raw = judge_client.complete(_load_system_prompt(), json.dumps(payload, ensure_ascii=False, indent=2))
    findings, clean = parse_judge_response(raw)
    findings = [f for f in findings if f.confidence >= min_confidence]
    findings = enrich_findings_with_catalog(findings)
    blocking = [f for f in findings if f.code in ("MANIFEST_STALE", "CATALOG_UNKNOWN")]
    clean = len(blocking) == 0
    model = getattr(judge_client, "_model", _DEFAULT_MODEL) if isinstance(judge_client, AnthropicJudgeClient) else None
    return findings, clean, model
