import json

import pytest

from fnx_spine_forge.conversion import AtlasConverter, ConversionPlanner, SkeletonConverter
from fnx_spine_forge.conversion.models import ConversionStatus
from fnx_spine_forge.parsers import parse_atlas


def skeleton(version="4.2.43"):
    return json.dumps(
        {
            "skeleton": {"spine": version},
            "bones": [{"name": "root"}],
            "slots": [],
            "skins": [],
            "animations": {
                "idle": {
                    "bones": {
                        "root": {
                            "rotate": [{"time": 0, "angle": 10, "curve": [0.2, 0.3, 0.7, 0.8]}]
                        }
                    }
                }
            },
        }
    ).encode()


def test_skeleton_exact_version_conversion_preserves_semantics():
    source = skeleton()
    result = SkeletonConverter().convert(source, "4.2.43")
    assert result.status is ConversionStatus.STRUCTURALLY_VERIFIED
    assert result.output is not None
    assert json.loads(result.output) == json.loads(source)
    assert source == skeleton()
    assert not result.runtime_verified and not result.visually_verified


def test_skeleton_cross_family_route_is_rejected():
    from pathlib import Path

    source = Path(__file__).parent / "fixtures/spine38/golden_ingot.json"
    result = SkeletonConverter().convert(source, "4.2.43")
    assert result.status is ConversionStatus.STRUCTURALLY_VERIFIED
    assert result.output is not None


def test_planner_does_not_infer_route_from_recognition():
    plan = ConversionPlanner().plan("3.8.75", "4.2.43")
    assert not plan.executable


def test_converter_planner_registers_only_the_exact_qualified_patch_pair():
    converter = SkeletonConverter()
    assert converter.planner.plan("3.8.75", "4.2.43").executable
    assert not converter.planner.plan("3.8.76", "4.2.43").executable
    assert not converter.planner.plan("4.2.43", "3.8.75").executable


def test_atlas_multi_page_round_trip_and_indexed_duplicate_names():
    source = (
        b"page.png\nsize: 128, 128\nfilter: Linear, Linear\n\n"
        b"shared\n  rotate: false\n  xy: 1, 2\n  size: 3, 4\n  index: 0\n\n"
        b"shared\n  rotate: false\n  xy: 5, 6\n  size: 3, 4\n  index: 1\n\n"
        b"page2.png\nsize: 64, 64\n\nother\n  xy: 0, 0\n  size: 2, 2\n"
    )
    assert parse_atlas(source).duplicate_regions == ()
    output = AtlasConverter().convert(source)
    parsed = parse_atlas(output)
    assert parsed.pages == ("page.png", "page2.png")
    assert parsed.regions == ("shared", "shared", "other")
    assert parsed.region_records == parse_atlas(source).region_records


def test_atlas_rejects_malformed_source():
    with pytest.raises(ValueError):
        AtlasConverter().convert(b"region-before-page\n")


def test_real_38_75_to_42_43_migrates_curves_and_schema():
    from pathlib import Path

    source_path = Path(__file__).parent / "fixtures/spine38/golden_ingot.json"
    source = source_path.read_bytes()
    result = SkeletonConverter().convert(source, "4.2.43")
    assert result.status is ConversionStatus.STRUCTURALLY_VERIFIED
    assert result.output is not None
    converted = json.loads(result.output)
    assert converted["skeleton"]["spine"] == "4.2.43"
    assert "transform" not in converted["bones"][0]
    assert "rgba" in converted["animations"]["idle"]["slots"]["02_Gold_Ingot_Foreground2"]
    curve = converted["animations"]["idle"]["slots"]["02_Gold_Ingot_Foreground2"]["rgba"][0][
        "curve"
    ]
    assert len(curve) == 16
    assert result.statistics is not None
    assert result.statistics["bones"] == 5
    assert result.statistics["slots"] == 8
    assert result.statistics["skins"] == 1
    assert result.statistics["bezier_segments"] > 0
    assert result.statistics["max_numerical_error"] <= 1e-12
    assert source_path.read_bytes() == source
    assert SkeletonConverter().convert(source, "4.2.43").output == result.output


def test_real_38_atlas_migrates_region_geometry_without_texture_changes():
    from pathlib import Path

    root = Path(__file__).parent / "fixtures/spine38"
    converter = AtlasConverter()
    source = (root / "golden_ingot.atlas").read_bytes()
    texture = (root / "golden_ingot.png").read_bytes()
    output = converter.convert(source, "4.2.43", source_version="3.8.75")
    parsed = parse_atlas(output)
    assert parsed.pages == ("golden_ingot.png",)
    assert len(parsed.regions) == 6
    assert dict(parsed.region_records[0].attributes)["rotate"] == "90"
    assert "bounds" in dict(parsed.region_records[0].attributes)
    assert "offsets" in dict(parsed.region_records[3].attributes)
    assert (root / "golden_ingot.png").read_bytes() == texture


