import json
from pathlib import Path

import pytest

from fnx_spine_forge.conversion import (
    AtlasConverter,
    ConversionPlanner,
    SkeletonConverter,
    SourceRiskPolicy,
)
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


def legacy_curve_samples(frame):
    curve = frame.get("curve")
    if not isinstance(curve, (int, float)) or isinstance(curve, bool):
        return None
    controls = (curve, frame.get("c2", 0), frame.get("c3", 1), frame.get("c4", 1))

    def cubic(p1, p2, t):
        inverse = 1 - t
        return 3 * inverse * inverse * t * p1 + 3 * inverse * t * t * p2 + t**3

    values = []
    for sample in range(257):
        x = sample / 256
        low, high = 0.0, 1.0
        for _ in range(48):
            middle = (low + high) / 2
            if cubic(controls[0], controls[2], middle) < x:
                low = middle
            else:
                high = middle
        values.append(cubic(controls[1], controls[3], (low + high) / 2))
    return values


def absolute_curve_samples(frame, next_frame, value_field):
    curve = frame["curve"]
    start_time = frame.get("time", 0)
    duration = next_frame["time"] - start_time
    start_value = frame[value_field]
    end_value = next_frame[value_field]
    x1, y1, x2, y2 = curve

    def cubic(p0, p1, p2, p3, t):
        inverse = 1 - t
        return (
            inverse**3 * p0
            + 3 * inverse**2 * t * p1
            + 3 * inverse * t**2 * p2
            + t**3 * p3
        )

    normalized_x1 = (x1 - start_time) / duration
    normalized_x2 = (x2 - start_time) / duration
    values = []
    for sample in range(257):
        x = sample / 256
        low, high = 0.0, 1.0
        for _ in range(48):
            middle = (low + high) / 2
            if cubic(0, normalized_x1, normalized_x2, 1, middle) < x:
                low = middle
            else:
                high = middle
        values.append(cubic(start_value, y1, y2, end_value, (low + high) / 2))
    return values


def test_skeleton_exact_version_conversion_preserves_semantics():
    source = skeleton()
    result = SkeletonConverter().convert(
        source, "4.2.43", source_risk_policy=SourceRiskPolicy.ALLOW_WITH_DIAGNOSTIC
    )
    assert result.status is ConversionStatus.STRUCTURALLY_VERIFIED
    assert result.output is not None
    assert json.loads(result.output) == json.loads(source)
    assert source == skeleton()
    assert not result.runtime_verified and not result.visually_verified


def test_skeleton_cross_family_route_is_rejected():
    from pathlib import Path

    source = Path(__file__).parent / "fixtures/spine38/golden_ingot.json"
    result = SkeletonConverter().convert(
        source, "4.2.43", source_risk_policy=SourceRiskPolicy.ALLOW_WITH_DIAGNOSTIC
    )
    assert result.status is ConversionStatus.STRUCTURALLY_VERIFIED
    assert result.output is not None


def test_planner_does_not_infer_route_from_recognition():
    plan = ConversionPlanner().plan("3.8.75", "4.2.43")
    assert not plan.executable


def test_converter_planner_registers_only_the_exact_qualified_patch_pair():
    converter = SkeletonConverter()
    assert converter.planner.plan("3.8.75", "4.2.43").executable
    assert converter.planner.plan("3.8.99", "4.2.43").executable
    assert converter.planner.plan("3.8.75", "4.1.56").executable
    assert converter.planner.plan("3.8.99", "4.1.56").executable
    assert converter.planner.plan("3.8.75", "4.0.31").executable
    assert converter.planner.plan("3.8.99", "4.0.31").executable
    assert converter.planner.plan("3.8.75", "4.3.13").executable
    assert converter.planner.plan("3.8.99", "4.3.13").executable
    assert converter.planner.plan("3.8.75", "3.7.94").executable
    assert converter.planner.plan("3.8.99", "3.7.94").executable
    for target in ("3.5.51", "3.6.53"):
        assert converter.planner.plan("3.8.75", target).executable
        assert converter.planner.plan("3.8.99", target).executable
    assert not converter.planner.plan("3.8.76", "4.2.43").executable
    assert not converter.planner.plan("4.2.43", "3.8.75").executable
    assert converter.planner.plan("4.2.43", "4.3.13").executable
    assert converter.planner.plan("4.1.56", "4.2.43").executable
    assert converter.planner.plan("4.0.31", "4.1.56").executable
    assert converter.planner.plan("3.7.94", "3.8.99").executable


@pytest.mark.parametrize("target_version", ["3.5.51", "3.6.53", "3.7.94"])
def test_38_to_legacy_uses_skin_map_schema_and_keeps_runtime_timelines(target_version):
    source_path = Path(__file__).parent / "fixtures/spine38/golden_ingot.json"
    source = source_path.read_bytes()
    result = SkeletonConverter().convert(
        source, target_version, source_risk_policy=SourceRiskPolicy.ALLOW_WITH_DIAGNOSTIC
    )
    assert result.status is ConversionStatus.STRUCTURALLY_VERIFIED, result.diagnostics
    assert result.output is not None
    target = json.loads(result.output)
    original = json.loads(source)
    assert target["skeleton"]["spine"] == target_version
    assert isinstance(target["skins"], dict)
    assert "default" in target["skins"]
    timeline = target["animations"]["idle"]["bones"]["main"]["rotate"][0]
    assert "angle" in timeline
    assert "curve" in timeline
    assert target["animations"] == original["animations"]
    def curve_frames(value):
        frames = []
        stack = [value]
        while stack:
            item = stack.pop()
            if isinstance(item, dict):
                if "curve" in item:
                    frames.append(item)
                stack.extend(item.values())
            elif isinstance(item, list):
                stack.extend(item)
        return frames

    source_curves = curve_frames(original["animations"])
    target_curves = curve_frames(target["animations"])
    assert len(source_curves) == len(target_curves) == result.statistics["bezier_segments"]
    for source_frame, target_frame in zip(source_curves, target_curves, strict=True):
        assert legacy_curve_samples(source_frame) == legacy_curve_samples(target_frame)
    assert result.details["verification_level"] == "structural_only"
    assert result.feature_compatibility["target_runtime"] == "not_executed"
    assert result.provenance["declared_source_version"] == "3.8.75"
    assert result.provenance["source_fidelity"] == "unverified_without_trusted_baseline"
    assert source_path.read_bytes() == source


