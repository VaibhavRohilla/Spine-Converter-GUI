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
from fnx_spine_forge.bundle_models import BundleRequest
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
    codec = BinaryCodecRegistry().codec("4.2.22", experimental=True)
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
    # This encoder input is derived from FNX decoding, never mislabel it as an
    # independent authenticated-JSON encoder reference.
    encoded = output / "powerup.reencoded.skel"
    encoded.write_bytes(codec.encode(decoded))
    assert encoded.read_bytes() == codec.encode(decoded)
    reencoded = json.loads(
        runtime("compare_binary42.mts", authentic, FIXTURES / "powerup.atlas", encoded).stdout
    )
    try:
        codec.encode(decode_json_object((FIXTURES / "powerup-ess.json").read_bytes(), "official"))
    except BinaryError as error:
        original_json_encoder = error.to_dict()
    else:
        raise AssertionError("Update release evidence: original JSON now encodes")
    reference_json = runtime(
        "compare_binary42.mts",
        authentic,
        FIXTURES / "powerup.atlas",
        FIXTURES / "powerup-ess.json",
        check=False,
    )
    assert reference_json.returncode != 0, "Reassess original JSON export precision"
    (output / "official-json-comparison.stderr").write_text(reference_json.stderr)
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
    source = output / "source"
    source.mkdir()
    for name in ("powerup-ess.skel", "powerup.atlas", "powerup.png"):
        shutil.copyfile(FIXTURES / name, source / name)
    before = {p.name: sha(p) for p in source.iterdir()}
    bundles = []
    for experimental in (False, True):
        result = BundleService().convert_bundle(
            BundleRequest(
                source,
                "4.2.22",
                output / f"bundle-{experimental}.zip",
                experimental_structural=experimental,
            )
        )
        bundles.append(result.report.to_dict())
        assert not result.published, "Reassess release gate: authentic bundle now publishes"
    assert before == {p.name: sha(p) for p in source.iterdir()}
    report = {
        "decision": "B3 PARTIAL — BINARY QUALIFICATION BLOCKED",
        "existing_authenticated_binary_inventory": existing_binaries,
        "new_authenticated_sources": provenance,
        "authentic_runtime_inventory": fixtures,
        "decoder_semantics": comparison,
        "decoder_poses": poses,
        "encoder_binary_derived_input_only": reencoded,
        "unchanged_authentic_json_encoder": original_json_encoder,
        "official_json_pair": {
            "same_pinned_repository_commit": True,
            "editor_hash_matches_binary_bytes": base64.b64decode(
                json.loads((FIXTURES / "powerup-ess.json").read_text())["skeleton"]["hash"] + "="
            )
            == authentic.read_bytes()[:8],
            "matching_export_settings_proven": False,
            "semantic_equality": "FAIL: original JSON rounds setup values; see stderr",
            "used_as_decoder_expected_reference": False,
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
