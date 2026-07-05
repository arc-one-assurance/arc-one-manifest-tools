"""Detección de profile de stack para manifest bootstrap."""

from __future__ import annotations

from pathlib import Path

from arc_one_manifest.intelligence.extractors.python_deps import extract_python_deps_signals
from arc_one_manifest.intelligence.git_diff import DEFAULT_EXCLUDE, DEFAULT_INCLUDE, list_repo_files, read_file_lines


def _file_has_token(repo: Path, token: str) -> bool:
    token_l = token.lower()
    for file_path in list_repo_files(repo, DEFAULT_INCLUDE, DEFAULT_EXCLUDE):
        rel = file_path.relative_to(repo).as_posix().lower()
        if token_l in rel:
            return True
        lines = read_file_lines(file_path)
        if any(token_l in line.lower() for line in lines[:200]):
            return True
    return False


def _has_boto3(repo: Path) -> bool:
    for file_path in list_repo_files(repo, DEFAULT_INCLUDE, DEFAULT_EXCLUDE):
        rel = file_path.relative_to(repo).as_posix().lower()
        if "requirements" in rel or rel == "pyproject.toml":
            signals = extract_python_deps_signals(rel, read_file_lines(file_path))
            if any(s.inferred_id == "aws-sdk" for s in signals):
                return True
    return False


def detect_profile(repo: Path, requested: str = "auto") -> str:
    if requested != "auto":
        return requested

    has_docker = _file_has_token(repo, "dockerfile")
    has_ecs = _file_has_token(repo, "ecs") or _file_has_token(repo, "fargate")
    has_boto3 = _has_boto3(repo)

    if has_docker and (has_boto3 or has_ecs):
        return "python-aws-ecs"

    if _file_has_token(repo, "fastapi"):
        return "python-fastapi-local"

    return "generic"


PROFILE_DEFAULTS: dict[str, dict[str, str]] = {
    "python-aws-ecs": {
        "deployment_target": "ecs/fargate/aws",
        "framework": "anthropic/claude-agent-sdk",
    },
    "python-fastapi-local": {
        "deployment_target": "custom/internal-infra",
        "framework": "fastapi",
    },
    "generic": {
        "deployment_target": "custom/internal-infra",
        "framework": "custom",
    },
}
