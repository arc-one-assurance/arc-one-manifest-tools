"""Señales desde código Python (regex + heurísticas ligeras)."""

from __future__ import annotations

import re

from arc_one_manifest.intelligence.models import CodeSignal, Evidence

_BOTO3_CLIENT = re.compile(
    r"""boto3\.client\s*\(\s*['"]([a-zA-Z0-9_-]+)['"]""",
)
_BOTO3_RESOURCE = re.compile(
    r"""boto3\.resource\s*\(\s*['"]([a-zA-Z0-9_-]+)['"]""",
)
_HTTP_URL = re.compile(r"""https?://[^\s'"]+""")

_BOTO_SERVICE_MAP: dict[str, tuple[str, float]] = {
    "dynamodb": ("dynamodb", 0.92),
    "s3": ("aws-s3", 0.9),
    "rds": ("postgresql", 0.75),
    "secretsmanager": ("aws-secrets-manager", 0.88),
    "sqs": ("aws-sqs", 0.7),
    "sns": ("aws-sns", 0.7),
}

_MCP_PATTERNS = (
    re.compile(r"""mcp[_-]?server[s]?['"]?\s*[:=]\s*['"]([^'"]+)['"]""", re.I),
    re.compile(r"""mcp\.connect\s*\(\s*['"]([^'"]+)['"]""", re.I),
)


def _append(
    signals: list[CodeSignal],
    seen: set[tuple[str, str, str]],
    *,
    kind: str,
    inferred_id: str,
    confidence: float,
    section: str,
    path: str,
    line_no: int,
    snippet: str,
) -> None:
    key = (kind, inferred_id, path)
    if key in seen:
        return
    seen.add(key)
    signals.append(
        CodeSignal(
            kind=kind,  # type: ignore[arg-type]
            inferred_id=inferred_id,
            confidence=confidence,
            evidence=Evidence(file=path, line=line_no, snippet=snippet[:160]),
            manifest_section=section,
        )
    )


def extract_python_ast_signals(path: str, lines: list[str]) -> list[CodeSignal]:
    signals: list[CodeSignal] = []
    seen: set[tuple[str, str, str]] = set()

    for idx, raw in enumerate(lines, start=1):
        line = raw.strip()
        if not line or line.startswith("#"):
            continue

        for match in _BOTO3_CLIENT.finditer(line):
            service = match.group(1).lower()
            mapped = _BOTO_SERVICE_MAP.get(service, (service, 0.8))
            inferred_id, confidence = mapped
            _append(
                signals,
                seen,
                kind="data_store",
                inferred_id=inferred_id,
                confidence=confidence,
                section="data_stores",
                path=path,
                line_no=idx,
                snippet=line,
            )

        for match in _BOTO3_RESOURCE.finditer(line):
            service = match.group(1).lower()
            mapped = _BOTO_SERVICE_MAP.get(service, (service, 0.78))
            inferred_id, confidence = mapped
            _append(
                signals,
                seen,
                kind="data_store",
                inferred_id=inferred_id,
                confidence=confidence,
                section="data_stores",
                path=path,
                line_no=idx,
                snippet=line,
            )

        if "pinecone" in line.lower() and ("Index" in line or "Pinecone" in line):
            _append(
                signals,
                seen,
                kind="data_store",
                inferred_id="pinecone",
                confidence=0.88,
                section="data_stores",
                path=path,
                line_no=idx,
                snippet=line,
            )

        for pattern in _MCP_PATTERNS:
            mcp_match = pattern.search(line)
            if mcp_match:
                slug = re.sub(r"[^a-z0-9-]+", "-", mcp_match.group(1).lower()).strip("-")
                _append(
                    signals,
                    seen,
                    kind="mcp_server",
                    inferred_id=slug or "custom-mcp",
                    confidence=0.85,
                    section="mcp_servers",
                    path=path,
                    line_no=idx,
                    snippet=line,
                )

        if "os.environ" in line or "process.env" in line:
            if re.search(r"API_KEY|SECRET|TOKEN", line, re.I):
                _append(
                    signals,
                    seen,
                    kind="secret",
                    inferred_id="runtime-secret",
                    confidence=0.72,
                    section="secrets_required",
                    path=path,
                    line_no=idx,
                    snippet=line,
                )

        for url_match in _HTTP_URL.finditer(line):
            url = url_match.group(0)
            if any(skip in url for skip in ("localhost", "127.0.0.1", "example.com")):
                continue
            slug = re.sub(r"^https?://", "", url).split("/")[0].lower()
            slug = re.sub(r"[^a-z0-9.-]+", "-", slug)[:48]
            _append(
                signals,
                seen,
                kind="integration_endpoint",
                inferred_id=slug or "http-endpoint",
                confidence=0.68,
                section="integration_endpoints",
                path=path,
                line_no=idx,
                snippet=line,
            )

    return signals