def test_38_to_37_rejects_unrepresentable_skin_constraints_and_ik_softness():
    source = json.loads(skeleton("3.8.99"))
    source["skins"] = [{"name": "default", "attachments": {}, "ik": ["aim"]}]
    rejected_skin = SkeletonConverter().convert(json.dumps(source).encode(), "3.7.94")
    assert rejected_skin.status is ConversionStatus.REJECTED
    assert any("skin-specific bones or constraints" in item for item in rejected_skin.diagnostics)

    source["skins"][0].pop("ik")
    source["ik"] = [{"name": "aim", "bones": ["root"], "target": "root", "softness": 2}]
    rejected_softness = SkeletonConverter().convert(json.dumps(source).encode(), "3.7.94")
    assert rejected_softness.status is ConversionStatus.REJECTED
    assert any("cannot represent IK softness" in item for item in rejected_softness.diagnostics)


@pytest.mark.parametrize("target_version", ["3.5.51", "3.6.53", "3.7.94"])
def test_38_99_to_legacy_uses_target_writer_and_legacy_atlas(target_version):
    document = json.loads(skeleton("3.8.99"))
    document["animations"] = {"idle": {"bones": {"root": {"rotate": [
        {"time": 0, "angle": 0, "curve": 0.25, "c2": 0.2, "c3": 0.75, "c4": 0.8},
        {"time": 1, "angle": 45},
    ]}}}}
    result = SkeletonConverter().convert(json.dumps(document).encode(), target_version)
    assert result.status is ConversionStatus.STRUCTURALLY_VERIFIED, result.diagnostics
    assert result.statistics["bezier_segments"] == 1
    target = json.loads(result.output)
    assert target["skins"] == {}
    assert target["animations"]["idle"]["bones"]["root"]["rotate"][0]["curve"] == 0.25

    atlas = (
        b"page.png\nsize: 16, 16\n\nregion\n  rotate: false\n  xy: 1, 2\n"
        b"  size: 3, 4\n  orig: 3, 4\n  offset: 0, 0\n"
    )
    converted = AtlasConverter().convert(atlas, target_version, source_version="3.8.99")
    assert parse_atlas(converted).region_records == parse_atlas(atlas).region_records


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
    result = SkeletonConverter().convert(
        source, "4.2.43", source_risk_policy=SourceRiskPolicy.ALLOW_WITH_DIAGNOSTIC
    )
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
    assert (
        SkeletonConverter()
        .convert(source, "4.2.43", source_risk_policy=SourceRiskPolicy.ALLOW_WITH_DIAGNOSTIC)
        .output
        == result.output
    )
    assert "SOURCE_EXPORT_KNOWN_BUG" in result.diagnostic_codes
    assert result.provenance is not None
    assert result.provenance["declared_source_version"] == "3.8.75"
    assert result.provenance["source_fidelity"] == "unverified_without_trusted_baseline"


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


def test_known_3875_export_bug_requires_explicit_risk_policy():
    from pathlib import Path

    source = Path(__file__).parent / "fixtures/spine38/golden_ingot.json"
    result = SkeletonConverter().convert(source, "4.2.43")
    assert result.status is ConversionStatus.REJECTED
    assert result.output is None
    assert result.diagnostic_codes == ("SOURCE_EXPORT_KNOWN_BUG",)
    assert result.provenance == {"declared_source_version": "3.8.75"}


def test_3899_to_4243_uses_schema_migration_and_bundle_dependencies(tmp_path):
    import shutil

    from fnx_spine_forge.inspection import InspectionService

    document = json.loads(skeleton("3.8.99"))
    document["slots"] = [{"name": "item", "bone": "root", "attachment": "token"}]
    document["skins"] = [
        {
            "name": "default",
            "attachments": {
                "item": {"token": {"type": "region", "path": "token"}}
            },
        }
    ]
    first = document["animations"]["idle"]["bones"]["root"]["rotate"][0]
    first["time"] = 0
    first["angle"] = 0
    first["curve"] = 0.2
    first["c2"] = 0.3
    first["c3"] = 0.7
    first["c4"] = 0.8
    document["animations"]["idle"]["bones"]["root"]["rotate"].append(
        {"time": 1, "angle": 30}
    )
    source = json.dumps(document).encode()
    converted = SkeletonConverter().convert(source, "4.2.43")
    assert converted.status is ConversionStatus.STRUCTURALLY_VERIFIED, converted.diagnostics
    assert converted.output is not None
    assert converted.source_version == "3.8.99"
    assert "SOURCE_EXPORT_KNOWN_BUG" not in converted.diagnostic_codes
    target_document = json.loads(converted.output)
    assert target_document["skeleton"]["spine"] == "4.2.43"
    assert converted.statistics is not None
    assert converted.statistics["bezier_segments"] == 1
    assert converted.statistics["max_numerical_error"] <= 1e-12

    source_dir = tmp_path / "source"
    target_dir = tmp_path / "target"
    source_dir.mkdir()
    target_dir.mkdir()
    (source_dir / "item.json").write_bytes(source)
    atlas_bytes = (
        b"page.png\nsize: 1, 1\nfilter: Linear, Linear\n\n"
        b"token\n  rotate: false\n  xy: 0, 0\n  size: 1, 1\n"
    )
    (source_dir / "item.atlas").write_bytes(atlas_bytes)
    shutil.copyfile(
        Path(__file__).parent / "fixtures/spine38/golden_ingot.png", source_dir / "page.png"
    )
    (target_dir / "item.json").write_bytes(converted.output)
    (target_dir / "item.atlas").write_bytes(
        AtlasConverter().convert(atlas_bytes, "4.2.43", source_version="3.8.99")
    )
    shutil.copyfile(source_dir / "page.png", target_dir / "page.png")
    before = InspectionService().inspect(str(source_dir))
    after = InspectionService().inspect(str(target_dir))
    assert before.ok, before.diagnostics
    assert after.ok, after.diagnostics
    assert after.bundles[0].atlases == ("item.atlas",)
    assert after.bundles[0].texture_pages == ("page.png",)


