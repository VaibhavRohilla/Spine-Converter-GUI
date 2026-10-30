"""Authentic-source decoder proof. No self-roundtrip is used as its reference."""
import copy
import hashlib
import json
import subprocess
from pathlib import Path

import pytest

from fnx_spine_forge.binary import BinaryCodecRegistry, BinaryError, BinaryLimits
from fnx_spine_forge.bundle import BundleService
from fnx_spine_forge.bundle_models import BundleRequest, SkeletonFormat
from fnx_spine_forge.conversion.planner import ConversionPlanner
from fnx_spine_forge.conversion.qualification import (
    ConversionQualificationRegistry,
    SourceFeature,
    inspect_features,
)
from fnx_spine_forge.conversion.skeleton import SkeletonConverter
from fnx_spine_forge.json_types import decode_json_object, encode_json
from fnx_spine_forge.viewer.binary_policy import admit_binary

ROOT = Path(__file__).resolve().parents[1]
FIXTURES = ROOT / "tests/fixtures/binary/official42"


def codec():
    return BinaryCodecRegistry().codec("4.2.22", experimental=True)


def reference(candidate):
    return subprocess.run(
        ["node", "--max-old-space-size=256", str(ROOT / "scripts/compare_binary42.mts"),
         str(FIXTURES / "powerup-ess.skel"), str(FIXTURES / "powerup.atlas"), str(candidate)],
        cwd=ROOT, capture_output=True, text=True, timeout=30,
    )


def test_authentic_provenance_and_independent_decoder(tmp_path):
    for row in json.loads((FIXTURES / "provenance.json").read_text()):
        assert hashlib.sha256((ROOT / row["path"]).read_bytes()).hexdigest() == row["sha256"]
    original = (FIXTURES / "powerup-ess.skel").read_bytes()
    decoded = codec().decode(original)
    assert decoded["skeleton"]["spine"] == "4.2.22"
    path = tmp_path / "decoded.json"
    path.write_text(json.dumps(decoded))
    result = reference(path)
    assert result.returncode == 0, result.stderr
    evidence = json.loads(result.stdout)
    assert evidence["statistics"] == {"numeric": 2180, "exact": 207, "maximumError": 0}
    assert evidence["inventory"]["keyframes"] == 182
    assert evidence["inventory"]["attachments"] == {"RegionAttachment": 13}
    assert evidence["inventory"]["deformFrames"] == 0
    # The reference binary is original, independently authenticated bytes.
    assert evidence["binarySha256"] == hashlib.sha256(original).hexdigest()
    encoded = tmp_path / "output.skel"
    encoded.write_bytes(codec().encode(decoded))
    assert encoded.read_bytes() == codec().encode(decoded)
    assert reference(encoded).returncode == 0
    # Encoding decoded input is extra evidence, not an independent JSON source.
    with pytest.raises(ValueError, match="UNTRUSTED|UNAPPROVED|NOT_APPROVED"):
        admit_binary(encoded.read_bytes(), "4.2.22")
    assert (FIXTURES / "powerup-ess.skel").read_bytes() == original


def test_unchanged_official_json_encodes_and_matches_official_runtime(tmp_path):
    source = (FIXTURES / "powerup-ess.json").read_bytes()
    original = decode_json_object(source, "official Powerup JSON")
    encoded = codec().encode(original)
    assert encoded[:8].hex() == "48c29958a44b830f"
    assert original["skeleton"]["hash"] == "SMKZWKRLgw8"
    assert (FIXTURES / "powerup-ess.json").read_bytes() == source
    path = tmp_path / "powerup-from-official-json.skel"
    path.write_bytes(encoded)
    result = reference_json(path)
    assert result.returncode == 0, result.stderr
    evidence = json.loads(result.stdout)
    assert evidence["statistics"] == {
        "numeric": 2180,
        "exact": 207,
        "maximumError": 0.00000762939453125,
    }
    assert evidence["referenceFormat"] == "official-json"
    assert evidence["inventory"]["keyframes"] == 182
    assert codec().decode(encoded)["skeleton"]["hash"] == "48c29958a44b830f"


def reference_json(candidate):
    return subprocess.run(
        [
            "node",
            "--max-old-space-size=256",
            str(ROOT / "scripts/compare_binary42.mts"),
            str(FIXTURES / "powerup-ess.json"),
            str(FIXTURES / "powerup.atlas"),
            str(candidate),
        ],
        cwd=ROOT,
        capture_output=True,
        text=True,
        timeout=30,
    )


@pytest.mark.parametrize("value", ["!!!!", "abc", "AAAAAAAAAAAA", "SMKZWKRLg!8"])
def test_malformed_4222_hash_rejected(value):
    document = decode_json_object((FIXTURES / "powerup-ess.json").read_bytes(), "official")
    document["skeleton"]["hash"] = value
    with pytest.raises(BinaryError) as error:
        codec().encode(document)
    assert error.value.code.value == "BINARY_HASH"


