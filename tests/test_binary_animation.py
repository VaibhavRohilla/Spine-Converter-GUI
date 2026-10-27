"""Independent runtime encoder tests and fail-closed animated binary checks."""

import copy
import hashlib
import json
import struct
import subprocess
from pathlib import Path
from zipfile import ZipFile

import pytest

from fnx_spine_forge.binary import BinaryCodecRegistry, BinaryError, BinaryLimits
from fnx_spine_forge.bundle import BundleService
from fnx_spine_forge.bundle_models import BundleRequest, SkeletonFormat
from fnx_spine_forge.json_types import decode_json_object

ROOT = Path(__file__).resolve().parents[1]
FIXTURES = ROOT / "tests/fixtures/binary"
KINDS = ("region", "mesh", "ik")


def codec():
    return BinaryCodecRegistry().codec("4.2.43", experimental=True)


def document(kind="region"):
    return decode_json_object((FIXTURES / f"animated_{kind}_4_2_43.json").read_bytes(), "fixture")


@pytest.mark.parametrize("kind", KINDS)
def test_official_runtime_encoder_and_decoded_json(kind, tmp_path):
    original = FIXTURES / f"animated_{kind}_4_2_43.json"
    encoded = codec().encode(document(kind))
    output = tmp_path / "asset.skel"
    output.write_bytes(encoded)
    decoded = codec().decode(encoded)
    decoded_path = tmp_path / "decoded.json"
    decoded_path.write_text(json.dumps(decoded))
    assert codec().encode(decoded) == encoded
    for json_path in (original, decoded_path):
        result = subprocess.run(
            [
                "node",
                "--max-old-space-size=256",
                "scripts/qualify_binary42.mjs",
                str(json_path),
                str(output),
                str(FIXTURES / "animated_region.atlas"),
            ],
            cwd=ROOT,
            capture_output=True,
            text=True,
            timeout=30,
            check=True,
        )
        evidence = json.loads(result.stdout)
        assert evidence["readerSuccess"] and evidence["animationEvaluation"]
        assert evidence["samples"] >= 42
        assert evidence["maximumError"] < 1e-5
        assert evidence["binarySha256"] == hashlib.sha256(encoded).hexdigest()
    # Successful external loading never adds production viewer trust.
    from fnx_spine_forge.viewer.binary_policy import admit_binary

    with pytest.raises(ValueError, match="UNTRUSTED|UNAPPROVED|NOT_APPROVED"):
        admit_binary(encoded, "4.2.43")


def test_independent_animated_wire_vector():
    # Hand-specified wire constants, not FNX writer output and not an editor export.
    # root -> region slot, default skin, linear rotate from 0 to 90 degrees.
    def f(*values):
        return struct.pack(">" + "f" * len(values), *values)

    data = bytes(8) + b"\x074.2.43" + f(0, 0, 64, 32, 100)
    data += b"\0\1\5face\1\5root" + f(0, 0, 0, 1, 1, 0, 0, 0) + bytes(2)
    data += b"\1\5face\0" + bytes.fromhex("ffffffffffffffff") + b"\1\0"
    data += bytes(4) + b"\1\0\1\1\0" + f(0, 0, 1, 1, 64, 32)
    data += b"\0\0\1\5turn\1\0\1\0\1\0\2\0" + f(0, 0, 1, 90) + bytes(8)
    decoded = codec().decode(data)
    assert decoded["slots"][0]["attachment"] == "face"
    assert decoded["skins"][0]["attachments"]["face"]["face"]["width"] == 64
    assert decoded["animations"]["turn"]["bones"]["root"]["rotate"] == [
        {"time": 0.0, "value": 0.0},
        {"time": 1.0, "value": 90.0},
    ]


@pytest.mark.parametrize("kind", KINDS)
def test_all_animated_truncations_and_determinism(kind):
    doc = document(kind)
    before = copy.deepcopy(doc)
    data = codec().encode(doc)
    assert doc == before
    assert codec().encode(doc) == data
    for length in range(len(data)):
        with pytest.raises(BinaryError):
            codec().decode(data[:length])
    for offset in range(len(data)):
        changed = bytearray(data)
        changed[offset] ^= 0xFF
        try:
            codec().decode(bytes(changed))
        except BinaryError:
            pass  # A mutation may also encode a different, valid skeleton.