def test_38_to_4156_uses_version_specific_bone_and_atlas_schema():
    document = json.loads(skeleton("3.8.99"))
    document["bones"][0]["transform"] = "NoScale"
    frame = document["animations"]["idle"]["bones"]["root"]["rotate"][0]
    frame.pop("curve")
    source = json.dumps(document).encode()
    result = SkeletonConverter().convert(source, "4.1.56")
    assert result.status is ConversionStatus.STRUCTURALLY_VERIFIED, result.diagnostics
    assert result.output is not None
    target = json.loads(result.output)
    assert target["skeleton"]["spine"] == "4.1.56"
    assert target["bones"][0]["transform"] == "NoScale"
    assert "inherit" not in target["bones"][0]

    legacy_atlas = (
        b"page.png\nsize: 8, 8\nfilter: Linear, Linear\n\n"
        b"sprite\n  rotate: true\n  xy: 1, 2\n  size: 3, 4\n  orig: 5, 6\n  offset: 1, 1\n"
    )
    converted_atlas = AtlasConverter().convert(
        legacy_atlas, "4.1.56", source_version="3.8.99"
    )
    reparsed = parse_atlas(converted_atlas)
    assert reparsed.pages == ("page.png",)
    assert dict(reparsed.region_records[0].attributes)["rotate"] == "true"
    assert "xy" in dict(reparsed.region_records[0].attributes)
    assert "bounds" not in dict(reparsed.region_records[0].attributes)


def test_38_to_4031_preserves_legacy_deform_and_linked_mesh_schema():
    document = json.loads(skeleton("3.8.99"))
    document["bones"][0]["transform"] = "NoScale"
    document["slots"] = [{"name": "item", "bone": "root", "attachment": "child"}]
    document["skins"] = [
        {
            "name": "default",
            "attachments": {
                "item": {
                    "parent": {
                        "type": "mesh",
                        "path": "parent",
                        "uvs": [0, 0, 1, 0, 1, 1],
                        "vertices": [0, 0, 1, 0, 1, 1],
                        "triangles": [0, 1, 2],
                        "hull": 3,
                        "width": 1,
                        "height": 1,
                    },
                    "child": {
                        "type": "linkedmesh",
                        "path": "parent",
                        "parent": "parent",
                        "deform": True,
                    },
                }
            },
        }
    ]
    document["animations"] = {
        "idle": {
            "deform": {
                "default": {
                    "item": {
                        "child": [
                            {"time": 0, "vertices": [0, 0, 0, 0, 0, 0]},
                            {"time": 1, "vertices": [1, 0, 0, 0, 0, 0]},
                        ]
                    }
                }
            }
        }
    }
    result = SkeletonConverter().convert(json.dumps(document).encode(), "4.0.31")
    assert result.status is ConversionStatus.STRUCTURALLY_VERIFIED, result.diagnostics
    assert result.output is not None
    target = json.loads(result.output)
    assert target["skeleton"]["spine"] == "4.0.31"
    assert target["bones"][0]["transform"] == "NoScale"
    assert "inherit" not in target["bones"][0]
    assert target["skins"][0]["attachments"]["item"]["child"]["deform"] is True
    assert "timelines" not in target["skins"][0]["attachments"]["item"]["child"]
    deform_frames = target["animations"]["idle"]["deform"]["default"]["item"]["child"]
    assert isinstance(deform_frames, list)
    assert len(deform_frames) == 2


