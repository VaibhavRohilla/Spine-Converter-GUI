"""Headless CLI adapter over the shared inspection and version APIs."""

from __future__ import annotations

import argparse
import json
import os
import sys
import tempfile
from pathlib import Path
from typing import Any

from .conversion import AtlasConverter, ConversionPlanner, SkeletonConverter, SourceRiskPolicy
from .conversion.runtime import run_spine_runtime_smoke
from .inspection import InspectionService
from .versions import VersionRegistry


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="spine-forge")
    sub = parser.add_subparsers(dest="command", required=True)
    inspect = sub.add_parser("inspect", help="Inspect a ZIP or folder")
    inspect.add_argument("source")
    inspect.add_argument("--json", action="store_true", dest="json_output")
    inspect.add_argument("--strict", action="store_true")
    sub.add_parser("versions", help="List recognized Spine version families")
    plan = sub.add_parser("plan", help="Check for a registered migration route")
    plan.add_argument("--from-version", required=True)
    plan.add_argument("--to-version", required=True)
    runtime_smoke = sub.add_parser(
        "runtime-smoke",
        help="Load and evaluate a converted bundle with an exact official Spine runtime",
    )
    runtime_smoke.add_argument("--skeleton", required=True)
    runtime_smoke.add_argument("--atlas", required=True)
    runtime_smoke.add_argument("--runtime-package", required=True)
    convert = sub.add_parser("convert", help="Convert a standalone JSON skeleton or atlas")
    kinds = convert.add_subparsers(dest="kind", required=True)
    for kind in ("skeleton", "atlas"):
        command = kinds.add_parser(kind)
        command.add_argument("--input", required=True)
        command.add_argument("--target", required=True)
        command.add_argument("--source-version")
        command.add_argument("--output")
        command.add_argument("--dry-run", action="store_true")
        if kind == "skeleton":
            command.add_argument(
                "--allow-known-source-export-risk",
                action="store_true",
                help="Allow Spine 3.8.75 conversion while recording SOURCE_EXPORT_KNOWN_BUG",
            )
    args = parser.parse_args(argv)
    if args.command == "versions":
        print(json.dumps([v.family for v in VersionRegistry().definitions()], indent=2))
        return 0
    if args.command == "inspect":
        result = InspectionService().inspect(args.source)
        if args.json_output:
            print(json.dumps(result.to_dict(), ensure_ascii=False, sort_keys=True, indent=2))
        else:
            print(
                f"Source: {result.source}\n"
                f"Assets: {result.summary.get('assets', 0)} | "
                f"Skeletons: {result.summary.get('skeletons', 0)} | "
                f"Atlases: {result.summary.get('atlases', 0)} | "
                f"Textures: {result.summary.get('textures', 0)}"
            )
            print(
                "Versions: "
                + (
                    ", ".join(sorted({a.spine_version for a in result.assets if a.spine_version}))
                    or "unknown"
                )
            )
            for b in result.bundles:
                print(
                    f"Bundle {b.bundle_id}: skeletons={len(b.skeletons)} "
                    f"atlases={len(b.atlases)} pages={len(b.texture_pages)}"
                )
            for d in result.diagnostics:
                print(
                    f"{d.severity.value.upper()} {d.code}: {d.message}"
                    + (f" [{d.path}]" if d.path else "")
                )
        return (
            2
            if not result.ok
            or (args.strict and any(d.severity.value == "warning" for d in result.diagnostics))
            else 0
        )
    if args.command == "plan":
        planned = ConversionPlanner(
            {(f, f) for f in ("3.5", "3.6", "3.7", "3.8", "4.0", "4.1", "4.2", "4.3")}
            | {
                ("3.8.75", "4.2.43"),
                ("3.8.99", "4.2.43"),
                ("3.8.75", "4.1.56"),
                ("3.8.99", "4.1.56"),
                ("3.8.75", "4.0.31"),
                ("3.8.99", "4.0.31"),
                ("3.8.75", "4.3.13"),
                ("3.8.99", "4.3.13"),
                ("3.8.75", "3.7.94"),
                ("3.8.99", "3.7.94"),
                ("3.8.75", "3.6.53"),
                ("3.8.99", "3.6.53"),
                ("3.8.75", "3.5.51"),
                ("3.8.99", "3.5.51"),
                ("4.2.43", "4.3.13"),
                ("4.1.56", "4.2.43"),
                ("4.0.31", "4.1.56"),
                ("3.7.94", "3.8.99"),
                ("3.6.53", "3.7.94"),
                ("3.5.51", "3.6.53"),
                ("4.3.13", "4.2.43"),
                ("4.2.43", "4.1.56"),
                ("4.1.56", "4.0.31"),
                ("4.0.31", "3.8.99"),
                ("3.7.94", "3.6.53"),
                ("3.6.53", "3.5.51"),
            }
        ).plan(args.from_version, args.to_version)
        print(
            json.dumps(
                {
                    "executable": planned.executable,
                    "route": planned.route,
                    "diagnostics": planned.diagnostics,
                },
                indent=2,
            )
        )
        return 0 if planned.executable else 2
    if args.command == "runtime-smoke":
        runtime_report = run_spine_runtime_smoke(
            args.skeleton, args.atlas, args.runtime_package
        )
        print(json.dumps(runtime_report, ensure_ascii=False, sort_keys=True, indent=2))
        return 0 if runtime_report.get("status") == "animation_state_evaluated" else 2
    if args.kind == "skeleton":
        outcome = SkeletonConverter().convert(
            args.input,
            args.target,
            source_risk_policy=(
                SourceRiskPolicy.ALLOW_WITH_DIAGNOSTIC
                if args.allow_known_source_export_risk
                else SourceRiskPolicy.REJECT_KNOWN_ISSUES
            ),
        )
        report: dict[str, Any] = {
            "status": outcome.status.value,
            "source_version": outcome.source_version,
            "target_version": outcome.target_version,
            "route": outcome.route,
            "diagnostics": outcome.diagnostics,
            "statistics": outcome.statistics,
            "details": outcome.details,
            "unsupported_features": outcome.unsupported_features,
            "runtime_verified": outcome.runtime_verified,
            "visually_verified": outcome.visually_verified,
            "diagnostic_codes": outcome.diagnostic_codes,
            "provenance": outcome.provenance,
            "feature_compatibility": outcome.feature_compatibility,
        }
        if outcome.output is not None and not args.dry_run:
            if not args.output:
                parser.error("convert skeleton requires --output unless --dry-run is used")
            _atomic_write(Path(args.output), outcome.output)
        print(json.dumps(report, indent=2))
        return 0 if outcome.output is not None else 2
    try:
        atlas_output = AtlasConverter().convert(
            args.input, args.target, source_version=args.source_version
        )
        atlas_model = AtlasConverter().read(atlas_output)
        report = {
            "status": "structurally_verified",
            "source_version": args.source_version,
            "target_version": args.target,
            "pages": len(atlas_model.pages),
            "regions": len(atlas_model.regions),
            "structural_verification": "passed",
            "diagnostics": [],
        }
        if not args.dry_run:
            if not args.output:
                parser.error("convert atlas requires --output unless --dry-run is used")
            _atomic_write(Path(args.output), atlas_output)
    except (OSError, ValueError, UnicodeError) as exc:
        report = {"status": "rejected", "diagnostics": [str(exc)]}
        print(json.dumps(report, indent=2))
        return 2
    print(json.dumps(report, indent=2))
    return 0


def _atomic_write(path: Path, content: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    try:
        with os.fdopen(fd, "wb") as stream:
            stream.write(content)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    except BaseException:
        try:
            os.unlink(temporary)
        except FileNotFoundError:
            pass
        raise


if __name__ == "__main__":
    sys.exit(main())
