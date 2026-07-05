#!/usr/bin/env python3
"""Arc One Manifest CLI — validate · gate · register · audit."""
from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

from arc_one_manifest.gate import validate_gate, write_bump
from arc_one_manifest.intelligence.audit import report_to_json, report_to_markdown, run_audit
from arc_one_manifest.intelligence.generate import (
    report_to_json as generation_report_to_json,
    run_generate,
    write_generate_outputs,
)
from arc_one_manifest.intelligence.generate import _manifest_yaml_with_header
from arc_one_manifest.intelligence.reporter import report_to_pr_comment
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


def _cmd_audit(args: argparse.Namespace) -> None:
    static_only = args.static_only
    has_platform = bool(
        os.environ.get("ARC_ONE_API_BASE_URL", "").strip()
        and os.environ.get("ARC_ONE_BEARER_TOKEN", "").strip()
    )
    if not static_only and not has_platform and not os.environ.get("ARC_ONE_LLM_API_KEY", "").strip():
        static_only = True

    try:
        report = run_audit(
            args.manifest,
            repo=args.repo,
            base_ref=args.base,
            static_only=static_only,
            min_confidence=args.min_confidence,
            scan_all=args.scan_all,
        )
    except ValueError as exc:
        print(str(exc), file=sys.stderr)
        raise SystemExit(2) from exc

    if args.format == "json":
        payload = report_to_json(report)
    elif args.format == "pr-comment":
        payload = report_to_pr_comment(report)
    else:
        payload = report_to_markdown(report)

    if args.output:
        with open(args.output, "w", encoding="utf-8") as fh:
            fh.write(payload)
            if not payload.endswith("\n"):
                fh.write("\n")
    else:
        print(payload)

    if report.clean:
        return

    if args.warn_only:
        return

    codes = {f.code for f in report.findings}
    fail_on = set(args.fail_on or [])
    if fail_on and codes.intersection(fail_on):
        raise SystemExit(1)
    if not fail_on:
        raise SystemExit(1)


def _cmd_generate(args: argparse.Namespace) -> None:
    try:
        manifest, report = run_generate(args.repo, profile=args.profile, skip_llm=args.skip_llm)
    except ValueError as exc:
        print(str(exc), file=sys.stderr)
        raise SystemExit(2) from exc

    yaml_text = _manifest_yaml_with_header(manifest, confidence=report.confidence, profile=report.profile)

    if args.dry_run:
        print(yaml_text)
        print("---")
        print(generation_report_to_json(report))
        return

    output = Path(args.output)
    report_path = Path(args.report)
    write_generate_outputs(manifest, report, output=output, report_path=report_path)
    print(f"Generated {output} (confidence {report.confidence:.0%}, profile {report.profile})")
    print(f"Report: {report_path}")
    if not report.validation.get("ok"):
        print("Validation: pending TODO fields — complete before register.", file=sys.stderr)


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

    p_audit = sub.add_parser(
        "audit",
        help="Detect code ↔ manifest drift (Manifest Intelligence · static layer)",
    )
    p_audit.add_argument("manifest", nargs="?", default="arc-one.agent.yaml")
    p_audit.add_argument("--repo", default=".", help="Repo root to scan")
    p_audit.add_argument("--base", default="origin/main", help="Git base ref for diff")
    p_audit.add_argument("--scan-all", action="store_true", help="Scan all scoped files, not just git diff")
    p_audit.add_argument(
        "--static-only",
        action="store_true",
        default=False,
        help="Skip LLM judge (default: use judge when ARC_ONE_LLM_API_KEY is set)",
    )
    p_audit.add_argument("--min-confidence", type=float, default=0.85)
    p_audit.add_argument("--format", choices=("json", "markdown", "pr-comment"), default="markdown")
    p_audit.add_argument("--output", "-o", default="")
    p_audit.add_argument(
        "--warn-only",
        action="store_true",
        default=True,
        help="Exit 0 even when findings exist (default)",
    )
    p_audit.add_argument(
        "--fail-on",
        action="append",
        default=[],
        help="Finding codes that fail CI (e.g. MANIFEST_STALE). Implies --no-warn-only when matched.",
    )
    p_audit.add_argument("--no-warn-only", dest="warn_only", action="store_false")
    p_audit.set_defaults(func=_cmd_audit)

    p_gen = sub.add_parser("generate", help="Bootstrap arc-one.agent.yaml from repo scan")
    p_gen.add_argument("--repo", default=".", help="Repo root to scan")
    p_gen.add_argument("--output", default="arc-one.agent.yaml")
    p_gen.add_argument("--report", default="manifest-generation-report.json")
    p_gen.add_argument("--profile", default="auto", help="Stack profile (auto, generic, python-aws-ecs)")
    p_gen.add_argument("--skip-llm", action="store_true", default=True)
    p_gen.add_argument("--dry-run", action="store_true", help="Print to stdout, do not write files")
    p_gen.set_defaults(func=_cmd_generate)

    args = ap.parse_args(argv)
    args.func(args)


if __name__ == "__main__":
    main()
