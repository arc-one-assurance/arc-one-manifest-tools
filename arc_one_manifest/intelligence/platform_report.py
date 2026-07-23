"""Reportar el audit de código a Arc One (Arc Scanner · Fase 2 · Card 5 · doc 16a §5c).

Hasta acá el audit moría en el CI: el juez contestaba, el comment del PR lo pintaba y Arc
One no se quedaba con nada. Esto es la mitad del cliente de ese cambio: el CLI **postea el
resultado** al endpoint con estado y **recibe la triangulación** para pintarla donde el
cliente la lee.

Dos reglas gobiernan este módulo, y las dos vienen de tropezones propios:

🔴 **El scope se manda honesto.** ``full`` sólo si el audit corrió con ``--scan-all``;
``diff`` si miró los archivos del cambio contra un base ref. El CLI es el único que sabe
cuánto miró, y del otro lado ese dato decide si el audit puede **archivar** Hallazgos. Un
``full`` mentido cerraría como resueltos hallazgos de archivos que nadie abrió.

🔴 **Si el reporte no se entrega, se dice fuerte — y NO se rompe el CI.** Arc One es
declarativo: detecta y avisa, no frena merges (decisión 4 de §7). Pero *jamás en silencio*:
es exactamente el patrón del juez que caía a estático sin avisar y hacía que un "todo en
orden" fuera indistinguible de un "no pude mirar". Por eso nada de acá levanta una
excepción hacia arriba: se devuelve un ``ReportOutcome`` con el motivo, y el motivo termina
en el log **y** en el comment del PR.
"""

from __future__ import annotations

import os
import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, Optional

import httpx

from arc_one_manifest.canonical import canonical_name
from arc_one_manifest.intelligence.models import AuditReport
from arc_one_manifest.register import ci_provenance_headers

SCOPE_FULL = "full"
SCOPE_DIFF = "diff"

_TIMEOUT_S = 60.0


@dataclass
class ReportOutcome:
    """Qué pasó con la entrega. ``delivered=False`` **siempre** trae ``reason``."""

    delivered: bool
    reason: Optional[str] = None
    agent_id: Optional[str] = None
    report_id: Optional[str] = None
    triangulation: Dict[str, Any] = field(default_factory=dict)


def resolve_scope(*, scan_all: bool) -> str:
    """``full`` sólo si se miró el repo entero. El CLI no puede mentir sobre esto.

    Del otro lado, ``manifest_audit_reconcile_allowed`` usa este valor para decidir si el
    audit tiene derecho a archivar Hallazgos que ya no ve. *Lo que no se miró no es lo que
    dejó de existir.*
    """
    return SCOPE_FULL if scan_all else SCOPE_DIFF


def _commit_sha(repo: str) -> Optional[str]:
    """El commit auditado. Del CI si está; si no, del git local; si no, nada."""
    env = (os.environ.get("GITHUB_SHA") or os.environ.get("ARC_ONE_COMMIT_SHA") or "").strip()
    if env:
        return env[:64]
    try:
        proc = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=repo,
            capture_output=True,
            text=True,
            check=False,
        )
    except OSError:
        return None
    sha = proc.stdout.strip()
    return sha[:64] if proc.returncode == 0 and sha else None


def _manifest_changed_in_pr(repo: str, manifest_path: str, base_ref: str) -> bool:
    """¿El cambio tocó el propio Manifiesto?

    No es cosmético: explica por sí solo una diferencia entre el YAML del repo y lo
    registrado en Arc One (*"lo cambiaste y todavía no lo registraste"*). Sin este dato, esa
    divergencia parece un descuido cuando puede ser un cambio en curso.

    🔴 **Se pregunta a git directamente, a propósito.** El `changed_files` del audit cae a
    *"listar el repo entero"* cuando git falla (checkout shallow, sin base ref) — que es lo
    correcto para escanear, y **exactamente lo contrario** de lo correcto para esta pregunta:
    haría que el manifiesto "cambió siempre". Acá, no poder averiguarlo es ``False``: no
    afirmamos un hecho que no comprobamos.
    """
    try:
        root = Path(repo).resolve()
        target = (root / manifest_path).resolve()
    except OSError:
        return False
    try:
        proc = subprocess.run(
            ["git", "diff", "--name-only", f"{base_ref}...HEAD"],
            cwd=root,
            capture_output=True,
            text=True,
            check=False,
        )
    except OSError:
        return False
    if proc.returncode != 0:
        return False
    for line in proc.stdout.splitlines():
        rel = line.strip()
        if not rel:
            continue
        try:
            if (root / rel).resolve() == target:
                return True
        except OSError:  # pragma: no cover — rutas raras del diff
            continue
    return False


def _headers(token: str, debug_sub: str) -> Dict[str, str]:
    headers: Dict[str, str] = {"Authorization": f"Bearer {token}"}
    if debug_sub:
        headers["X-ArcOne-Debug-Sub"] = debug_sub
    # De qué repo y qué corrida viene: la ÚNICA señal de vida de la conexión de repos.
    headers.update(ci_provenance_headers())
    return headers


