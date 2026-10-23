"""Optional exact-version official Spine TypeScript runtime smoke test."""

from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path
from typing import Any, cast


def run_spine_42_runtime_smoke(
    skeleton_path: str | Path,
    atlas_path: str | Path,
    runtime_package: str | Path,
) -> dict[str, Any]:
    """Load and sample a target export using the caller's licensed 4.2.43 runtime."""
    package_root = Path(runtime_package)
    try:
        package = json.loads((package_root / "package.json").read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        return {"status": "not_run", "reason": f"Runtime package metadata unavailable: {exc}"}
    if (
        package.get("name") != "@esotericsoftware/spine-core"
        or package.get("version") != "4.2.43"
        or not isinstance(package.get("main"), str)
    ):
        return {
            "status": "rejected_runtime_identity",
            "reason": "Runtime must be the official @esotericsoftware/spine-core 4.2.43 package",
            "runtime": f"{package.get('name')}@{package.get('version')}",
        }
    node = shutil.which("node")
    if node is None:
        return {"status": "not_run", "reason": "Node.js is unavailable"}
    script = Path(__file__).with_name("runtime_smoke.mjs")
    try:
        process = subprocess.run(
            [
                node,
                str(script),
                str(package_root.resolve()),
                str(Path(skeleton_path).resolve()),
                str(Path(atlas_path).resolve()),
            ],
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
        result = json.loads(process.stdout)
    except json.JSONDecodeError as exc:
        return {"status": "failed", "error": f"Runtime harness returned invalid JSON: {exc}"}
    return cast(dict[str, Any], result)