def test_exact_route_registry_does_not_expand_patch_policy():
    planner = ConversionPlanner({("3.8.75", "4.2.43")})
    assert planner.plan("3.8.75", "4.2.43").executable
    assert not planner.plan("3.8.76", "4.2.43").executable
    assert not planner.plan("3.8.75", "4.2.44").executable


def test_38_migration_fails_closed_for_unknown_timeline_and_invalid_curve():
    unknown = json.loads(skeleton("3.8.75"))
    unknown["animations"]["idle"]["bones"] = {"root": {"future": [{"time": 0}]}}
    assert (
        SkeletonConverter().convert(json.dumps(unknown).encode(), "4.2.43").status
        is ConversionStatus.REJECTED
    )

    malformed = json.loads(skeleton("3.8.75"))
    frame = malformed["animations"]["idle"]["bones"]["root"]["rotate"][0]
    frame["curve"] = 1.4
    assert (
        SkeletonConverter().convert(json.dumps(malformed).encode(), "4.2.43").status
        is ConversionStatus.REJECTED
    )


def test_38_migration_rejects_missing_linked_mesh_parent_and_bad_constraint_reference():
    linked = json.loads(skeleton("3.8.75"))
    linked["skins"] = [
        {
            "name": "default",
            "attachments": {"slot": {"broken": {"type": "linkedmesh", "parent": "absent"}}},
        }
    ]
    assert (
        SkeletonConverter().convert(json.dumps(linked).encode(), "4.2.43").status
        is ConversionStatus.REJECTED
    )

    invalid_constraint = json.loads(skeleton("3.8.75"))
    invalid_constraint["ik"] = [{"name": "bad", "bones": ["missing"], "target": "root"}]
    assert (
        SkeletonConverter().convert(json.dumps(invalid_constraint).encode(), "4.2.43").status
        is ConversionStatus.REJECTED
    )


def test_38_migration_rejects_invalid_deform_and_missing_schema_fields():
    source = json.loads(skeleton("3.8.75"))
    source["skins"] = [
        {"name": "default", "attachments": {"slot": {"mesh": {"type": "mesh", "vertices": [0, 1]}}}}
    ]
    source["animations"]["idle"]["deform"] = {
        "default": {"slot": {"mesh": [{"time": 0, "vertices": ["bad"]}]}}
    }
    assert (
        SkeletonConverter().convert(json.dumps(source).encode(), "4.2.43").status
        is ConversionStatus.REJECTED
    )

    missing = {"skeleton": {"spine": "3.8.75"}, "bones": []}
    assert (
        SkeletonConverter().convert(json.dumps(missing).encode(), "4.2.43").status
        is ConversionStatus.REJECTED
    )
    assert (
        SkeletonConverter().convert(skeleton("3.8.75"), "4.2").status is ConversionStatus.REJECTED
    )


def test_38_migration_rejects_empty_attachment_path_and_downgrade():
    source = json.loads(skeleton("3.8.75"))
    source["skins"] = [
        {
            "name": "default",
            "attachments": {"slot": {"bad": {"path": "", "width": 1, "height": 1}}},
        }
    ]
    assert (
        SkeletonConverter().convert(json.dumps(source).encode(), "4.2.43").status
        is ConversionStatus.REJECTED
    )
    assert (
        SkeletonConverter().convert(skeleton("4.2.43"), "3.8.75").status
        is ConversionStatus.REJECTED
    )