@pytest.mark.parametrize(
    "mutation",
    [
        lambda d: d["slots"][0].update(bone="missing"),
        lambda d: d["skins"][0]["attachments"]["face"]["face"].update(type="path"),
        lambda d: d["animations"]["pulse"].update(events=[{"name": "missing"}]),
        lambda d: d["animations"]["pulse"]["bones"]["symbol"]["rotate"][1].update(time=0),
        lambda d: d["animations"]["pulse"]["bones"]["symbol"]["rotate"][0].update(curve=[0, 1]),
        lambda d: d["animations"]["pulse"]["bones"]["symbol"]["rotate"][0].update(
            value=float("nan")
        ),
        lambda d: d["animations"]["pulse"]["bones"]["symbol"]["rotate"].append(
            {"time": 1.00000000001}
        ),
        lambda d: d["animations"]["pulse"].update(physics={"x": []}),
        lambda d: d["skeleton"].update(spine="4.2.22"),
    ],
)
def test_rejected_animation_documents(mutation):
    doc = document()
    mutation(doc)
    with pytest.raises(BinaryError):
        codec().encode(doc)


@pytest.mark.parametrize(
    "mutation",
    [
        lambda a: a.update(triangles=[0, 1, 50, 2, 3, 0]),
        lambda a: a.update(hull=10),
        lambda a: a["vertices"].__setitem__(4, -1),
        lambda a: a["vertices"].__setitem__(1, 100),
        lambda a: a.update(vertices=[1000000000]),
    ],
)
def test_bad_mesh_geometry(mutation):
    doc = document("mesh")
    mutation(doc["skins"][0]["attachments"]["face"]["face"])
    with pytest.raises(BinaryError):
        codec().encode(doc)


def test_missing_linked_parent_and_bad_deform():
    doc = document("mesh")
    doc["skins"][1]["attachments"]["face"]["face"]["parent"] = "missing"
    with pytest.raises(BinaryError):
        codec().encode(doc)
    doc = document("mesh")
    doc["animations"]["pulse"]["attachments"]["default"]["face"]["face"]["deform"][1]["offset"] = (
        100
    )
    with pytest.raises(BinaryError):
        codec().encode(doc)


def test_animated_bundle_roundtrip_and_rollback(tmp_path):
    source = tmp_path / "source"
    source.mkdir()
    (source / "symbol.json").write_text(json.dumps(document()))
    (source / "symbol.atlas").write_bytes((FIXTURES / "animated_region.atlas").read_bytes())
    from PIL import Image

    Image.new("RGBA", (64, 32), (255, 255, 255, 255)).save(source / "page.png")
    before = {p.name: p.read_bytes() for p in source.iterdir()}
    service = BundleService()
    outputs = []
    for i in range(2):
        output = tmp_path / f"bundle{i}.zip"
        request = BundleRequest(
            source,
            "4.2.43",
            output,
            skeleton_format=SkeletonFormat.BINARY,
            experimental_structural=True,
        )
        result = service.convert_bundle(request)
        assert result.published, result.to_dict()
        outputs.append(output.read_bytes())
        with ZipFile(output) as archive:
            assert sorted(archive.namelist()) == ["page.png", "symbol.atlas", "symbol.skel"]
            assert archive.read("page.png") == before["page.png"]
            assert codec().decode(archive.read("symbol.skel"))["animations"]
        assert not service.convert_bundle(request).published
    assert outputs[0] == outputs[1]
    converted = tmp_path / "json.zip"
    result = service.convert_bundle(
        BundleRequest(tmp_path / "bundle0.zip", "4.2.43", converted, experimental_structural=True)
    )
    assert result.published, result.to_dict()
    assert {p.name: p.read_bytes() for p in source.iterdir()} == before
    rejected = tmp_path / "rejected.zip"
    assert not service.convert_bundle(
        BundleRequest(source, "4.2.43", rejected, skeleton_format=SkeletonFormat.BINARY)
    ).published
    assert not rejected.exists()
    bad = document()
    bad["animations"]["pulse"]["events"] = [{"name": "missing"}]
    (source / "symbol.json").write_text(json.dumps(bad))
    assert not service.convert_bundle(
        BundleRequest(
            source,
            "4.2.43",
            rejected,
            skeleton_format=SkeletonFormat.BINARY,
            experimental_structural=True,
        )
    ).published
    assert not rejected.exists()


def test_bounded_collections():
    with pytest.raises(BinaryError):
        BinaryCodecRegistry().codec(
            "4.2.43", experimental=True, limits=BinaryLimits(max_count=2)
        ).encode(document())
