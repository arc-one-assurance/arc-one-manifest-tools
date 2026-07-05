#!/usr/bin/env python3
"""Arc One Manifest CLI — validate · gate · register."""
from __future__ import annotations

import argparse
import json
import os
import sys

from arc_one_manifest.gate import validate_gate, write_bump
from arc_one_manifest.loader import load_manifest
from arc_one_manifest.register import apply
from arc_one_manifest.validation import ManifestValidationError, validate_madre_manifest


def _cmd_validate(args: argparse.Namespace) -> None:
    manifest = load_manifest(args.manifest)
    try:
        validate_madre_manifest(
            manifest,
            allow_connector_placeholder=not args.no_placeholder,
            require_connector=not args.optional_connector,
        )
    except ManifestValidationError as exc:
        print(str(exc), file=sys.stderr)
        raise SystemExit(1) from exc
    name = manifest.get("name", "?")
    version = manifest.get("agent_version") or manifest.get("agentVersion") or "?"
    mv = manifest.get("manifest_version") or manifest.get("manifestVersion") or "?"
    print(f"Manifest OK · v1.1/v1.2 · {name} · {version} (manifest {mv})")


def _cmd_gate(args: argparse.Namespace) -> None:
    if args.write_bump:
        write_bump(args.manifest, args.write_bump)
        return
    validate_gate(
        args.manifest,
        base_url=os.environ.get("ARC_ONE_API_BASE_URL", "http://127.0.0.1:8000"),
        agent_id=args.agent_id.strip() or None,
        token=os.environ.get("ARC_ONE_BEARER_TOKEN", ""),
        debug_sub=os.environ.get("ARC_ONE_DEBUG_SUB", ""),
        suggest_only=args.suggest_bump,
    )


def _cmd_register(args: argparse.Namespace) -> None:
    apply(
        args.manifest,
        base_url=os.environ.get("ARC_ONE_API_BASE_URL", "http://127.0.0.1:8000"),
        dry_run=args.dry_run,
        token=os.environ.get("ARC_ONE_BEARER_TOKEN", ""),
        debug_sub=os.environ.get("ARC_ONE_DEBUG_SUB", ""),
    )


def _cmd_suggest_bump(args: argparse.Namespace) -> None:
    validate_gate(
        args.manifest,
        base_url=os.environ.get("ARC_ONE_API_BASE_URL", "http://127.0.0.1:8000"),
        agent_id=args.agent_id.strip() or None,
        token=os.environ.get("ARC_ONE_BEARER_TOKEN", ""),
        debug_sub=os.environ.get("ARC_ONE_DEBUG_SUB", ""),
        suggest_only=True,
    )


def main(argv: list[str] | None = None) -> None:
    ap = argparse.ArgumentParser(
        prog="arc-one-manifest",
        description="Arc One manifest bridge — validate, CI gate and registration",
    )
    ap.add_argument("--version", action="version", version=f"%(prog)s {__import__('arc_one_manifest.__version__', fromlist=['__version__']).__version__}")
    sub = ap.add_subparsers(dest="command", required=True)

    p_val = sub.add_parser("validate", help="Validate MADRE v1.1 structure")
    p_val.add_argument("manifest", nargs="?", default="arc-one.agent.yaml")
    p_val.add_argument("--no-placeholder", action="store_true")
    p_val.add_argument("--optional-connector", action="store_true")
    p_val.set_defaults(func=_cmd_validate)

    p_gate = sub.add_parser("gate", help="Drift check + semver bump enforcement")
    p_gate.add_argument("manifest", nargs="?", default="arc-one.agent.yaml")
    p_gate.add_argument("--suggest-bump", action="store_true")
    p_gate.add_argument("--write-bump", choices=("patch", "minor", "major"))
    p_gate.add_argument("--agent-id", default=os.environ.get("ARC_ONE_AGENT_ID", ""))
    p_gate.set_defaults(func=_cmd_gate)

    p_reg = sub.add_parser("register", help="Register manifest with Arc One API")
    p_reg.add_argument("manifest", nargs="?", default="arc-one.agent.yaml")
    p_reg.add_argument("--dry-run", action="store_true")
    p_reg.set_defaults(func=_cmd_register)

    p_sug = sub.add_parser("suggest-bump", help="Print suggested semver bump as JSON")
    p_sug.add_argument("manifest", nargs="?", default="arc-one.agent.yaml")
    p_sug.add_argument("--agent-id", default=os.environ.get("ARC_ONE_AGENT_ID", ""))
    p_sug.set_defaults(func=_cmd_suggest_bump)

    args = ap.parse_args(argv)
    args.func(args)


if __name__ == "__main__":
    main()
