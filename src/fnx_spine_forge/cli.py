"""Headless CLI adapter over the shared inspection and version APIs."""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import replace
from pathlib import Path

from .atomic_io import write_bytes_exclusive
from .binary import BinaryCodecRegistry
from .bundle import BundleService
from .bundle_models import (
    BundleRequest,
    PackageContainer,
    PackageMode,
    RetentionPolicy,
    SkeletonFormat,
)
from .conversion import (
    AssetSetConverter,
    AtlasConverter,
    ConversionPlanner,
    SkeletonConverter,
    SourceRiskPolicy,
)
from .conversion.runtime import run_spine_runtime_smoke
from .inspection import InspectionService
from .json_types import JSONDocument, JSONValue
from .packaging import PackageBuilder
from .versions import VersionRegistry


class CLIArguments(argparse.Namespace):
    container: str = "zip"
    skeleton_format: str = "json"
    report_output: str | None = None
    bundle_operation: str = ""
    bundle_id: list[str] | None = None
    retention: str = "required_only"
    package_mode: str = "viewer"
    command: str = ""
    kind: str = ""
    source: str = ""
    input: str = ""
    target: str = ""
    skeleton: str = ""
    atlas: str = ""
    runtime_package: str = ""
    from_version: str = ""
    to_version: str = ""
    output: str | None = None
    output_dir: str = ""
    source_version: str | None = None
    json_output: bool = False
    strict: bool = False
    dry_run: bool = False
    experimental_structural: bool = False
    allow_known_source_export_risk: bool = False


def main(argv: list[str] | None = None) -> int:
    try:
        return _execute(argv)
    except (OSError, ValueError, UnicodeError) as exc:
        failure: JSONDocument = {
            "status": "failed",
            "code": "CLI_OPERATION_FAILED",
            "message": str(exc),
        }
        print(json.dumps(failure, ensure_ascii=False, sort_keys=True, indent=2))
        return 2


