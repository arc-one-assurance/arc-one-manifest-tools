"""CI Gate — validate manifest drift + semver bump before Arc One registration."""
from __future__ import annotations

import copy
import hashlib
import json
import os
import re
import sys
from typing import Any, Dict, Optional, Tuple

import httpx
import yaml

from arc_one_manifest.material_paths import MATERIAL_PATHS
from arc_one_manifest.register import ci_provenance_headers

SEMVER_RE = re.compile(r"^(\d+)\.(\d+)\.(\d+)$")

# Back-compat alias — gate y manifest intelligence comparten el mismo set.
_MATERIAL_PATHS = MATERIAL_PATHS


def _load_yaml(path: str) -> Dict[str, Any]:
    with open(path, encoding="utf-8") as f:
        data = yaml.safe_load(f)
    if not isinstance(data, dict):
        raise SystemExit(f"{path}: manifest must be a YAML mapping")
    return data


def _normalize_for_drift(manifest: Dict[str, Any]) -> Dict[str, Any]:
    """Strip version-only / CI metadata before hashing."""
    m = copy.deepcopy(manifest)
    for key in (
        "agent_version",
        "agentVersion",
        "revalidation",
        "manifest_version",
        "agent_id",
        "agentId",
        "data_classes",
        "data_classes_effective",
    ):
        m.pop(key, None)
    purpose = m.get("purpose")
    if isinstance(purpose, str):
        m["purpose"] = purpose.rstrip("\n")
    sp = m.get("system_prompt")
    if isinstance(sp, dict) and isinstance(sp.get("content"), str):
        sp = dict(sp)
        sp["content"] = sp["content"].rstrip("\n")
        m["system_prompt"] = sp
    con = m.get("connector")
    if isinstance(con, dict):
        con = dict(con)
        con.pop("endpointUrl", None)
        m["connector"] = con
    return m


def _stable_hash(obj: Any) -> str:
    payload = json.dumps(obj, sort_keys=True, ensure_ascii=False, default=str)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _parse_semver(v: str) -> Tuple[int, int, int]:
    m = SEMVER_RE.match(v.strip())
    if not m:
        raise ValueError(f"invalid semver: {v!r}")
    return int(m.group(1)), int(m.group(2)), int(m.group(3))


def _format_semver(major: int, minor: int, patch: int) -> str:
    return f"{major}.{minor}.{patch}"


def _bump(current: str, level: str) -> str:
    major, minor, patch = _parse_semver(current)
    if level == "major":
        return _format_semver(major + 1, 0, 0)
    if level == "minor":
        return _format_semver(major, minor + 1, 0)
    return _format_semver(major, minor, patch + 1)


def _is_increment(prev: str, new: str) -> bool:
    try:
        p = _parse_semver(prev)
        n = _parse_semver(new)
    except ValueError:
        return False
    return n > p


def _binding_accounts(manifest: Dict[str, Any]) -> set:
    """Cuentas de nube declaradas en infra_binding (ignora el scope)."""
    raw = manifest.get("infra_binding") or manifest.get("infraBinding") or []
    if not isinstance(raw, list):
        return set()
    return {
        str(b.get("account") or "").strip()
        for b in raw
        if isinstance(b, dict) and str(b.get("account") or "").strip()
    }


def _suggest_bump_level(repo: Dict[str, Any], registered: Dict[str, Any]) -> str:
    """Heuristic bump suggestion for CI messages / --write-bump."""
    if (repo.get("agent_model") or "") != (registered.get("agent_model") or ""):
        return "major"
    for path in _MATERIAL_PATHS:
        if repo.get(path) != registered.get(path):
            return "minor"
    # Mudanza de infra = cambio de fondo. Cambiar de plataforma (deployment_target) o de
    # cuenta de nube implica otra credencial y otra frontera de seguridad → minor.
    # Reacomodar el scope DENTRO de la misma cuenta es un ajuste fino → patch.
    if (repo.get("deployment_target") or repo.get("deploymentTarget") or "") != (
        registered.get("deployment_target") or registered.get("deploymentTarget") or ""
    ):
        return "minor"
    if _binding_accounts(repo) != _binding_accounts(registered):
        return "minor"
    return "patch"


