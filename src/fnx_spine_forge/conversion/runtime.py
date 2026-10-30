"""Optional exact-version official Spine TypeScript runtime smoke test."""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

from ..json_types import JSONDocument, decode_json_object
from .registry import RUNTIME_EXTENSION_LOADER_PATCHES, RUNTIME_SMOKE_PATCHES


def run_spine_runtime_smoke(
    skeleton_path: str | Path,
    atlas_path: str | Path,
    runtime_package: str | Path,
) -> JSONDocument:
    """Select the exact supported runtime matching the skeleton's target version."""
    package_root = Path(runtime_package)
    try:
        package = decode_json_object(
            (package_root / "package.json").read_text(encoding="utf-8"),
            "Spine runtime package metadata",
        )
    except (OSError, ValueError) as exc:
        return {"status": "not_run", "reason": f"Runtime package metadata unavailable: {exc}"}
    package_name, package_version = package.get("name"), package.get("version")
    if (
        package_name != "@esotericsoftware/spine-core"
        or not isinstance(package_version, str)
        or package_version not in RUNTIME_SMOKE_PATCHES
        or not isinstance(package.get("main"), str)
    ):
        return {
            "status": "rejected_runtime_identity",
            "reason": "Runtime must be an explicitly supported official Spine runtime package",
            "runtime": f"{package_name}@{package_version}",
        }
    target_version = package_version
    node = shutil.which("node")
    if node is None:
        return {"status": "not_run", "reason": "Node.js is unavailable"}
    script = Path(__file__).with_name("runtime_smoke.mjs")
    command = [node]
    if target_version in RUNTIME_EXTENSION_LOADER_PATCHES:
        command.extend(
            ["--experimental-loader", str(Path(__file__).with_name("runtime_extension_loader.mjs"))]
        )
    command.extend(
        [
            str(script),
            str(package_root.resolve()),
            str(Path(skeleton_path).resolve()),
            str(Path(atlas_path).resolve()),
        ]
    )
    try:
        process = subprocess.run(
            command,
            check=False,
            capture_output=True,
            text=True,
            timeout=60,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        return {"status": "failed", "error": f"Runtime smoke process could not complete: {exc}"}
    if process.returncode:
        return {
            "status": "failed",
            "runtime": f"{package['name']}@{package['version']}",
            "error": process.stderr.strip() or process.stdout.strip(),
        }
    try:
        result = decode_json_object(process.stdout, "Runtime smoke report")
    except ValueError as exc:
        return {"status": "failed", "error": f"Runtime harness returned invalid JSON: {exc}"}
    return result
