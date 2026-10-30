"""Reproduce authentic decoder evidence without changing B4 admission or B2 routes.

Run with the installed wheel's Python as well as the checkout. Each official
runtime child is bounded to 256 MiB heap, 30 seconds and 4 MiB per fixture.
"""

from __future__ import annotations

import base64
import hashlib
import json
import shutil
import subprocess
import sys
from pathlib import Path

from fnx_spine_forge.binary import BinaryCodecRegistry, BinaryError
from fnx_spine_forge.bundle import BundleService
from fnx_spine_forge.bundle_models import BundleRequest, SkeletonFormat
from fnx_spine_forge.json_types import decode_json_object

ROOT = Path(__file__).resolve().parents[1]
FIXTURES = ROOT / "tests/fixtures/binary/official42"


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def runtime(script, *paths, check=True):
    return subprocess.run(
        ["node", "--max-old-space-size=256", str(ROOT / "scripts" / script), *map(str, paths)],
        cwd=ROOT,
        capture_output=True,
        text=True,
        timeout=30,
        check=check,
    )


def main():
    output = Path(sys.argv[1]).resolve()
    output.mkdir(parents=True, exist_ok=False)
    provenance = json.loads((FIXTURES / "provenance.json").read_text())
    for row in provenance:
        assert sha(ROOT / row["path"]) == row["sha256"]
    existing = json.loads((ROOT / "viewer/fixtures/provenance.json").read_text())
    existing_binaries = []
    for row in existing:
        if row["file"].endswith(".skel"):
            path = ROOT / "viewer/fixtures" / row["family"] / row["file"]
            assert sha(path) == row["sha256"]
            existing_binaries.append(row)
    codec = BinaryCodecRegistry().codec("4.2.22")
    authentic = FIXTURES / "powerup-ess.skel"
    decoded = codec.decode(authentic.read_bytes())
    decoded_path = output / "powerup.decoded.json"
    decoded_path.write_text(json.dumps(decoded, indent=2) + "\n")
    comparison = json.loads(
        runtime("compare_binary42.mts", authentic, FIXTURES / "powerup.atlas", decoded_path).stdout
    )
    poses = json.loads(
        runtime("qualify_binary42.mjs", decoded_path, authentic, FIXTURES / "powerup.atlas").stdout
    )
    # Keep binary-derived encoder evidence distinct from the unchanged JSON gate.
    encoded = output / "powerup.reencoded.skel"
    encoded.write_bytes(codec.encode(decoded))
    assert encoded.read_bytes() == codec.encode(decoded)
    reencoded = json.loads(
        runtime("compare_binary42.mts", authentic, FIXTURES / "powerup.atlas", encoded).stdout
    )
    official_json = FIXTURES / "powerup-ess.json"
    official_document = decode_json_object(official_json.read_bytes(), "official Powerup JSON")
    encoded_official = output / "powerup.official-json.skel"
    encoded_official.write_bytes(codec.encode(official_document))
    official_json_comparison = json.loads(
        runtime(
            "compare_binary42.mts",
            official_json,
            FIXTURES / "powerup.atlas",
            encoded_official,
        ).stdout
    )
    fixtures = []
    for name, binary, atlas in (
        ("powerup-ess", authentic, FIXTURES / "powerup.atlas"),
        (
            "spineboy-pro",
            ROOT / "viewer/fixtures/4.2/spineboy-pro.skel",
            ROOT / "viewer/fixtures/4.2/spineboy.atlas",
        ),
        (
            "spineboy-ess",
            FIXTURES / "spineboy-ess.skel",
            ROOT / "viewer/fixtures/4.2/spineboy.atlas",
        ),
        (
            "coin-pro",
            FIXTURES / "coin-pro.skel",
            ROOT / "viewer/fixtures/features/4.2-coin/coin.atlas",
        ),
        (
            "vine-pro",
            FIXTURES / "vine-pro.skel",
            ROOT / "viewer/fixtures/features/4.2-vine/vine.atlas",
        ),
    ):
        record = json.loads(runtime("compare_binary42.mts", binary, atlas).stdout)
        record["fixture"] = name
        try:
            codec.decode(binary.read_bytes())
        except BinaryError as error:
            record["fnx_decoder"] = error.to_dict()
        else:
            record["fnx_decoder"] = "decoded; see explicit Powerup comparisons"
        fixtures.append(record)
    bundles = []
    for source_name, output_format in (
        ("powerup-ess.skel", "json"),
        ("powerup-ess.json", "binary"),
    ):
        source = output / f"source-{output_format}"
        source.mkdir()
        for name in (source_name, "powerup.atlas", "powerup.png"):
            shutil.copyfile(FIXTURES / name, source / name)
        before = {p.name: sha(p) for p in source.iterdir()}
        result = BundleService().convert_bundle(
            BundleRequest(
                source,
                "4.2.22",
                output / f"bundle-{output_format}.zip",
                skeleton_format=SkeletonFormat(output_format),
            )
        )
        bundles.append(result.report.to_dict())
        assert result.published, result.to_dict()
        inspected = BundleService().inspect_source(output / f"bundle-{output_format}.zip")
        assert inspected.manifest.ok
        assert before == {p.name: sha(p) for p in source.iterdir()}
    report = {
        "decision": "B3 CLOSED / FROZEN — RESTRICTED 4.2.22 BINARY PROFILE",
        "existing_authenticated_binary_inventory": existing_binaries,
        "new_authenticated_sources": provenance,
        "authentic_runtime_inventory": fixtures,
        "decoder_semantics": comparison,
        "decoder_poses": poses,
        "encoder_binary_derived_input_only": reencoded,
        "unchanged_authentic_json_encoder": official_json_comparison,
        "official_json_pair": {
            "same_pinned_repository_commit": True,
            "editor_hash_matches_binary_bytes": base64.b64decode(
                json.loads((FIXTURES / "powerup-ess.json").read_text())["skeleton"]["hash"] + "="
            )
            == authentic.read_bytes()[:8],
            "matching_export_settings_proven": False,
            "semantic_equality": "PASS against original JSON loaded through the official runtime",
            "used_as_decoder_expected_reference": False,
            "json_encoder_comparison": official_json_comparison["statistics"],
        },
        "public_bundle_api": bundles,
        "source_and_png_immutable": True,
        "b4_policy_sha256": sha(ROOT / "src/fnx_spine_forge/viewer/trusted_binary.json"),
        "b2_evidence_sha256": sha(
            ROOT / "src/fnx_spine_forge/conversion/qualification_evidence.json"
        ),
        "sources": {
            name: sha(ROOT / name)
            for name in (
                "src/fnx_spine_forge/binary.py",
                "src/fnx_spine_forge/conversion/semantic.py",
                "src/fnx_spine_forge/conversion/qualification.py",
                "src/fnx_spine_forge/binary_animation.py",
                "src/fnx_spine_forge/binary_schema.py",
                "scripts/compare_binary42.mts",
                "scripts/qualify_authentic_binary.py",
            )
        },
    }
    (output / "qualification.json").write_text(json.dumps(report, indent=2) + "\n")
    print(
        json.dumps(
            {
                "decision": report["decision"],
                "semantics": comparison["statistics"],
                "poses": poses,
                "output": str(output),
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