def _fetch_registered_manifest(
    *,
    base_url: str,
    agent_id: Optional[str],
    nombre_canonico: Optional[str],
    token: str,
    debug_sub: str,
) -> Optional[Dict[str, Any]]:
    headers: Dict[str, str] = {}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    if debug_sub:
        headers["X-ArcOne-Debug-Sub"] = debug_sub
    headers.update(ci_provenance_headers())

    if not agent_id and nombre_canonico:
        r = httpx.get(
            f"{base_url.rstrip('/')}/api/agentes",
            headers=headers,
            timeout=60.0,
        )
        if r.status_code == 401:
            raise SystemExit(
                "CI Gate FAIL: 401 Unauthorized — el ARC_ONE_BEARER_TOKEN no es válido "
                "en esta API (¿token creado en local pero secret apunta a prod?). "
                "Creá un token arc1_… en el sandbox desplegado → Configuración → API Keys."
            )
        if r.status_code != 200:
            print(r.text, file=sys.stderr)
            raise SystemExit(f"API error listing agents: {r.status_code}")
        agents = r.json()
        match = next(
            (a for a in agents if a.get("nombreCanonico") == nombre_canonico),
            None,
        )
        if match:
            agent_id = match["id"]

    if not agent_id:
        return None

    r = httpx.get(
        f"{base_url.rstrip('/')}/api/agentes/{agent_id}/manifest",
        headers=headers,
        timeout=60.0,
    )
    if r.status_code == 401:
        raise SystemExit(
            "CI Gate FAIL: 401 Unauthorized — ARC_ONE_BEARER_TOKEN inválido en esta API."
        )
    if r.status_code == 404:
        raise SystemExit(
            f"CI Gate FAIL: agent_id {agent_id!r} no existe en esta API. "
            "No uses un id de localhost en secrets de prod; omití ARC_ONE_AGENT_ID "
            "o usá el id del agente en el sandbox desplegado."
        )
    if r.status_code != 200:
        print(r.text, file=sys.stderr)
        raise SystemExit(f"API error fetching manifest: {r.status_code}")
    return r.json()


def _agent_id_from_manifest(manifest: Dict[str, Any]) -> Optional[str]:
    """Arc One export includes agent_id — prefer over env when present."""
    raw = str(manifest.get("agent_id") or manifest.get("agentId") or "").strip()
    if raw.startswith("arc-agent-"):
        return raw
    return None


def _canonical_name(manifest: Dict[str, Any]) -> str:
    name = str(manifest.get("name") or "").strip()
    if not name:
        raise SystemExit("manifest missing required field: name")
    import re
    import unicodedata

    s = name.lower()
    s = unicodedata.normalize("NFD", s)
    s = "".join(ch for ch in s if unicodedata.category(ch) != "Mn")
    s = re.sub(r"[^a-z0-9]+", "-", s)
    return re.sub(r"(^-+|-+$)", "", s) or "agent"


def validate_gate(
    path: str,
    *,
    base_url: str,
    agent_id: Optional[str],
    token: str,
    debug_sub: str,
    suggest_only: bool = False,
) -> None:
    repo_manifest = _load_yaml(path)
    repo_version = str(
        repo_manifest.get("agent_version") or repo_manifest.get("agentVersion") or ""
    ).strip()
    if not repo_version:
        raise SystemExit("manifest missing agent_version")

    resolved_agent_id = (
        agent_id
        or os.environ.get("ARC_ONE_AGENT_ID", "").strip()
        or _agent_id_from_manifest(repo_manifest)
        or None
    )
    registered = _fetch_registered_manifest(
        base_url=base_url,
        agent_id=resolved_agent_id,
        nombre_canonico=_canonical_name(repo_manifest),
        token=token,
        debug_sub=debug_sub,
    )

    if registered is None:
        print("CI Gate: agent not found in Arc One — first registration allowed.")
        return

    reg_version = str(registered.get("agent_version") or "").strip()
    repo_hash = _stable_hash(_normalize_for_drift(repo_manifest))
    reg_hash = _stable_hash(_normalize_for_drift(registered))

    if repo_hash == reg_hash:
        if repo_version != reg_version:
            raise SystemExit(
                f"CI Gate FAIL: manifest content unchanged but agent_version "
                f"({repo_version}) differs from registered ({reg_version}). "
                "Revert version bump or change manifest content."
            )
        print(f"CI Gate OK: no drift (still at {repo_version}).")
        return

    level = _suggest_bump_level(repo_manifest, registered)
    suggested = _bump(reg_version or repo_version, level)

    if suggest_only:
        print(json.dumps({"suggestedVersion": suggested, "bumpLevel": level}, indent=2))
        return

    if not _is_increment(reg_version, repo_version):
        raise SystemExit(
            f"CI Gate FAIL: manifest content changed but agent_version not bumped.\n"
            f"  Registered: {reg_version}\n"
            f"  In repo:    {repo_version}\n"
            f"  Suggested:  {suggested} ({level} bump)\n"
            f"  Run: arc-one-manifest gate {path} --write-bump {level}"
        )

    print(
        f"CI Gate OK: drift detected · {reg_version} → {repo_version} ({level}-level change)"
    )


def write_bump(path: str, level: str) -> None:
    manifest = _load_yaml(path)
    current = str(
        manifest.get("agent_version") or manifest.get("agentVersion") or "1.0.0"
    ).strip()
    new_ver = _bump(current, level)
    manifest["agent_version"] = new_ver
    manifest.pop("agentVersion", None)
    with open(path, "w", encoding="utf-8") as f:
        yaml.dump(manifest, f, allow_unicode=True, sort_keys=False, default_flow_style=False)
    print(f"Bumped agent_version: {current} → {new_ver}")