def test_38_to_4313_combines_constraint_definitions_and_blocks_transform_constraints():
    document = json.loads(skeleton("3.8.99"))
    document["bones"] = [
        {"name": "root"},
        {"name": "effector", "parent": "root"},
        {"name": "target", "parent": "root"},
    ]
    document["slots"] = [{"name": "pathSlot", "bone": "root"}]
    rotate = document["animations"]["idle"]["bones"]["root"]["rotate"]
    rotate[0].pop("curve")
    rotate.append({"time": 1, "angle": 10})
    document["ik"] = [
        {
            "name": "aim",
            "order": 2,
            "bones": ["effector"],
            "target": "target",
            "mix": 0.75,
            "bendPositive": True,
        }
    ]
    document["path"] = [
        {
            "name": "follow",
            "order": 1,
            "bones": ["effector"],
            "slot": "pathSlot",
            "positionMode": "Percent",
            "spacingMode": "Length",
            "rotateMode": "Tangent",
            "position": 0,
            "spacing": 10,
            "rotateMix": 0.5,
            "translateMix": 0.75,
        }
    ]
    document["animations"]["idle"]["ik"] = {
        "aim": [{"time": 0, "mix": 1}, {"time": 1, "mix": 0.5}]
    }
    output = SkeletonConverter().convert(json.dumps(document).encode(), "4.3.13")
    assert output.status is ConversionStatus.STRUCTURALLY_VERIFIED, output.diagnostics
    assert output.output is not None
    target = json.loads(output.output)
    assert target["skeleton"]["spine"] == "4.3.13"
    assert "ik" not in target
    assert target["constraints"] == [
        {
            "name": "follow",
            "bones": ["effector"],
            "slot": "pathSlot",
            "positionMode": "Percent",
            "spacingMode": "Length",
            "rotateMode": "Tangent",
            "position": 0,
            "spacing": 10,
            "mixRotate": 0.5,
            "mixX": 0.75,
            "mixY": 0.75,
            "type": "path",
        },
        {
            "name": "aim",
            "bones": ["effector"],
            "target": "target",
            "mix": 0.75,
            "bendPositive": True,
            "type": "ik",
        }
    ]
    assert target["animations"]["idle"]["ik"]["aim"][1]["mix"] == 0.5

    unsupported = json.loads(skeleton("3.8.99"))
    unsupported["transform"] = [
        {"name": "tc", "bones": ["root"], "target": "root"}
    ]
    rejected = SkeletonConverter().convert(json.dumps(unsupported).encode(), "4.3.13")
    assert rejected.status is ConversionStatus.REJECTED
    assert any(
        "transform constraints use property mappings" in item for item in rejected.diagnostics
    )
    assert rejected.diagnostic_codes == ("UNSUPPORTED_TARGET_FEATURE",)
    assert rejected.unsupported_features == ("transform_constraints",)


def test_real_skeleton_atlas_texture_asset_references_survive_conversion(tmp_path):
    import shutil
    from pathlib import Path

    from fnx_spine_forge.inspection import InspectionService

    fixture = Path(__file__).parent / "fixtures/spine38"
    source_bundle = tmp_path / "source"
    target_bundle = tmp_path / "target"
    source_bundle.mkdir()
    target_bundle.mkdir()
    for filename in ("golden_ingot.json", "golden_ingot.atlas", "golden_ingot.png"):
        shutil.copyfile(fixture / filename, source_bundle / filename)
    original_texture = (source_bundle / "golden_ingot.png").read_bytes()

    skeleton_converter = SkeletonConverter()
    result = skeleton_converter.convert(
        source_bundle / "golden_ingot.json",
        "4.2.43",
        source_risk_policy=SourceRiskPolicy.ALLOW_WITH_DIAGNOSTIC,
    )
    assert result.output is not None
    (target_bundle / "golden_ingot.json").write_bytes(result.output)
    (target_bundle / "golden_ingot.atlas").write_bytes(
        AtlasConverter().convert(
            source_bundle / "golden_ingot.atlas",
            "4.2.43",
            source_version="3.8.75",
        )
    )
    shutil.copyfile(source_bundle / "golden_ingot.png", target_bundle / "golden_ingot.png")

    inspect = InspectionService()
    before = inspect.inspect(str(source_bundle))
    after = inspect.inspect(str(target_bundle))
    assert before.ok, before.diagnostics
    assert after.ok, after.diagnostics
    blocking_codes = {
        "MISSING_TEXTURE",
        "AMBIGUOUS_TEXTURE",
        "AMBIGUOUS_ATLAS",
        "ATLAS_REGION_MISSING",
    }
    assert not (blocking_codes & {item.code for item in after.diagnostics})
    source_skeleton = next(item for item in before.assets if item.kind == "skeleton_json")
    target_skeleton = next(item for item in after.assets if item.kind == "skeleton_json")
    assert tuple(source_skeleton.metadata["attachment_paths"]) == tuple(
        target_skeleton.metadata["attachment_paths"]
    )
    assert (target_bundle / "golden_ingot.png").read_bytes() == original_texture
    assert len(after.bundles) == 1
    assert after.bundles[0].atlases == ("golden_ingot.atlas",)
    assert after.bundles[0].texture_pages == ("golden_ingot.png",)


@pytest.mark.parametrize("target_version", ["3.5.51", "3.6.53", "3.7.94"])
def test_38_to_legacy_complete_asset_set_resolves_all_dependencies(tmp_path, target_version):
    import shutil

    from fnx_spine_forge.inspection import InspectionService

    fixture = Path(__file__).parent / "fixtures/spine38"
    source = tmp_path / "source37"
    target = tmp_path / f"target_{target_version.replace('.', '_')}"
    source.mkdir()
    target.mkdir()
    for name in ("golden_ingot.json", "golden_ingot.atlas", "golden_ingot.png"):
        shutil.copyfile(fixture / name, source / name)
    converted = SkeletonConverter().convert(
        source / "golden_ingot.json",
        target_version,
        source_risk_policy=SourceRiskPolicy.ALLOW_WITH_DIAGNOSTIC,
    )
    assert converted.output is not None
    (target / "golden_ingot.json").write_bytes(converted.output)
    (target / "golden_ingot.atlas").write_bytes(
        AtlasConverter().convert(
            source / "golden_ingot.atlas", target_version, source_version="3.8.75"
        )
    )
    shutil.copyfile(source / "golden_ingot.png", target / "golden_ingot.png")
    before = InspectionService().inspect(str(source))
    after = InspectionService().inspect(str(target))
    assert before.ok, before.diagnostics
    assert after.ok, after.diagnostics
    assert after.bundles[0].atlases == ("golden_ingot.atlas",)
    assert after.bundles[0].texture_pages == ("golden_ingot.png",)
    source_skeleton = next(item for item in before.assets if item.kind == "skeleton_json")
    target_skeleton = next(item for item in after.assets if item.kind == "skeleton_json")
    assert source_skeleton.metadata["attachment_paths"] == target_skeleton.metadata[
        "attachment_paths"
    ]
    assert (target / "golden_ingot.png").read_bytes() == (source / "golden_ingot.png").read_bytes()


