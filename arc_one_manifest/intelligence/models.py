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

    def to_wire_dict(self) -> dict[str, Any]:
        """La evidencia que sale del repositorio: **archivo y línea, nunca el código.**

        🔴 WS180 · decisión de Tomás. El `snippet` es la línea de código cruda, y los
        extractores apuntan justo a las líneas que matchean `SECRET|TOKEN|PASSWORD`: un
        secreto escrito a mano terminaba **en texto plano en la base de Arc One**. El doc 16a
        promete, con todas las letras, que *el código nunca sale del repositorio del cliente*
        — y esa promesa se dice en una sala con un banco enfrente.

        Sacarlo no cuesta nada hoy: se verificó que el `snippet` **no se muestra en ninguna
        pantalla, ni en el comment del PR, ni en el copy de los Hallazgos**. Se guardaba y no
        se leía. Y lo accionable sin él ya está definido por la propia fase: cuando no hay
        nombre, lo accionable es **`archivo:línea`** (regla 13 · WS179).

        Sigue viviendo en el artefacto JSON local del CI del cliente, que nunca sale de su
        repositorio: el recorte es del cable, no del análisis.
        """
        return {"file": self.file, "line": self.line}


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

    def to_wire_dict(self) -> dict[str, Any]:
        """La señal como viaja a Arc One: sin el código fuente. Ver ``Evidence.to_wire_dict``."""
        out = asdict(self)
        out["evidence"] = self.evidence.to_wire_dict()
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
    judge_model: str | None = None
    # 🔴 Cuánto miró este audit. ``clean`` sin esto es ambiguo: "no encontré nada" y "no
    # busqué en casi ningún lado" se leen igual. Quien redacte para un humano lo necesita.
    scan_all: bool = False
    # 🔴 Las otras dos mitades del "cuánto miró" (WS180). `scan_all` dice la INTENCIÓN;
    # estos dos dicen el HECHO:
    #   - `files_scanned`: cuántos archivos se abrieron de verdad. **Cero señales tras abrir
    #     200 archivos es limpieza; cero señales tras abrir CERO archivos es ceguera**, y sin
    #     este número el servidor no puede distinguirlos — y `full` lo autoriza a archivar.
    #   - `excludes`: qué recortó el usuario por debajo del alcance. El día que alguien suma
    #     una exclusión, esa primera corrida archivaría lo que vivía ahí sin haberlo abierto.
    files_scanned: int = 0
    excludes: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        out = {
            "manifestPath": self.manifest_path,
            "baseRef": self.base_ref,
            "staticOnly": self.static_only,
            "manifestSummary": self.manifest_summary.to_dict(),
            "codeSignals": [s.to_dict() for s in self.code_signals],
            "findings": [f.to_dict() for f in self.findings],
            "clean": self.clean,
            # El artefacto JSON hereda la misma honestidad que el markdown: sin alcance,
            # `clean` es una afirmación sin sujeto.
            "scanAll": self.scan_all,
            "filesScanned": self.files_scanned,
            "excludes": list(self.excludes),
        }
        if self.judge_model:
            out["judgeModel"] = self.judge_model
        return out
