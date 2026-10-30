"""Explicit local B3 qualification driver; no production viewer integration.

Usage: .venv/bin/python scripts/qualify_b3_binary.py /tmp/new-evidence-directory
Requires the existing pinned development runtime. Each official reader process
has a 256 MiB V8 heap and a 30 second wall-clock limit. This is a trusted local
fixture test tool, not an untrusted-upload service or OS sandbox claim.
"""
from __future__ import annotations

import hashlib
import json
import subprocess
import sys
from pathlib import Path

from fnx_spine_forge.binary import BinaryCodecRegistry, BinaryError, BinaryReader
from fnx_spine_forge.json_types import decode_json_object

ROOT = Path(__file__).resolve().parents[1]
FIXTURES = ROOT / "tests/fixtures/binary"


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def main() -> None:
    output = Path(sys.argv[1]).resolve()
    output.mkdir(parents=True, exist_ok=False)
    codec = BinaryCodecRegistry().codec("4.2.43", experimental=True)
    results = []
    for kind in ("region", "mesh", "ik"):
        source = FIXTURES / f"animated_{kind}_4_2_43.json"
        binary = output / f"{kind}.skel"
        binary.write_bytes(codec.encode(decode_json_object(source.read_bytes(), "fixture")))
        decoded = codec.decode(binary.read_bytes())
        (output / f"{kind}.decoded.json").write_text(json.dumps(decoded, indent=2) + "\n")
        assert codec.encode(decoded) == binary.read_bytes()
        result = subprocess.run(
            ["node", "--max-old-space-size=256", str(ROOT / "scripts/qualify_binary42.mjs"),
             str(source), str(binary), str(FIXTURES / "animated_region.atlas")],
            cwd=ROOT, check=True, capture_output=True, text=True, timeout=30,
        )
        evidence = json.loads(result.stdout)
        evidence["fixture"] = str(source.relative_to(ROOT))
        evidence["provenance"] = "independently specified JSON; not an authentic editor export"
        evidence["decoder_evidence"] = "self-roundtrip only for this fixture; not independent decoder qualification"
        results.append(evidence)
    authentic = ROOT / "viewer/fixtures/4.2/spineboy-pro.skel"
    payload = authentic.read_bytes()
    reader = BinaryReader(payload)
    reader.take(8)
    export_version = reader.string()
    try:
        codec.decode(payload)
    except BinaryError as error:
        authentic_result = {"fixture": str(authentic.relative_to(ROOT)), "sha256": sha(payload),
                            "export_version": export_version, "result": error.to_dict()}
    else:
        raise AssertionError("Unqualified authentic export version was admitted")
    report = {
        "decision": "B3 PARTIAL — BINARY UNQUALIFIED",
        "encoder_comparisons": results,
        "authentic_binary_admission": authentic_result,
        "production_binary_policy_modified": False,
        "b2_qualification_modified": False,
        "sources": {name: sha((ROOT / name).read_bytes()) for name in (
            "src/fnx_spine_forge/binary.py", "src/fnx_spine_forge/binary_animation.py",
            "src/fnx_spine_forge/binary_schema.py",
            "scripts/qualify_binary42.mjs", "scripts/qualify_b3_binary.py")},
    }
    (output / "qualification.json").write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
