"""Headless CLI adapter over the shared inspection and version APIs."""

from __future__ import annotations

import argparse
import json
import os
import shutil
import sys
import tempfile
from collections.abc import Mapping
from pathlib import Path

from .conversion import (
    AssetSetConverter,
    AtlasConverter,
    ConversionPlanner,
    SkeletonConverter,
    SourceRiskPolicy,
)
from .conversion.json_types import JSONValue
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
        planned = ConversionPlanner().plan(args.from_version, args.to_version)
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
    if args.command == "convert-asset-set":
        outcome = AssetSetConverter().convert(
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
            _publish_asset_set(Path(args.output_dir), outcome.outputs)
        print(
            json.dumps(
                {
                    "status": outcome.status.value,
                    "source_version": outcome.source_version,
                    "target_version": outcome.target_version,
                    "route": outcome.route,
                    "diagnostics": outcome.diagnostics,
                    "details": outcome.details,
                    "outputs": sorted(outcome.outputs) if outcome.outputs is not None else None,
                },
                ensure_ascii=False,
                sort_keys=True,
                indent=2,
            )
        )
        return 0 if outcome.outputs is not None else 2
    if args.kind == "skeleton":
        skeleton_outcome = SkeletonConverter().convert(
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
            "source_version": skeleton_outcome.source_version,
            "target_version": skeleton_outcome.target_version,
            "route": skeleton_outcome.route,
            "diagnostics": skeleton_outcome.diagnostics,
            "statistics": skeleton_outcome.statistics,
            "details": skeleton_outcome.details,
            "unsupported_features": skeleton_outcome.unsupported_features,
            "runtime_verified": skeleton_outcome.runtime_verified,
            "visually_verified": skeleton_outcome.visually_verified,
            "diagnostic_codes": skeleton_outcome.diagnostic_codes,
            "provenance": skeleton_outcome.provenance,
            "feature_compatibility": skeleton_outcome.feature_compatibility,
        }
        if skeleton_outcome.output is not None and not args.dry_run:
            if not args.output:
                parser.error("convert skeleton requires --output unless --dry-run is used")
            _atomic_write(Path(args.output), skeleton_outcome.output)
        print(json.dumps(report, indent=2))
        return 0 if skeleton_outcome.output is not None else 2
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


def _publish_asset_set(output_root: Path, outputs: Mapping[str, bytes]) -> None:
    """Publish a complete converted bundle with one directory rename."""
    for name, payload in outputs.items():
        if Path(name).name != name or name in {".", ".."} or not isinstance(payload, bytes):
            raise ValueError("Asset-set outputs must be filename-to-bytes entries")
    if output_root.exists():
        raise FileExistsError(f"Asset-set output directory already exists: {output_root}")
    output_root.parent.mkdir(parents=True, exist_ok=True)
    stage = Path(tempfile.mkdtemp(prefix=f".{output_root.name}.", dir=output_root.parent))
    try:
        for name, payload in outputs.items():
            _atomic_write(stage / name, payload)
        os.replace(stage, output_root)
    except BaseException:
        shutil.rmtree(stage, ignore_errors=True)
        raise


if __name__ == "__main__":
    sys.exit(main())