def test_hash_encoding_is_exact_versioned():
    from fnx_spine_forge.binary import BinaryErrorCode

    document = decode_json_object((FIXTURES / "powerup-ess.json").read_bytes(), "official")
    document["skeleton"]["spine"] = "4.2.43"
    with pytest.raises(BinaryError) as error:
        BinaryCodecRegistry().codec("4.2.43", experimental=True).encode(document)
    assert error.value.code is BinaryErrorCode.HASH


@pytest.mark.parametrize(
    ("location", "field", "value", "code"),
    [
        ("skeleton", "fps", "fast", "BINARY_NUMBER"),
        ("bone", "color", "zzzzzzzz", "BINARY_COLOR"),
        ("bone", "visible", "yes", "BINARY_BOOLEAN"),
    ],
)
def test_malformed_nonessential_metadata_rejected(location, field, value, code):
    document = decode_json_object((FIXTURES / "powerup-ess.json").read_bytes(), "official")
    target = document["skeleton"] if location == "skeleton" else document["bones"][0]
    target[field] = value
    with pytest.raises(BinaryError) as error:
        codec().encode(document)
    assert error.value.code.value == code


def test_hex_hash_contract_and_editor_metadata_projection():
    document = decode_json_object((FIXTURES / "powerup-ess.json").read_bytes(), "official")
    document["skeleton"]["hash"] = "48c29958a44b830f"
    data = codec().encode(document)
    decoded = codec().decode(data)
    assert decoded["bones"][0]["visible"] is False
    assert decoded["bones"][0]["color"] == "00000000"
    authentic = codec().decode((FIXTURES / "powerup-ess.skel").read_bytes())
    assert authentic["bones"][0]["visible"] is True
    assert authentic["bones"][0]["color"] == "9b9b9bff"
    assert SkeletonConverter().read(encode_json(authentic)).document["bones"][0]["visible"] is True
    unknown = json.loads(encode_json(decoded))
    unknown["bones"][0]["semantic_typo"] = True
    with pytest.raises(ValueError, match="Unknown semantic bone fields"):
        SkeletonConverter().read(encode_json(unknown))
    malformed = json.loads(encode_json(decoded))
    malformed["bones"][0]["visible"] = "yes"
    with pytest.raises(ValueError, match="visible must be a boolean"):
        SkeletonConverter().read(encode_json(malformed))


def test_qualified_codec_rejects_features_outside_evidence_profile():
    document = json.loads((ROOT / "tests/fixtures/binary/animated_mesh_4_2_43.json").read_text())
    document["skeleton"]["spine"] = "4.2.22"
    with pytest.raises(BinaryError, match="qualified binary profile"):
        BinaryCodecRegistry().codec("4.2.22").encode(document)


@pytest.mark.parametrize(
    ("timeline", "feature"),
    [
        (
            {
                "bones": {
                    "root": {
                        "translatex": [
                            {"time": 0, "value": 0},
                            {"time": 1, "value": 1},
                        ]
                    }
                }
            },
            SourceFeature.SEPARATE_AXIS,
        ),
        (
            {
                "slots": {
                    "slot": {
                        "rgba": [
                            {
                                "time": 0,
                                "color": "ffffffff",
                                "curve": [0.2, 0.1, 0.8, 0.9] * 4,
                            },
                            {"time": 1, "color": "00000000"},
                        ]
                    }
                }
            },
            SourceFeature.SLOT_BEZIER,
        ),
    ],
)
def test_unverified_timeline_categories_stay_out_of_qualified_profile(timeline, feature):
    document = {
        "skeleton": {"spine": "4.2.22"},
        "bones": [{"name": "root"}],
        "slots": [{"name": "slot", "bone": "root"}],
        "skins": [],
        "animations": {"a": timeline},
    }
    canonical = SkeletonConverter().read(encode_json(document))
    features = inspect_features(canonical.semantic, canonical.document)
    assert feature in features
    with pytest.raises(BinaryError, match="qualified binary profile"):
        BinaryCodecRegistry().codec("4.2.22").encode(document)


