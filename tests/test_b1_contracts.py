import json

from fnx_spine_forge.parsers import inspect_skeleton, parse_atlas
from fnx_spine_forge.versions import CapabilityState, VersionRegistry


def test_version_families_are_recognized_without_writer_claim():
    registry = VersionRegistry()
    assert registry.family_for("4.3.12") == "4.3"
    assert registry.family_for("9.1.0") is None
    assert registry.definitions()[0].writer is CapabilityState.NOT_IMPLEMENTED


def test_skeleton_historical_skin_shape_and_image_path():
    payload = json.dumps(
        {
            "skeleton": {"spine": "3.8.75"},
            "bones": [{"name": "root"}],
            "slots": [],
            "skins": {
                "default": {"slot": {"attachment": {"name": "a", "path": "folder/hero face"}}}
            },
            "animations": {},
        }
    ).encode()
    result = inspect_skeleton(payload)
    assert result and result.attachment_paths == ("folder/hero face",)
    assert result.counts["bones"] == 1


def test_atlas_multi_page_and_unknown_fields():
    raw = (
        b"page one.png\nsize: 32,32\n"
        b"filter: Linear,Linear\n\n"
        b"region one\n  xy: 0,0\n"
        b"  strange: keep\n\n"
        b"page two.png\nsize: 16,16\n"
        b"\nregion two\n"
        b"  bounds: 1,2,3,4\n"
    )
    parsed = parse_atlas(raw)
    assert parsed.pages == ("page one.png", "page two.png")
    assert parsed.regions == ("region one", "region two")
    assert ("strange", "keep") in parsed.unknown_attributes
    assert ("size", "32,32") in parsed.page_records[0].attributes
    assert ("xy", "0,0") in parsed.region_records[0].attributes