@pytest.mark.parametrize("target_version", ["3.5.51", "3.6.53", "3.7.94"])
def test_synthetic_38_99_legacy_bundle_preserves_region_and_texture_dependencies(
    tmp_path, target_version
):
    import shutil

    from fnx_spine_forge.inspection import InspectionService

    source = tmp_path / "source"
    target = tmp_path / "target"
    source.mkdir()
    target.mkdir()
    document = {
        "skeleton": {"spine": "3.8.99", "images": ""},
        "bones": [{"name": "root"}],
        "slots": [{"name": "slot", "bone": "root", "attachment": "wheel"}],
        "skins": [{
            "name": "default",
            "attachments": {
                "slot": {"wheel": {"type": "region", "path": "Wheel", "width": 1, "height": 1}}
            },
        }],
        "animations": {},
    }
    (source / "synthetic.json").write_text(json.dumps(document), encoding="utf-8")
    fixture = Path(__file__).parent / "fixtures/spine38"
    shutil.copyfile(fixture / "golden_ingot.atlas", source / "golden_ingot.atlas")
    shutil.copyfile(fixture / "golden_ingot.png", source / "golden_ingot.png")
    result = SkeletonConverter().convert(source / "synthetic.json", target_version)
    assert result.output is not None, result.diagnostics
    (target / "synthetic.json").write_bytes(result.output)
    (target / "golden_ingot.atlas").write_bytes(
        AtlasConverter().convert(
            source / "golden_ingot.atlas", target_version, source_version="3.8.99"
        )
    )
    shutil.copyfile(source / "golden_ingot.png", target / "golden_ingot.png")
    before = InspectionService().inspect(str(source))
    after = InspectionService().inspect(str(target))
    assert before.ok, before.diagnostics
    assert after.ok, after.diagnostics
    assert after.bundles[0].texture_pages == ("golden_ingot.png",)
    assert (target / "golden_ingot.png").read_bytes() == (source / "golden_ingot.png").read_bytes()


def test_direct_42_to_43_converts_constraints_and_preserves_channel_curves():
    document = json.loads(skeleton("4.2.43"))
    document["animations"]["idle"]["bones"]["root"]["rotate"] = [
        {"time": 0, "value": 0, "curve": [0.2, 1, 0.7, 2]},
        {"time": 1, "value": 45},
    ]
    document["ik"] = [
        {
            "name": "aim",
            "order": 2,
            "bones": ["root"],
            "target": "root",
            "mix": 0.75,
            "bendPositive": True,
        }
    ]
    document["animations"]["idle"]["ik"] = {
        "aim": [
            {"time": 0, "mix": 1, "curve": [0.2, 0.1, 0.8, 0.9]},
            {"time": 1, "mix": 0.5},
        ]
    }
    source = json.dumps(document).encode()
    result = SkeletonConverter().convert(source, "4.3.13")
    assert result.status is ConversionStatus.STRUCTURALLY_VERIFIED, result.diagnostics
    assert result.output is not None
    target = json.loads(result.output)
    assert target["skeleton"]["spine"] == "4.3.13"
    assert target["constraints"][0]["type"] == "ik"
    assert "ik" not in target
    assert target["animations"]["idle"]["bones"]["root"]["rotate"][0]["curve"] == [
        0.2, 1, 0.7, 2
    ]
    assert result.statistics["bezier_segments"] == 2
    source_rotation = document["animations"]["idle"]["bones"]["root"]["rotate"]
    target_rotation = target["animations"]["idle"]["bones"]["root"]["rotate"]
    source_ik = document["animations"]["idle"]["ik"]["aim"]
    target_ik = target["animations"]["idle"]["ik"]["aim"]
    rotation_error = max(
        abs(a - b)
        for a, b in zip(
            absolute_curve_samples(source_rotation[0], source_rotation[1], "value"),
            absolute_curve_samples(target_rotation[0], target_rotation[1], "value"),
            strict=True,
        )
    )
    ik_error = max(
        abs(a - b)
        for a, b in zip(
            absolute_curve_samples(source_ik[0], source_ik[1], "mix"),
            absolute_curve_samples(target_ik[0], target_ik[1], "mix"),
            strict=True,
        )
    )
    assert max(rotation_error, ik_error) <= 1e-12
    assert source == json.dumps(document).encode()
    repeated = SkeletonConverter().convert(source, "4.3.13")
    assert repeated.output == result.output

    document["transform"] = [{"name": "copy", "bones": ["root"], "target": "root"}]
    rejected = SkeletonConverter().convert(json.dumps(document).encode(), "4.3.13")
    assert rejected.status is ConversionStatus.REJECTED
    assert rejected.unsupported_features == ("transform_constraints",)


def test_direct_42_to_43_preserves_modern_atlas_semantics():
    legacy = Path(__file__).parent / "fixtures/spine38/golden_ingot.atlas"
    atlas_42 = AtlasConverter().convert(
        legacy, "4.2.43", source_version="3.8.75"
    )
    atlas_43 = AtlasConverter().convert(
        atlas_42, "4.3.13", source_version="4.2.43"
    )
    assert parse_atlas(atlas_43).page_records == parse_atlas(atlas_42).page_records
    assert parse_atlas(atlas_43).region_records == parse_atlas(atlas_42).region_records