def resolve_agent_id(
    *,
    base_url: str,
    token: str,
    debug_sub: str,
    explicit: str = "",
    manifest: Optional[Dict[str, Any]] = None,
) -> tuple[Optional[str], Optional[str]]:
    """``(agent_id, motivo_del_fallo)``. **Nunca levanta**: acá un fallo no rompe el CI.

    Orden: lo explícito → la variable de entorno → el ``agent_id`` del manifiesto exportado
    → resolver por nombre canónico contra ``/api/agentes``. Es el mismo orden del
    ``gate``, sin su ``SystemExit``: el gate **es** una compuerta, esto es un reporte.

    🔴 El canónico se **deriva de ``name``** con la regla compartida de
    ``arc_one_manifest.canonical`` — la misma que usa el ``gate`` y la misma que el
    platform aplica al registrar. Buscarlo como clave ``nombre_canonico`` del YAML
    (como hacía esta función) no encuentra nada nunca: el Manifiesto MADRE no la tiene.
    """
    candidate = (explicit or os.environ.get("ARC_ONE_AGENT_ID", "")).strip()
    if candidate:
        return candidate, None

    manifest = manifest or {}
    from_manifest = str(manifest.get("agent_id") or manifest.get("agentId") or "").strip()
    if from_manifest:
        return from_manifest, None

    canonico = canonical_name(manifest)
    if not canonico:
        return None, (
            "no se pudo determinar a qué agente pertenece este repositorio: el "
            "Manifiesto no declara `name`. Pasá `--agent-id` (o `ARC_ONE_AGENT_ID`)."
        )

    try:
        res = httpx.get(
            f"{base_url.rstrip('/')}/api/agentes",
            headers=_headers(token, debug_sub),
            timeout=_TIMEOUT_S,
        )
    except httpx.HTTPError as exc:
        return None, f"no se pudo consultar la lista de agentes: {exc}"

    if res.status_code == 401:
        return None, "401 Unauthorized — el `ARC_ONE_BEARER_TOKEN` no es válido en esta API."
    if res.status_code != 200:
        return None, f"la lista de agentes respondió {res.status_code}."

    try:
        agents = res.json()
    except ValueError:
        return None, "la lista de agentes no devolvió JSON."

    match = next(
        (a for a in agents if isinstance(a, dict) and a.get("nombreCanonico") == canonico),
        None,
    )
    if not match:
        return None, (
            f"el agente `{canonico}` no está registrado en este workspace. "
            "Registralo antes de reportar el audit."
        )
    return str(match.get("id") or "") or None, None


def report_audit_to_platform(
    report: AuditReport,
    *,
    repo: str,
    base_url: str,
    token: str,
    scope: str,
    agent_id: str = "",
    debug_sub: str = "",
    repo_manifest: Optional[Dict[str, Any]] = None,
) -> ReportOutcome:
    """Postea el audit y devuelve la triangulación. **Nunca levanta una excepción.**"""
    if not base_url.strip() or not token.strip():
        return ReportOutcome(
            delivered=False,
            reason=(
                "faltan `ARC_ONE_API_BASE_URL` y/o `ARC_ONE_BEARER_TOKEN` — el audit corrió, "
                "pero Arc One no se enteró."
            ),
        )

    resolved, motivo = resolve_agent_id(
        base_url=base_url,
        token=token,
        debug_sub=debug_sub,
        explicit=agent_id,
        manifest=repo_manifest,
    )
    if not resolved:
        return ReportOutcome(delivered=False, reason=motivo)

    body = {
        "manifestSummary": report.manifest_summary.to_dict(),
        "codeSignals": [s.to_dict() for s in report.code_signals],
        "scope": scope,
        "commitSha": _commit_sha(repo),
        "manifestChangedInPr": _manifest_changed_in_pr(
            repo, report.manifest_path, report.base_ref
        ),
    }

    url = f"{base_url.rstrip('/')}/api/agentes/{resolved}/manifest-intelligence/audit-result"
    try:
        res = httpx.post(url, json=body, headers=_headers(token, debug_sub), timeout=_TIMEOUT_S)
    except httpx.HTTPError as exc:
        return ReportOutcome(delivered=False, reason=f"no se pudo entregar el reporte: {exc}", agent_id=resolved)

    if res.status_code == 404:
        return ReportOutcome(
            delivered=False,
            agent_id=resolved,
            reason=(
                f"el agente `{resolved}` no existe en este workspace (404). Revisá que el "
                "token y el id sean del mismo entorno."
            ),
        )
    if res.status_code not in (200, 201):
        return ReportOutcome(
            delivered=False,
            agent_id=resolved,
            reason=f"Arc One respondió {res.status_code}: {res.text[:300]}",
        )

    try:
        payload = res.json()
    except ValueError:
        return ReportOutcome(
            delivered=False,
            agent_id=resolved,
            reason="Arc One aceptó el reporte pero no devolvió JSON.",
        )

    return ReportOutcome(
        delivered=True,
        agent_id=resolved,
        report_id=str(payload.get("reportId") or "") or None,
        triangulation=payload if isinstance(payload, dict) else {},
    )