@pytest.mark.parametrize("input_kind", ["folder", "zip"])
def test_authentic_powerup_public_bundle_workflows(tmp_path, input_kind):
    service = BundleService()
    for source_name, skeleton_format, target_name in (
        ("powerup-ess.skel", SkeletonFormat.JSON, "decoded.zip"),
        ("powerup-ess.json", SkeletonFormat.BINARY, "encoded.zip"),
    ):
        source = tmp_path / f"source-{source_name}"
        source.mkdir()
        for name in (source_name, "powerup.atlas", "powerup.png"):
            (source / name).write_bytes((FIXTURES / name).read_bytes())
        source_selection = source
        if input_kind == "zip":
            from zipfile import ZIP_DEFLATED, ZipFile

            archive_path = tmp_path / f"{source.name}.zip"
            with ZipFile(archive_path, "w", compression=ZIP_DEFLATED) as archive:
                for path in source.iterdir():
                    archive.write(path, path.name)
            source_selection = archive_path
        before = {
            path.name: hashlib.sha256(path.read_bytes()).hexdigest()
            for path in source.iterdir()
        }
        output = tmp_path / target_name
        result = service.convert_bundle(
            BundleRequest(
                source_selection,
                "4.2.22",
                output,
                bundle_ids=(source_name,),
                skeleton_format=skeleton_format,
            )
        )
        assert result.published, result.to_dict()
        inspected = service.inspect_source(output)
        assert inspected.manifest.ok
        from zipfile import ZipFile

        with ZipFile(output) as archive:
            names = set(archive.namelist())
            skeleton_name = (
                "powerup-ess.json"
                if skeleton_format is SkeletonFormat.JSON
                else "powerup-ess.skel"
            )
            assert skeleton_name in names
            assert "powerup.atlas" in names and "powerup.png" in names
            assert archive.read("powerup.png") == (FIXTURES / "powerup.png").read_bytes()
            if skeleton_format is SkeletonFormat.JSON:
                result_document = json.loads(archive.read(skeleton_name))
                assert result_document["skeleton"]["spine"] == "4.2.22"
                assert result_document["bones"][0]["visible"] is True
            else:
                payload = archive.read(skeleton_name)
                assert payload[:8].hex() == "48c29958a44b830f"
                assert codec().decode(payload)["animations"]["bounce"]
        assert before == {
            path.name: hashlib.sha256(path.read_bytes()).hexdigest()
            for path in source.iterdir()
        }


def mutate(document, kind):
    if kind == "hierarchy":
        document["bones"][2]["parent"] = "root"
    elif kind == "setup":
        document["bones"][1]["x"] += 1
    elif kind == "region":
        document["skins"][0]["attachments"]["left-wing"]["wing"]["width"] += 1
    elif kind == "slot":
        document["slots"][0]["color"] = "ff0000ff"
    else:
        timelines = document["animations"]["bounce"]["bones"]
        if kind == "curve":
            frame = next(f for b in timelines.values() for frames in b.values()
                         for f in frames if isinstance(f.get("curve"), list))
            frame["curve"][1] += 10
        else:
            frames = next(frames for b in timelines.values() for name, frames in b.items()
                          if name == "rotate" and len(frames) > 1)
            if kind == "time":
                frames[1]["time"] += 0.001
            else:
                frames[0]["value"] += 5


@pytest.mark.parametrize("kind", ["hierarchy", "setup", "region", "slot", "curve", "time", "value"])
def test_reference_detects_semantic_corruption(kind, tmp_path):
    document = copy.deepcopy(codec().decode((FIXTURES / "powerup-ess.skel").read_bytes()))
    mutate(document, kind)
    path = tmp_path / "corrupted.json"
    path.write_text(json.dumps(document))
    result = reference(path)
    assert result.returncode != 0
    assert "AssertionError" in result.stderr
    assert "!=" in result.stderr or "Expected values to be strictly equal" in result.stderr


def test_authentic_version_is_experimental_and_has_no_migration_edges():
    capability = BinaryCodecRegistry().codec("4.2.22").capability
    assert capability.semantically_qualified
    assert capability.to_dict()["experimental"] is False
    with pytest.raises(BinaryError, match="experimental"):
        BinaryCodecRegistry().codec("4.2.43")
    for version in ("4.2.43", "4.1.56", "4.3.13"):
        assert not ConversionPlanner().structural_plan("4.2.22", version).executable
        assert not ConversionPlanner().structural_plan(version, "4.2.22").executable
    registry = ConversionQualificationRegistry()
    assert registry.record(("4.2.22",)).supported_features
    assert registry.record(("4.2.22",)) in registry.records()
    plan = ConversionPlanner().plan(
        "4.2.22",
        "4.2.22",
        source_features=frozenset({SourceFeature.HIERARCHY}),
    )
    assert plan.executable and plan.qualification is not None and plan.qualification.qualified


@pytest.mark.parametrize("name", ["spineboy-ess", "coin-pro", "vine-pro"])
def test_authentic_advanced_content_fails_closed(name):
    with pytest.raises(BinaryError, match="Unsupported"):
        codec().decode((FIXTURES / f"{name}.skel").read_bytes())


def test_authentic_truncation_and_oversize_rejection():
    payload = (FIXTURES / "powerup-ess.skel").read_bytes()
    for length in (0, 8, 16, 100, len(payload)//2, len(payload)-1):
        with pytest.raises(BinaryError):
            codec().decode(payload[:length])
    with pytest.raises(BinaryError):
        BinaryCodecRegistry().codec(
            "4.2.22", experimental=True, limits=BinaryLimits(max_bytes=len(payload)-1)
        ).decode(payload)