def _execute(argv: list[str] | None = None) -> int:
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
    asset_convert = sub.add_parser(
        "convert-asset-set",
        help="Convert and validate a complete skeleton, atlas, and texture bundle",
    )
    asset_convert.add_argument("--input", required=True, help="Inspected folder or ZIP source")
    asset_convert.add_argument("--skeleton", required=True, help="Skeleton path or bundle ID")
    asset_convert.add_argument("--target", required=True)
    asset_convert.add_argument("--output-dir", required=True)
    asset_convert.add_argument("--allow-known-source-export-risk", action="store_true")
    convert = sub.add_parser("convert", help="Convert a standalone JSON skeleton or atlas")
    kinds = convert.add_subparsers(dest="kind", required=True)
    conversion_parsers: list[argparse.ArgumentParser] = []
    for kind in ("skeleton", "atlas"):
        command = kinds.add_parser(kind)
        conversion_parsers.append(command)
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
    asset_convert.add_argument("--experimental-structural", action="store_true")
    for command_parser in conversion_parsers:
        command_parser.add_argument("--experimental-structural", action="store_true")
    sub.add_parser("binary-capabilities", help="List exact binary operations and evidence limits")
    bundle_parser = sub.add_parser("bundle", help="Inspect, plan and package logical bundles")
    operations = bundle_parser.add_subparsers(dest="bundle_operation", required=True)
    retention_choices: list[str] = [p.value for p in RetentionPolicy]
    format_choices: tuple[str, ...] = tuple(f.value for f in SkeletonFormat)
    container_choices: tuple[str, ...] = tuple(c.value for c in PackageContainer)
    package_choices: list[str] = [p.value for p in PackageMode]
    for operation in ("inspect", "list", "plan", "convert"):
        operation_parser = operations.add_parser(operation)
        if operation in ("inspect", "list"):
            operation_parser.add_argument("source")
        else:
            operation_parser.add_argument("--input", required=True)
            operation_parser.add_argument("--target", required=True)
            operation_parser.add_argument(
                "--container",
                choices=container_choices,
                required=operation == "convert",
                default="zip",
            )
            operation_parser.add_argument(
                "--skeleton-format", choices=format_choices, default=SkeletonFormat.JSON.value
            )
            operation_parser.add_argument(
                "--report-output", help="Separate atomic report sidecar export"
            )
            operation_parser.add_argument("--bundle-id", action="append")
            operation_parser.add_argument("--output", required=operation == "convert")
            operation_parser.add_argument("--experimental-structural", action="store_true")
            operation_parser.add_argument("--allow-known-source-export-risk", action="store_true")
            operation_parser.add_argument(
                "--retention", choices=retention_choices, default="required_only"
            )
            operation_parser.add_argument(
                "--package-mode", choices=package_choices, default="viewer"
            )
    args = CLIArguments()
    parser.parse_args(argv, namespace=args)
    if args.command == "binary-capabilities":
        capabilities: tuple[JSONDocument, ...] = tuple(
            c.to_dict() for c in BinaryCodecRegistry().capabilities()
        )
        print(json.dumps(capabilities, sort_keys=True, indent=2))
        return 0
    if args.command == "bundle":
        service = BundleService()
        if args.bundle_operation in ("inspect", "list"):
            try:
                inspected = service.inspect_source(args.source)
                print(json.dumps(inspected.to_dict(), ensure_ascii=False, sort_keys=True, indent=2))
                return 0 if inspected.manifest.ok else 2
            except (OSError, ValueError) as exc:
                failure_report: JSONDocument = {"status": "failed", "message": str(exc)}
                print(json.dumps(failure_report))
                return 2
        request = BundleRequest(
            source=args.input,
            target=args.target,
            output=Path(args.output or "unused-plan-output.zip"),
            bundle_ids=tuple(args.bundle_id or ()),
            experimental_structural=args.experimental_structural,
            source_risk_policy=(
                SourceRiskPolicy.ALLOW_WITH_DIAGNOSTIC
                if args.allow_known_source_export_risk
                else SourceRiskPolicy.REJECT_KNOWN_ISSUES
            ),
            container=PackageContainer(args.container),
            skeleton_format=SkeletonFormat(args.skeleton_format),
            retention=RetentionPolicy(args.retention),
            package_mode=PackageMode(args.package_mode),
        )
        bundle_result = (
            service.plan_conversion(request)
            if args.bundle_operation == "plan"
            else service.convert_bundle(request)
        )
        if args.report_output:
            try:
                service.write_report(bundle_result, Path(args.report_output))
            except OSError as exc:
                bundle_result = replace(
                    bundle_result, report=replace(bundle_result.report, sidecar_error=str(exc))
                )
                print(
                    json.dumps(
                        bundle_result.to_dict(), ensure_ascii=False, sort_keys=True, indent=2
                    )
                )
                return 2
        print(json.dumps(bundle_result.to_dict(), ensure_ascii=False, sort_keys=True, indent=2))
        return 0 if bundle_result.status in ("completed", "planned") else 2
    if args.command == "versions":
        families: list[str] = [v.family for v in VersionRegistry().definitions()]
        print(json.dumps(families, indent=2))
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
        planned = ConversionPlanner().plan(args.from_version, args.to_version)
        plan_report: JSONDocument = {
            "executable": planned.executable,
            "route": planned.route,
            "diagnostics": planned.diagnostics,
            "qualification": planned.qualification.to_json() if planned.qualification else None,
        }
        print(json.dumps(plan_report, indent=2))
        return 0 if planned.executable else 2
    if args.command == "runtime-smoke":
        runtime_report = run_spine_runtime_smoke(args.skeleton, args.atlas, args.runtime_package)
        print(json.dumps(runtime_report, ensure_ascii=False, sort_keys=True, indent=2))
        return 0 if runtime_report.get("status") == "animation_state_evaluated" else 2
    if args.command == "convert-asset-set":
        outcome = AssetSetConverter(experimental_structural=args.experimental_structural).convert(
            args.input,
            args.skeleton,
            args.target,
            source_risk_policy=(
                SourceRiskPolicy.ALLOW_WITH_DIAGNOSTIC
                if args.allow_known_source_export_risk
                else SourceRiskPolicy.REJECT_KNOWN_ISSUES
            ),
        )
        if outcome.outputs is not None:
            if outcome.skeleton_path is None:
                raise ValueError("Converted asset set has no skeleton path")
            PackageBuilder().publish(
                outcome.outputs,
                (outcome.skeleton_path,),
                Path(args.output_dir),
                PackageContainer.FOLDER,
            )
        output_names: list[str] = sorted(outcome.outputs) if outcome.outputs is not None else []
        asset_report: JSONDocument = {
            "status": outcome.status.value,
            "qualification": outcome.qualification.to_json() if outcome.qualification else None,
            "source_version": outcome.source_version,
            "target_version": outcome.target_version,
            "route": outcome.route,
            "diagnostics": outcome.diagnostics,
            "details": outcome.details,
            "outputs": tuple(output_names) if outcome.outputs is not None else None,
        }
        print(json.dumps(asset_report, ensure_ascii=False, sort_keys=True, indent=2))
        return 0 if outcome.outputs is not None else 2
    if args.kind == "skeleton":
        skeleton_outcome = SkeletonConverter(
            experimental_structural=args.experimental_structural
        ).convert(
            args.input,
            args.target,
            source_risk_policy=(
                SourceRiskPolicy.ALLOW_WITH_DIAGNOSTIC
                if args.allow_known_source_export_risk
                else SourceRiskPolicy.REJECT_KNOWN_ISSUES
            ),
        )
        report: dict[str, JSONValue] = {
            "status": skeleton_outcome.status.value,
            "qualification": skeleton_outcome.qualification.to_json()
            if skeleton_outcome.qualification
            else None,
            "source_version": skeleton_outcome.source_version,
            "target_version": skeleton_outcome.target_version,
            "route": skeleton_outcome.route,
            "diagnostics": skeleton_outcome.diagnostics,
            "statistics": skeleton_outcome.statistics,
            "details": skeleton_outcome.details,
            "unsupported_features": skeleton_outcome.unsupported_features,
            "diagnostic_codes": skeleton_outcome.diagnostic_codes,
            "provenance": skeleton_outcome.provenance,
        }
        if skeleton_outcome.output is not None and not args.dry_run:
            if not args.output:
                parser.error("convert skeleton requires --output unless --dry-run is used")
            write_bytes_exclusive(Path(args.output), skeleton_outcome.output)
        print(json.dumps(report, indent=2))
        return 0 if skeleton_outcome.output is not None else 2
    try:
        atlas_output = AtlasConverter(experimental_structural=args.experimental_structural).convert(
            args.input, args.target, source_version=args.source_version
        )
        atlas_model = AtlasConverter().read(atlas_output)
        report = {
            "status": "structurally_verified",
            "source_version": args.source_version,
            "target_version": args.target,
            "qualification": AtlasConverter()
            .qualification(args.source_version or "", args.target)
            .to_json(),
            "experimental_structural": args.experimental_structural,
            "pages": len(atlas_model.pages),
            "regions": len(atlas_model.regions),
            "structural_verification": "passed",
            "diagnostics": [],
        }
        if not args.dry_run:
            if not args.output:
                parser.error("convert atlas requires --output unless --dry-run is used")
            write_bytes_exclusive(Path(args.output), atlas_output)
    except (OSError, ValueError, UnicodeError) as exc:
        report = {
            "status": "rejected",
            "diagnostics": [str(exc)],
            "qualification": AtlasConverter()
            .qualification(args.source_version or "", args.target)
            .to_json(),
        }
        print(json.dumps(report, indent=2))
        return 2
    print(json.dumps(report, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