def test_direct_41_to_42_migrates_transform_modes_and_atlas():
    document = json.loads(skeleton("4.1.56"))
    document["bones"][0]["transform"] = "NoScale"
    document["animations"]["idle"]["bones"]["root"]["rotate"] = [
        {"time": 0, "value": 0, "curve": [0.2, 1, 0.7, 2]},
        {"time": 1, "value": 45},
    ]
    source = json.dumps(document).encode()
    result = SkeletonConverter().convert(source, "4.2.43")
    assert result.status is ConversionStatus.STRUCTURALLY_VERIFIED, result.diagnostics
    assert result.output is not None
    target = json.loads(result.output)
    assert target["skeleton"]["spine"] == "4.2.43"
    assert "transform" not in target["bones"][0]
    assert target["bones"][0]["inherit"] == "NoScale"
    assert target["animations"] == document["animations"]
    assert result.statistics["max_numerical_error"] == 0
    assert result.output == SkeletonConverter().convert(source, "4.2.43").output
    source_frames = document["animations"]["idle"]["bones"]["root"]["rotate"]
    target_frames = target["animations"]["idle"]["bones"]["root"]["rotate"]
    source_samples = absolute_curve_samples(source_frames[0], source_frames[1], "value")
    target_samples = absolute_curve_samples(target_frames[0], target_frames[1], "value")
    assert max(abs(a - b) for a, b in zip(source_samples, target_samples, strict=True)) <= 1e-12

    atlas_41 = Path(__file__).parent / "fixtures/spine38/golden_ingot.atlas"
    atlas_42 = AtlasConverter().convert(
        atlas_41, "4.2.43", source_version="4.1.56"
    )
    assert {key for key, _ in parse_atlas(atlas_42).region_records[0].attributes} >= {
        "rotate", "bounds", "offsets"
    }

    invalid = json.loads(source)
    invalid["bones"][0]["inherit"] = "Normal"
    rejected = SkeletonConverter().convert(json.dumps(invalid).encode(), "4.2.43")
    assert rejected.status is ConversionStatus.REJECTED


def test_direct_41_to_42_real_bundle_reinspection(tmp_path):
    import shutil

    from fnx_spine_forge.inspection import InspectionService

    fixture = Path(__file__).parent / "fixtures/spine38"
    converter = SkeletonConverter()
    source = (fixture / "golden_ingot.json").read_bytes()
    result_41 = converter.convert(
        source, "4.1.56", source_risk_policy=SourceRiskPolicy.ALLOW_WITH_DIAGNOSTIC
    )
    assert result_41.output is not None
    result_42 = converter.convert(result_41.output, "4.2.43")
    assert result_42.output is not None, result_42.diagnostics
    atlas_41 = AtlasConverter().convert(
        (fixture / "golden_ingot.atlas").read_bytes(), "4.1.56", source_version="3.8.75"
    )
    atlas_42 = AtlasConverter().convert(atlas_41, "4.2.43", source_version="4.1.56")
    target = tmp_path / "bundle42"
    target.mkdir()
    (target / "golden_ingot.json").write_bytes(result_42.output)
    (target / "golden_ingot.atlas").write_bytes(atlas_42)
    shutil.copyfile(fixture / "golden_ingot.png", target / "golden_ingot.png")
    inspected = InspectionService().inspect(str(target))
    assert inspected.ok, inspected.diagnostics
    assert inspected.bundles[0].texture_pages == ("golden_ingot.png",)


def test_direct_40_to_41_migrates_linked_mesh_and_deform_schema():
    document = json.loads(skeleton("4.0.31"))
    document["bones"][0]["transform"] = "NoScale"
    document["slots"] = [{"name": "slot", "bone": "root", "attachment": "mesh"}]
    document["skins"] = [
        {
            "name": "default",
            "attachments": {
                "slot": {
                    "mesh": {
                        "type": "mesh",
                        "path": "image/mesh",
                        "uvs": [0, 0, 1, 0],
                        "vertices": [0, 0, 1, 0],
                        "triangles": [0, 1, 0],
                        "hull": 2,
                    },
                    "linked": {
                        "type": "linkedmesh",
                        "path": "image/mesh",
                        "parent": "mesh",
                        "deform": True,
                    },
                }
            },
        }
    ]
    frames = [
        {"time": 0, "vertices": [0, 0], "curve": [0.2, 0, 0.7, 1]},
        {"time": 1, "vertices": [1, 2]},
    ]
    document["animations"]["idle"] = {
        "deform": {"default": {"slot": {"mesh": frames}}}
    }
    source = json.dumps(document).encode()
    result = SkeletonConverter().convert(source, "4.1.56")
    assert result.status is ConversionStatus.STRUCTURALLY_VERIFIED, result.diagnostics
    assert result.output is not None
    target = json.loads(result.output)
    assert target["bones"][0]["transform"] == "NoScale"
    assert target["skins"][0]["attachments"]["slot"]["linked"]["timelines"] is True
    assert "deform" not in target["animations"]["idle"]
    assert target["animations"]["idle"]["attachments"]["default"]["slot"]["mesh"] == {
        "deform": frames
    }
    assert result.statistics["bezier_segments"] == 1
    assert result.output == SkeletonConverter().convert(source, "4.1.56").output

    legacy = Path(__file__).parent / "fixtures/spine38/golden_ingot.atlas"
    atlas40 = AtlasConverter().convert(legacy, "4.0.31", source_version="3.8.75")
    atlas41 = AtlasConverter().convert(atlas40, "4.1.56", source_version="4.0.31")
    assert parse_atlas(atlas41).region_records == parse_atlas(atlas40).region_records


