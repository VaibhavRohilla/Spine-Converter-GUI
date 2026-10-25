"""Independent wire vector, corruption tests and real B2 binary bundle integration."""

import json
import struct
from dataclasses import replace
from pathlib import Path
from zipfile import ZipFile

import pytest

from fnx_spine_forge.binary import (
    BinaryCodecRegistry,
    BinaryError,
    BinaryLimits,
    BinaryReader,
)
from fnx_spine_forge.bundle import BundleRequest, BundleService
from fnx_spine_forge.inspection import InspectionService
from fnx_spine_forge.versions import BINARY_HIERARCHY_VERSION

FIXTURE = Path(__file__).parent / "fixtures/binary/hierarchy_4_2_43.hex"


def vector():
    return bytes.fromhex(FIXTURE.read_text())


def codec():
    return BinaryCodecRegistry().codec(BINARY_HIERARCHY_VERSION, experimental=True)


def test_independent_wire_vector_decode():
    # Expected constants are specified independently, not derived by FNX encoding.
    doc = codec().decode(vector())
    assert doc["skeleton"]["spine"] == "4.2.43"
    assert doc["skeleton"]["width"] == 64 and doc["skeleton"]["height"] == 32
    assert doc["bones"] == [
        {
            "name": "root",
            "rotation": 10.0,
            "x": 2.0,
            "y": -3.0,
            "scaleX": 1.0,
            "scaleY": 1.0,
            "shearX": 0.0,
            "shearY": 0.0,
            "length": 5.0,
            "inherit": "normal",
            "skin": False,
        }
    ]
    assert codec().encode(doc) == vector()


def test_encode_independent_layout_and_nonessential_roundtrip():
    doc = {"skeleton": {"spine": "4.2.43"}, "bones": [{"name": "root", "x": 8.5}]}
    data = codec().encode(doc)
    # Independent primitive interpretation: no FNX reader participates here.
    assert data[:16] == bytes(8) + b"\x074.2.43" + b"\0"
    assert struct.unpack(">5f", data[15:35]) == (0, 0, 0, 0, 100)
    assert data[35:43] == b"\0\0\1\5root"
    assert struct.unpack(">8f", data[43:75]) == (0, 8.5, 0, 1, 1, 0, 0, 0)
    doc = {
        "skeleton": {"spine": "4.2.43", "fps": 60, "images": "图片/"},
        "bones": [
            {"name": "root", "icon": "bone", "color": "010203ff", "visible": False},
            {"name": "child", "parent": "root", "inherit": "noScale", "skin": True},
        ],
    }
    decoded = codec().decode(codec().encode(doc))
    assert decoded["skeleton"]["images"] == "图片/"
    assert decoded["bones"][0]["color"] == "010203ff"
    assert decoded["bones"][1]["parent"] == "root"
    assert codec().encode(decoded) == codec().encode(doc)


@pytest.mark.parametrize("length", range(0, 86))
def test_every_truncation(length):
    data = vector()
    if length >= len(data):
        return
    with pytest.raises(BinaryError):
        codec().decode(data[:length])


@pytest.mark.parametrize(
    "payload,code",
    [
        (b"\xff\xff\xff\xff\x10", "BINARY_VARINT"),
        (b"\x80\x00", "BINARY_VARINT"),
    ],
)
def test_varint_corruption(payload, code):
    with pytest.raises(BinaryError) as error:
        BinaryReader(payload).varint()
    assert error.value.code == code


def test_security_limits_invalid_data_and_unsupported_constructs():
    with pytest.raises(BinaryError):
        BinaryReader(bytes(10), BinaryLimits(max_bytes=9))
    with pytest.raises(BinaryError):
        BinaryReader(b"\x05abc", BinaryLimits(max_string_bytes=2)).string()
    with pytest.raises(BinaryError):
        BinaryReader(b"\x03", BinaryLimits(max_count=2)).count()
    for payload in (b"\0" * 20, b"JSON disguised as binary"):
        with pytest.raises(BinaryError):
            BinaryCodecRegistry().probe(payload)
    with pytest.raises(BinaryError):
        BinaryCodecRegistry().codec("3.8.99", experimental=True)
    with pytest.raises(BinaryError):
        BinaryCodecRegistry().codec("4.2.43")
    bad = bytearray(vector())
    bad[43:47] = struct.pack(">f", float("nan"))
    with pytest.raises(BinaryError, match="Non-finite"):
        codec().decode(bytes(bad))
    with pytest.raises(BinaryError, match="trailing"):
        codec().decode(vector() + b"junk")
    bad = bytearray(vector())
    bad[-9] = 1  # Slots are outside the implemented contract, not silently skipped.
    with pytest.raises(BinaryError, match="slots"):
        codec().decode(bytes(bad))
    for extension in (
        {"slots": [{}]},
        {"animations": {"walk": {}}},
        {"skins": [{"attachments": {"mesh": {"vertices": [0, 1]}}}]},
        {"future": True},
    ):
        with pytest.raises(BinaryError):
            codec().encode(
                {"skeleton": {"spine": "4.2.43"}, "bones": [{"name": "root"}]} | extension
            )
    with pytest.raises(BinaryError, match="Parent"):
        codec().encode(
            {
                "skeleton": {"spine": "4.2.43"},
                "bones": [{"name": "root"}, {"name": "bad", "parent": "missing"}],
            }
        )


