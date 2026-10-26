import json

from fnx_spine_forge.conversion import ConversionPlanner
from fnx_spine_forge.parsers import inspect_skeleton, parse_atlas
from fnx_spine_forge.versions import VersionRegistry


def test_version_families_are_recognized_without_writer_claim():
    registry = VersionRegistry()
    assert registry.family_for("4.3.12") == "4.3"
    assert registry.family_for("9.1.0") is None
    assert registry.definitions()[0].family == "3.5"
    assert not ConversionPlanner().structural_plan("3.5", "4.2.43").executable


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


def test_skeleton_parser_accepts_spine_43_combined_constraints():
    payload = json.dumps(
        {
            "skeleton": {"spine": "4.3.13"},
            "bones": [{"name": "root"}],
            "slots": [],
            "skins": [],
            "constraints": [{"name": "aim", "type": "ik", "bones": ["root"]}],
            "animations": {},
        }
    ).encode()
    result = inspect_skeleton(payload)
    assert result is not None
    assert result.names["constraints"] == ("aim",)
    assert not result.diagnostics


def test_skeleton_parser_rejects_malformed_spine_43_constraint_shape():
    payload = json.dumps(
        {
            "skeleton": {"spine": "4.3.13"},
            "bones": [{"name": "root"}],
            "slots": [],
            "skins": [],
            "constraints": {"aim": {"type": "ik"}},
            "animations": {},
        }
    ).encode()
    result = inspect_skeleton(payload)
    assert result is not None
    assert any(code == "UNSUPPORTED_CONSTRAINTS_SHAPE" for code, _ in result.diagnostics)


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