def test_direct_40_to_41_real_bundle_reinspection(tmp_path):
    import shutil

    from fnx_spine_forge.inspection import InspectionService

    fixture = Path(__file__).parent / "fixtures/spine38"
    converter = SkeletonConverter()
    result_40 = converter.convert(
        (fixture / "golden_ingot.json").read_bytes(), "4.0.31",
        source_risk_policy=SourceRiskPolicy.ALLOW_WITH_DIAGNOSTIC,
    )
    assert result_40.output is not None
    result_41 = converter.convert(result_40.output, "4.1.56")
    assert result_41.output is not None, result_41.diagnostics
    atlas_40 = AtlasConverter().convert(
        (fixture / "golden_ingot.atlas").read_bytes(), "4.0.31", source_version="3.8.75"
    )
    atlas_41 = AtlasConverter().convert(atlas_40, "4.1.56", source_version="4.0.31")
    target = tmp_path / "bundle41"
    target.mkdir()
    (target / "golden_ingot.json").write_bytes(result_41.output)
    (target / "golden_ingot.atlas").write_bytes(atlas_41)
    shutil.copyfile(fixture / "golden_ingot.png", target / "golden_ingot.png")
    inspected = InspectionService().inspect(str(target))
    assert inspected.ok, inspected.diagnostics
    assert inspected.bundles[0].texture_pages == ("golden_ingot.png",)


def legacy_37_skeleton():
    return {
        "skeleton": {"spine": "3.7.94"},
        "bones": [{"name": "root", "transform": "noscale"}],
        "slots": [{"name": "slot", "bone": "root", "attachment": "wheel"}],
        "skins": {
            "default": {
                "slot": {
                    "wheel": {
                        "type": "region",
                        "path": "Wheel",
                        "width": 1,
                        "height": 1,
                    }
                }
            }
        },
        "animations": {
            "idle": {
                "bones": {
                    "root": {
                        "rotate": [
                            {
                                "time": 0,
                                "angle": 0,
                                "curve": 0.25,
                                "c2": 0.2,
                                "c3": 0.75,
                                "c4": 0.8,
                            },
                            {"time": 1, "angle": 90},
                        ]
                    }
                }
            }
        },
    }


def test_direct_37_to_38_converts_skin_map_and_preserves_legacy_curve():
    document = legacy_37_skeleton()
    source = json.dumps(document).encode()
    result = SkeletonConverter().convert(source, "3.8.99")
    assert result.status is ConversionStatus.STRUCTURALLY_VERIFIED, result.diagnostics
    assert result.output is not None
    target = json.loads(result.output)
    assert target["skeleton"]["spine"] == "3.8.99"
    assert target["skins"] == [
        {"name": "default", "attachments": document["skins"]["default"]}
    ]
    assert target["bones"][0]["transform"] == "NoScale"
    assert target["animations"] == document["animations"]
    assert result.statistics["bezier_segments"] == 1
    assert result.output == SkeletonConverter().convert(source, "3.8.99").output

    malformed = legacy_37_skeleton()
    malformed["animations"]["idle"]["future"] = []
    rejected = SkeletonConverter().convert(json.dumps(malformed).encode(), "3.8.99")
    assert rejected.status is ConversionStatus.REJECTED


def test_direct_37_to_38_atlas_and_bundle_reinspection(tmp_path):
    import shutil

    from fnx_spine_forge.inspection import InspectionService

    fixture = Path(__file__).parent / "fixtures/spine38"
    source = tmp_path / "source37"
    target = tmp_path / "target38"
    source.mkdir()
    target.mkdir()
    (source / "skeleton.json").write_text(json.dumps(legacy_37_skeleton()), encoding="utf-8")
    shutil.copyfile(fixture / "golden_ingot.atlas", source / "golden_ingot.atlas")
    shutil.copyfile(fixture / "golden_ingot.png", source / "golden_ingot.png")
    converted = SkeletonConverter().convert(source / "skeleton.json", "3.8.99")
    assert converted.output is not None, converted.diagnostics
    (target / "skeleton.json").write_bytes(converted.output)
    (target / "golden_ingot.atlas").write_bytes(
        AtlasConverter().convert(
            source / "golden_ingot.atlas", "3.8.99", source_version="3.7.94"
        )
    )
    shutil.copyfile(source / "golden_ingot.png", target / "golden_ingot.png")
    before = InspectionService().inspect(str(source))
    after = InspectionService().inspect(str(target))
    assert before.ok, before.diagnostics
    assert after.ok, after.diagnostics
    assert after.bundles[0].texture_pages == ("golden_ingot.png",)


