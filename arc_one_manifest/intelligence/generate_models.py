"""Tipos para manifest bootstrap (generate)."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any


@dataclass
class FieldReport:
    value: Any
    confidence: float
    evidence: str = ""
    status: str = "ok"  # ok | TODO | inferred

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class GenerationReport:
    generated_at: str
    profile: str
    confidence: float
    fields: dict[str, FieldReport]
    validation: dict[str, Any]
    manifest_path: str | None = None
    report_path: str | None = None
    # Cuenta de nube detectada en el repo (sugerencia para `infra_binding`). `None` =
    # no se pudo leer ninguna: el bloque sale con placeholders, nunca inventada.
    infra_account_suggestion: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "generatedAt": self.generated_at,
            "profile": self.profile,
            "confidence": self.confidence,
            "fields": {k: v.to_dict() for k, v in self.fields.items()},
            "validation": self.validation,
            "manifestPath": self.manifest_path,
            "reportPath": self.report_path,
            "infraAccountSuggestion": self.infra_account_suggestion,
        }
