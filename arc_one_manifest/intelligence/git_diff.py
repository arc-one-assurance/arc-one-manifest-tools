"""Scope y diff git para Manifest Intelligence."""

from __future__ import annotations

import fnmatch
import subprocess
from pathlib import Path

DEFAULT_INCLUDE = (
    "src/**",
    "app/**",
    "lib/**",
    "services/**",
    "infra/**",
    "terraform/**",
    "cdk/**",
    "scripts/**",
    "requirements*.txt",
    "pyproject.toml",
    "package.json",
    "Dockerfile",
    "docker-compose*.yml",
    ".env.example",
    "config/**",
    "prompts/**",
    "*prompt*",
    "system*.md",
    "arc-one.agent.yaml",
)

DEFAULT_EXCLUDE = (
    "tests/**",
    "test/**",
    "**/node_modules/**",
    "**/.venv/**",
    "**/dist/**",
    "**/build/**",
    "**/.next/**",
    "**/coverage/**",
    "**/*.lock",
    "**/pnpm-lock.yaml",
)


def _matches(path: str, patterns: tuple[str, ...]) -> bool:
    normalized = path.replace("\\", "/")
    return any(fnmatch.fnmatch(normalized, pat) for pat in patterns)


def _normalize_rel_path(path: str) -> str:
    normalized = path.replace("\\", "/")
    while normalized.startswith("./"):
        normalized = normalized[2:]
    return normalized


def in_scope(path: str, include: tuple[str, ...], exclude: tuple[str, ...]) -> bool:
    normalized = _normalize_rel_path(path)
    if not _matches(normalized, include):
        return False
    return not _matches(normalized, exclude)


def list_repo_files(repo: Path, include: tuple[str, ...], exclude: tuple[str, ...]) -> list[Path]:
    out: list[Path] = []
    for p in repo.rglob("*"):
        if not p.is_file():
            continue
        rel = p.relative_to(repo).as_posix()
        if in_scope(rel, include, exclude):
            out.append(p)
    return sorted(out)


def changed_files(repo: Path, base_ref: str, include: tuple[str, ...], exclude: tuple[str, ...]) -> list[Path]:
    """Archivos modificados entre base_ref y HEAD, filtrados por scope."""
    try:
        proc = subprocess.run(
            ["git", "diff", "--name-only", f"{base_ref}...HEAD"],
            cwd=repo,
            capture_output=True,
            text=True,
            check=False,
        )
    except OSError:
        return list_repo_files(repo, include, exclude)

    if proc.returncode != 0:
        return list_repo_files(repo, include, exclude)

    paths: list[Path] = []
    for line in proc.stdout.splitlines():
        rel = line.strip()
        if not rel or not in_scope(rel, include, exclude):
            continue
        full = repo / rel
        if full.is_file():
            paths.append(full)
    return sorted(paths)


def read_file_lines(path: Path) -> list[str]:
    try:
        return path.read_text(encoding="utf-8", errors="replace").splitlines()
    except OSError:
        return []