def test_synthetic_38_fixture_covers_constraint_deform_and_draw_order_migrations():
    source = {
        "skeleton": {"spine": "3.8.75"},
        "bones": [
            {"name": "root", "transform": "noScaleOrReflection"},
            {"name": "child", "parent": "root"},
        ],
        "slots": [
            {"name": "slot", "bone": "root", "attachment": "mesh"},
            {"name": "clip", "bone": "root"},
        ],
        "ik": [{"name": "ik", "bones": ["child"], "target": "root"}],
        "transform": [{"name": "tc", "bones": ["child"], "target": "root", "translateMix": 0.5}],
        "path": [{"name": "pc", "bones": ["child"], "target": "slot", "translateMix": 0.75}],
        "skins": [
            {
                "name": "default",
                "ik": ["ik"],
                "transform": ["tc"],
                "path": ["pc"],
                "attachments": {
                    "slot": {
                        "mesh": {
                            "type": "mesh",
                            "uvs": [0, 0, 1, 0],
                            "vertices": [0, 0, 1, 0],
                            "triangles": [0, 1, 0],
                            "hull": 2,
                            "path": "image/mesh",
                        },
                        "weighted": {
                            "type": "mesh",
                            "uvs": [0, 0],
                            "vertices": [1, 0, 1, 2, 1],
                            "triangles": [0, 0, 0],
                            "hull": 1,
                            "path": "image/weighted",
                        },
                        "linked": {
                            "type": "linkedmesh",
                            "parent": "mesh",
                            "deform": False,
                            "path": "image/mesh",
                        },
                        "point": {"type": "point", "x": 2, "y": 3},
                        "box": {
                            "type": "boundingbox",
                            "vertexCount": 3,
                            "vertices": [0, 0, 1, 0, 0, 1],
                        },
                        "pathAttachment": {
                            "type": "path",
                            "vertexCount": 4,
                            "vertices": [0, 0, 1, 0, 2, 0, 3, 0],
                            "lengths": [3],
                        },
                    },
                    "clip": {
                        "clipper": {
                            "type": "clipping",
                            "end": "clip",
                            "vertexCount": 3,
                            "vertices": [0, 0, 1, 0, 0, 1],
                        }
                    },
                },
            }
        ],
        "events": {"hit": {"int": 1}},
        "animations": {
            "move": {
                "bones": {
                    "child": {
                        "rotate": [
                            {"time": 0, "angle": 0, "curve": 0.2, "c2": 0.3, "c3": 0.7, "c4": 0.8},
                            {"time": 1, "angle": 90},
                        ],
                        "translate": [{"time": 0}, {"time": 1, "x": -5, "y": 10}],
                        "scale": [{"time": 0}, {"time": 1, "x": 2, "y": 0.5}],
                        "shear": [{"time": 0}, {"time": 1, "x": 5, "y": -5}],
                    }
                },
                "slots": {
                    "slot": {
                        "attachment": [{"time": 0, "name": "mesh"}],
                        "color": [{"time": 0, "color": "FFFFFFFF"}],
                        "twoColor": [{"time": 0, "light": "FFFFFFFF", "dark": "000000"}],
                    }
                },
                "ik": {"ik": [{"time": 0, "mix": 0.2}, {"time": 1, "mix": 0.8}]},
                "transform": {
                    "tc": [{"time": 0, "translateMix": 0.1}, {"time": 1, "translateMix": 0.9}]
                },
                "path": {
                    "pc": {
                        "position": [{"time": 0, "position": 0}, {"time": 1, "position": 5}],
                        "mix": [{"time": 0, "rotateMix": 0.2, "translateMix": 0.4}, {"time": 1}],
                    }
                },
                "deform": {
                    "default": {
                        "slot": {
                            "mesh": [
                                {"time": 0, "vertices": [0, 0], "curve": 0.25, "c3": 0.75},
                                {"time": 1, "vertices": [1, 2]},
                            ],
                            "weighted": [
                                {"time": 0, "vertices": [0.1, 0.2]},
                                {"time": 1, "vertices": [0.3, 0.4]},
                            ],
                        }
                    }
                },
                "draworder": [{"time": 0, "offsets": [{"slot": "slot", "offset": 1}]}],
                "events": [{"time": 0.5, "name": "hit"}],
            }
        },
    }
    result = SkeletonConverter().convert(json.dumps(source).encode(), "4.2.43")
    assert result.status is ConversionStatus.STRUCTURALLY_VERIFIED, result.diagnostics
    assert result.output is not None
    target = json.loads(result.output)
    assert target["bones"][0]["inherit"] == "NoScaleOrReflection"
    assert target["transform"][0]["mixX"] == target["transform"][0]["mixY"] == 0.5
    assert target["path"][0]["mixX"] == target["path"][0]["mixY"] == 0.75
    assert target["skins"][0]["attachments"]["slot"]["linked"]["timelines"] is False
    assert target["skins"][0]["attachments"]["slot"]["weighted"]["vertices"] == [
        1,
        0,
        1,
        2,
        1,
    ]
    animation = target["animations"]["move"]
    assert "drawOrder" in animation and "draworder" not in animation
    assert "attachments" in animation and "deform" not in animation
    deform = animation["attachments"]["default"]["slot"]["mesh"]["deform"]
    assert len(deform[0]["curve"]) == 4
    assert animation["bones"]["child"]["rotate"][0]["value"] == 0
    assert result.statistics is not None
    assert result.statistics["max_numerical_error"] <= 1e-12


def test_target_atlas_conversion_handles_multi_page_and_index_fields():
    source = (
        b"p1.png\nsize: 64, 64\nfilter: Linear, Linear\n\n"
        b"icon\nrotate: true\nxy: 1, 2\nsize: 3, 4\norig: 5, 6\noffset: 1, 1\nindex: 0\n\n"
        b"p2.png\nsize: 32, 32\n\n"
        b"icon\nrotate: false\nxy: 0, 1\nsize: 2, 3\norig: 2, 3\noffset: 0, 0\nindex: 1\n"
    )
    output = AtlasConverter().convert(source, "4.2.43", source_version="3.8.75")
    parsed = parse_atlas(output)
    assert parsed.pages == ("p1.png", "p2.png")
    assert parsed.regions == ("icon", "icon")
    assert dict(parsed.region_records[0].attributes)["bounds"] == "1, 2, 3, 4"
    assert dict(parsed.region_records[0].attributes)["offsets"] == "1, 1, 5, 6"
    assert dict(parsed.region_records[1].attributes)["index"] == "1"
    with pytest.raises(ValueError, match="qualified only"):
        AtlasConverter().convert(source, "4.2.43")
