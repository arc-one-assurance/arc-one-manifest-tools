"""Tipos compartidos de Manifest Intelligence."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Literal

FindingCode = Literal[
    "MANIFEST_STALE",
    "MANIFEST_OVER_DECLARED",
    "MANIFEST_MISMATCH",
    "UNCERTAIN",
    "CATALOG_UNKNOWN",
]

SignalKind = Literal[
    "data_store",
    "integration_endpoint",
    "mcp_server",
    "secret",
    "model_hint",
    "knowledge_base",
]


@dataclass
class Evidence:
    file: str
    line: int
    snippet: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class CodeSignal:
    kind: SignalKind
    inferred_id: str
    confidence: float
    evidence: Evidence
    manifest_section: str

    def to_dict(self) -> dict[str, Any]:
        out = asdict(self)
        out["evidence"] = self.evidence.to_dict()
        return out


@dataclass
class AuditFinding:
    code: FindingCode
    severity: Literal["high", "medium", "low"]
    confidence: float
    title: str
    detail: str
    manifest_section: str
    suggested_catalog_id: str
    evidence: list[Evidence] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "code": self.code,
            "severity": self.severity,
            "confidence": self.confidence,
            "title": self.title,
            "detail": self.detail,
            "manifestSection": self.manifest_section,
            "suggestedCatalogId": self.suggested_catalog_id,
            "evidence": [e.to_dict() for e in self.evidence],
        }


@dataclass
class ManifestSummary:
    agent_model: str | None
    data_stores: set[str]
    integration_endpoints: set[str]
    secrets_required: set[str]
    mcp_servers: set[str]
    knowledge_bases: set[str]

    def to_dict(self) -> dict[str, Any]:
        return {
            "agentModel": self.agent_model,
            "dataStores": sorted(self.data_stores),
            "integrationEndpoints": sorted(self.integration_endpoints),
            "secretsRequired": sorted(self.secrets_required),
            "mcpServers": sorted(self.mcp_servers),
            "knowledgeBases": sorted(self.knowledge_bases),
        }


@dataclass
class AuditReport:
    manifest_path: str
    base_ref: str
    static_only: bool
    manifest_summary: ManifestSummary
    code_signals: list[CodeSignal]
    findings: list[AuditFinding]
    clean: bool

    def to_dict(self) -> dict[str, Any]:
        return {
            "manifestPath": self.manifest_path,
            "baseRef": self.base_ref,
            "staticOnly": self.static_only,
            "manifestSummary": self.manifest_summary.to_dict(),
            "codeSignals": [s.to_dict() for s in self.code_signals],
            "findings": [f.to_dict() for f in self.findings],
            "clean": self.clean,
        }