def test_binary_bundle_json_and_binary_outputs(tmp_path):
    source = tmp_path / "source"
    source.mkdir()
    (source / "asset.skel").write_bytes(vector())
    fixtures = Path(__file__).parent / "fixtures/spine38"
    (source / "asset.atlas").write_bytes((fixtures / "golden_ingot.atlas").read_bytes())
    (source / "golden_ingot.png").write_bytes((fixtures / "golden_ingot.png").read_bytes())
    manifest = InspectionService().inspect(str(source))
    asset = next(a for a in manifest.assets if a.path == "asset.skel")
    assert asset.spine_version == "4.2.43"
    service = BundleService()
    req = BundleRequest(source, "4.2.43", tmp_path / "json.zip", experimental_structural=True)
    result = service.convert_bundle(req)
    assert result.published, result.report
    with ZipFile(req.output) as z:
        assert json.loads(z.read("asset.json"))["bones"][0]["x"] == 2
    binary_req = replace(req, skeleton_format="binary", output=tmp_path / "binary.zip")
    result = service.convert_bundle(binary_req)
    assert result.published, result.report
    with ZipFile(binary_req.output) as z:
        assert codec().decode(z.read("asset.skel"))["bones"][0]["y"] == -3
    assert (source / "asset.skel").read_bytes() == vector()
    assert not service.convert_bundle(replace(req, experimental_structural=False)).published
    assert not BinaryCodecRegistry().capabilities()[0].semantically_qualified


@pytest.mark.parametrize(
    "offset,value,code",
    [(75, 255, "BINARY_INHERIT"), (76, 2, "BINARY_BOOLEAN"), (38, 1, "BINARY_BONE_NAME")],
)
def test_invalid_bone_records(offset, value, code):
    data = bytearray(vector())
    data[offset] = value
    with pytest.raises(BinaryError) as error:
        codec().decode(bytes(data))
    assert error.value.code == code


def test_decoder_invalid_parent_and_excessive_bones():
    data = vector()
    malformed = data[:37] + b"\x02" + data[38:77] + b"\x06child\x01"
    with pytest.raises(BinaryError) as error:
        codec().decode(malformed)
    assert error.value.code == "BINARY_BONE_INDEX"
    with pytest.raises(BinaryError) as error:
        codec().decode(data[:37] + b"\xff\xff\xff\xff\x0f")
    assert error.value.code == "BINARY_COUNT_LIMIT"
    for value in (False, "", {}):
        with pytest.raises(BinaryError):
            codec().encode(
                {"skeleton": {"spine": "4.2.43"}, "bones": [{"name": "root"}], "slots": value}
            )
    with pytest.raises(BinaryError):
        codec().encode({"skeleton": {"spine": "4.2.43"}, "bones": [{"name": "\ud800"}]})


@pytest.mark.parametrize("output_format", ["json", "binary"])
def test_binary_retention_does_not_retain_superseded_selected_skeleton(tmp_path, output_format):
    from fnx_spine_forge.bundle import RetentionPolicy, SkeletonFormat

    source = tmp_path / "source"
    source.mkdir()
    (source / "setup.skel").write_bytes(vector())
    fixture = Path(__file__).parent / "fixtures/spine38"
    for name in ("golden_ingot.atlas", "golden_ingot.png"):
        (source / name).write_bytes((fixture / name).read_bytes())
    (source / "notes.txt").write_bytes(b"retained")
    req = BundleRequest(
        source,
        "4.2.43",
        tmp_path / "out.zip",
        skeleton_format=SkeletonFormat(output_format),
        experimental_structural=True,
        retention=RetentionPolicy.ALL,
    )
    result = BundleService().convert_bundle(req)
    assert result.published, result.report
    with ZipFile(req.output) as z:
        assert "notes.txt" in z.namelist()
        skeletons = [n for n in z.namelist() if n.endswith((".json", ".skel"))]
        assert skeletons == ["setup.json" if output_format == "json" else "setup.skel"]
    assert result.report["excluded_files"] == ()


def test_directional_capabilities_are_independent():
    from fnx_spine_forge.binary import BinarySkeletonCodec

    capability = BinaryCodecRegistry().capabilities()[0]
    decoder_only = BinarySkeletonCodec(replace(capability, encode=False), experimental=True)
    document = decoder_only.decode(vector())
    with pytest.raises(BinaryError, match="no encoder"):
        decoder_only.encode(document)
    encoder_only = BinarySkeletonCodec(replace(capability, decode=False), experimental=True)
    assert encoder_only.encode(document) == vector()
    with pytest.raises(BinaryError, match="no decoder"):
        encoder_only.decode(vector())
    with pytest.raises(BinaryError, match="authorization"):
        BinarySkeletonCodec(capability)