def test_direct_42_to_43_real_bundle_reinspection_preserves_texture(tmp_path):
    import shutil

    from fnx_spine_forge.inspection import InspectionService

    fixture = Path(__file__).parent / "fixtures/spine38"
    source_38 = (fixture / "golden_ingot.json").read_bytes()
    converter = SkeletonConverter()
    result_42 = converter.convert(
        source_38, "4.2.43", source_risk_policy=SourceRiskPolicy.ALLOW_WITH_DIAGNOSTIC
    )
    assert result_42.output is not None
    result_43 = converter.convert(result_42.output, "4.3.13")
    assert result_43.output is not None, result_43.diagnostics
    atlas_42 = AtlasConverter().convert(
        (fixture / "golden_ingot.atlas").read_bytes(), "4.2.43", source_version="3.8.75"
    )
    atlas_43 = AtlasConverter().convert(atlas_42, "4.3.13", source_version="4.2.43")
    target = tmp_path / "bundle43"
    target.mkdir()
    (target / "golden_ingot.json").write_bytes(result_43.output)
    (target / "golden_ingot.atlas").write_bytes(atlas_43)
    shutil.copyfile(fixture / "golden_ingot.png", target / "golden_ingot.png")
    inspected = InspectionService().inspect(str(target))
    assert inspected.ok, inspected.diagnostics
    assert inspected.bundles[0].texture_pages == ("golden_ingot.png",)
    assert (target / "golden_ingot.png").read_bytes() == (fixture / "golden_ingot.png").read_bytes()


def test_runtime_smoke_refuses_a_nonmatching_runtime_version(tmp_path):
    import json

    from fnx_spine_forge.conversion.runtime import run_spine_42_runtime_smoke

    package = tmp_path / "spine-core"
    package.mkdir()
    (package / "package.json").write_text(
        json.dumps(
            {
                "name": "@esotericsoftware/spine-core",
                "version": "4.3.0",
                "main": "index.js",
            }
        ),
        encoding="utf-8",
    )
    result = run_spine_42_runtime_smoke("missing.json", "missing.atlas", package)
    assert result["status"] == "rejected_runtime_identity"


def test_exact_route_registry_does_not_expand_patch_policy():
    planner = ConversionPlanner({("3.8.75", "4.2.43")})
    assert planner.plan("3.8.75", "4.2.43").executable
    assert not planner.plan("3.8.76", "4.2.43").executable
    assert not planner.plan("3.8.75", "4.2.44").executable


def test_38_migration_fails_closed_for_unknown_timeline_and_invalid_curve():
    unknown = json.loads(skeleton("3.8.75"))
    unknown["animations"]["idle"]["bones"] = {"root": {"future": [{"time": 0}]}}
    assert (
        SkeletonConverter()
        .convert(
            json.dumps(unknown).encode(),
            "4.2.43",
            source_risk_policy=SourceRiskPolicy.ALLOW_WITH_DIAGNOSTIC,
        )
        .status
        is ConversionStatus.REJECTED
    )

    malformed = json.loads(skeleton("3.8.75"))
    frame = malformed["animations"]["idle"]["bones"]["root"]["rotate"][0]
    frame["curve"] = 1.4
    assert (
        SkeletonConverter()
        .convert(
            json.dumps(malformed).encode(),
            "4.2.43",
            source_risk_policy=SourceRiskPolicy.ALLOW_WITH_DIAGNOSTIC,
        )
        .status
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
        SkeletonConverter()
        .convert(
            json.dumps(linked).encode(),
            "4.2.43",
            source_risk_policy=SourceRiskPolicy.ALLOW_WITH_DIAGNOSTIC,
        )
        .status
        is ConversionStatus.REJECTED
    )

    invalid_constraint = json.loads(skeleton("3.8.75"))
    invalid_constraint["ik"] = [{"name": "bad", "bones": ["missing"], "target": "root"}]
    assert (
        SkeletonConverter()
        .convert(
            json.dumps(invalid_constraint).encode(),
            "4.2.43",
            source_risk_policy=SourceRiskPolicy.ALLOW_WITH_DIAGNOSTIC,
        )
        .status
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
        SkeletonConverter()
        .convert(
            json.dumps(source).encode(),
            "4.2.43",
            source_risk_policy=SourceRiskPolicy.ALLOW_WITH_DIAGNOSTIC,
        )
        .status
        is ConversionStatus.REJECTED
    )

    missing = {"skeleton": {"spine": "3.8.75"}, "bones": []}
    assert (
        SkeletonConverter()
        .convert(
            json.dumps(missing).encode(),
            "4.2.43",
            source_risk_policy=SourceRiskPolicy.ALLOW_WITH_DIAGNOSTIC,
        )
        .status
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
        SkeletonConverter()
        .convert(
            json.dumps(source).encode(),
            "4.2.43",
            source_risk_policy=SourceRiskPolicy.ALLOW_WITH_DIAGNOSTIC,
        )
        .status
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
    result = SkeletonConverter().convert(
        json.dumps(source).encode(),
        "4.2.43",
        source_risk_policy=SourceRiskPolicy.ALLOW_WITH_DIAGNOSTIC,
    )
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

    for target_version in ("3.5.51", "3.6.53", "3.7.94"):
        legacy_source = json.loads(json.dumps(source))
        for legacy_skin in legacy_source["skins"]:
            for field in ("ik", "transform", "path"):
                legacy_skin.pop(field, None)
        legacy_result = SkeletonConverter().convert(
            json.dumps(legacy_source).encode(), target_version,
            source_risk_policy=SourceRiskPolicy.ALLOW_WITH_DIAGNOSTIC,
        )
        assert legacy_result.status is ConversionStatus.STRUCTURALLY_VERIFIED, (
            legacy_result.diagnostics
        )
        assert legacy_result.output is not None
        legacy = json.loads(legacy_result.output)
        assert legacy["skeleton"]["spine"] == target_version
        assert isinstance(legacy["skins"], dict)
        assert legacy["skins"]["default"]["slot"]["linked"]["deform"] is False
        assert legacy["animations"]["move"]["bones"]["child"]["rotate"][0]["angle"] == 0
        assert legacy["animations"]["move"]["draworder"] == source["animations"]["move"][
            "draworder"
        ]
        assert legacy["animations"]["move"]["deform"] == source["animations"]["move"][
            "deform"
        ]


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
