"""Headless CLI adapter over the shared inspection and version APIs."""

from __future__ import annotations

import argparse
import json
import sys

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
    print(
        json.dumps(
            {
                "ok": False,
                "error": f"Unsupported migration {args.from_version} -> {args.to_version}; "
                "no registered implementation",
            },
            indent=2,
        )
    )
    return 2


if __name__ == "__main__":
    sys.exit(main())
