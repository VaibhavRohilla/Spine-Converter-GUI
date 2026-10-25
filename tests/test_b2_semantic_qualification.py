from __future__ import annotations

import json
import math
from hashlib import sha256
from pathlib import Path

import pytest
from b2_semantics import evaluate, feature_fixture, restricted_fixture, semantic_view

from fnx_spine_forge.conversion import AssetSetConverter, SkeletonConverter
from fnx_spine_forge.conversion.models import ConversionStatus
from fnx_spine_forge.inspection import InspectionService

ROUTES = (
    ("3.5.51", "4.3.13"),
    ("3.6.53", "4.2.43"),
    ("3.7.94", "4.1.56"),
    ("4.3.13", "3.8.99"),
    ("4.2.43", "3.6.53"),
    ("4.1.56", "3.5.51"),
)
SPINE_38_TARGETS = ("3.5.51", "3.6.53", "3.7.94", "4.0.31", "4.1.56", "4.2.43", "4.3.13")


@pytest.mark.parametrize(("source_version", "target_version"), ROUTES)
def test_feature_fixture_composed_route_semantic_and_numerical_evidence(
    source_version: str, target_version: str
) -> None:
    """Synthetic version-shaped fixture; success requires normalized endpoint meaning."""
    fixture = (
        Path(__file__).parent
        / "fixtures"
        / "b2_semantic"
        / (f"spine_{source_version.replace('.', '_')}.json")
    )
    source_doc = json.loads(fixture.read_text())
    if target_version in {"3.8.99", "3.6.53", "3.5.51"} and source_version.startswith("4."):
        source_doc = restricted_fixture(source_version, target_version)
    source_bytes = json.dumps(source_doc, separators=(",", ":")).encode()
    before = source_bytes[:]
    result = SkeletonConverter().convert(source_bytes, target_version)
    assert result.output is not None, result.diagnostics
    assert result.status is ConversionStatus.STRUCTURALLY_VERIFIED
    assert result.route[0] == source_version and result.route[-1] == target_version
    assert len(result.details["hop_evidence"]) == len(result.route) - 1
    target_doc = json.loads(result.output)
    left, right = semantic_view(source_doc), semantic_view(target_doc)
    assert len(left["bones"]) == len(right["bones"])
    for a, b in zip(left["bones"], right["bones"], strict=True):
        assert a[:2] == b[:2]
        assert a[2:] == pytest.approx(b[2:], abs=2e-6)
    assert left["slots"] == right["slots"]
    assert left["skins"] == right["skins"]
    assert left["attachments"] == right["attachments"]
    assert left["color"] == right["color"]
    assert left["attachment_timeline"] == right["attachment_timeline"]
    assert len(left["events"]) == len(right["events"])
    for a, b in zip(left["events"], right["events"], strict=True):
        assert {**a, "time": 0} == {**b, "time": 0}
        assert a["time"] == pytest.approx(b["time"], abs=1e-7)
    assert left["event_definitions"] == right["event_definitions"]
    assert left["duration"] == right["duration"]
    assert left["draw_order"] == right["draw_order"]
    # Independent evaluation at setup, before/at/after keyframes, midpoint and end.
    times = (0.0, 0.25, math.nextafter(0.5, 0.0), 0.5, 0.75, math.nextafter(1.0, 0.0), 1.0, 1.01)
    deviations = []
    translation_deviations = []
    for time in times:
        a = evaluate(left["rotation"], time, ("angle",))
        b = evaluate(right["rotation"], time, ("angle",))
        deviations.append(abs(a[0] - b[0]))
        ta = evaluate(left["translation"], time, ("x", "y"))
        tb = evaluate(right["translation"], time, ("x", "y"))
        translation_deviations.extend(abs(x - y) for x, y in zip(ta, tb, strict=True))
    assert max(deviations) <= 2e-5  # float32 event/key times in 3.5->3.6 paths
    assert max(translation_deviations) <= 2e-6
    assert source_bytes == before


def test_fixture_schemas_are_version_shaped_and_nontrivial() -> None:
    legacy = feature_fixture("3.7.94")
    modern = feature_fixture("4.2.43")
    assert isinstance(legacy["skins"], dict)
    assert isinstance(modern["skins"], list)
    assert len(legacy["bones"]) == 2
    assert len(legacy["animations"]["motion"]["bones"]["root"]["rotate"]) == 2
    assert legacy["animations"]["motion"]["events"][0]["name"] == "impact"


def _attachment_records(
    document: dict[str, object],
) -> dict[tuple[str, str, str], tuple[object, ...]]:
    """Independent fixture reader for serialized attachment meaning."""
    raw_skins = document["skins"]
    records: dict[tuple[str, str, str], tuple[object, ...]] = {}
    if isinstance(raw_skins, list):
        skins = ((str(skin["name"]), skin["attachments"]) for skin in raw_skins)
    else:
        skins = ((str(name), skin) for name, skin in raw_skins.items())
    for skin_name, slots in skins:
        for slot_name, attachments in slots.items():
            for attachment_name, attachment in attachments.items():
                kind = attachment.get("type", "region")
                records[(skin_name, slot_name, attachment_name)] = (
                    kind,
                    attachment.get("path", attachment_name),
                    attachment.get("x", 0),
                    attachment.get("y", 0),
                    attachment.get("rotation", 0),
                    attachment.get("width", 0),
                    attachment.get("height", 0),
                    tuple(attachment.get("uvs", ())),
                    tuple(attachment.get("triangles", ())),
                    tuple(attachment.get("vertices", ())),
                    attachment.get("parent"),
                    attachment.get("skin", skin_name),
                    attachment.get("deform", attachment.get("inheritDeform")),
                    attachment.get("hull"),
                    attachment.get("vertexCount"),
                    tuple(attachment.get("lengths", ())),
                    attachment.get("end"),
                )
    return records


def test_independent_attachment_expected_records_and_corruption_detection() -> None:
    """Schema-derived expectations are authored independently of converter output."""
    doc = {
        "skeleton": {"spine": "3.8.75"},
        "bones": [{"name": "root"}],
        "slots": [{"name": "slot", "bone": "root"}],
        "skins": {
            "base": {
                "slot": {
                    "region": {
                        "path": "art",
                        "x": 2,
                        "y": -3,
                        "rotation": 15,
                        "width": 8,
                        "height": 6,
                    },
                    "mesh": {
                        "type": "mesh",
                        "uvs": [0, 0, 1, 0],
                        "triangles": [0, 1, 0],
                        "vertices": [1, 2, 3, 4],
                        "hull": 2,
                    },
                    "weighted": {
                        "type": "mesh",
                        "uvs": [0.25, 0.75],
                        "vertices": [1, 0, 1, 2, 3, 0.4, 1, 4, 5, 0.6],
                        "triangles": [],
                        "vertexCount": 1,
                    },
                    "clip": {"type": "clipping", "vertices": [0, 0, 4, 0, 4, 3], "end": "slot"},
                    "box": {"type": "boundingbox", "vertices": [-1, -2, 2, 3]},
                    "path": {"type": "path", "vertices": [0, 0, 2, 1], "lengths": [3.5]},
                    "point": {"type": "point", "x": 5, "y": 6, "rotation": 90},
                }
            },
            "linkedSkin": {
                "slot": {
                    "linked": {
                        "type": "linkedmesh",
                        "parent": "mesh",
                        "skin": "base",
                        "inheritDeform": True,
                    }
                }
            },
        },
        "animations": {},
    }
    expected = {
        ("base", "slot", "region"): (
            "region",
            "art",
            2,
            -3,
            15,
            8,
            6,
            (),
            (),
            (),
            None,
            "base",
            None,
            None,
            None,
            (),
            None,
        ),
        ("base", "slot", "mesh"): (
            "mesh",
            "mesh",
            0,
            0,
            0,
            0,
            0,
            (0, 0, 1, 0),
            (0, 1, 0),
            (1, 2, 3, 4),
            None,
            "base",
            None,
            2,
            None,
            (),
            None,
        ),
        ("base", "slot", "weighted"): (
            "mesh",
            "weighted",
            0,
            0,
            0,
            0,
            0,
            (0.25, 0.75),
            (),
            (1, 0, 1, 2, 3, 0.4, 1, 4, 5, 0.6),
            None,
            "base",
            None,
            None,
            1,
            (),
            None,
        ),
        ("base", "slot", "clip"): (
            "clipping",
            "clip",
            0,
            0,
            0,
            0,
            0,
            (),
            (),
            (0, 0, 4, 0, 4, 3),
            None,
            "base",
            None,
            None,
            None,
            (),
            "slot",
        ),
        ("base", "slot", "box"): (
            "boundingbox",
            "box",
            0,
            0,
            0,
            0,
            0,
            (),
            (),
            (-1, -2, 2, 3),
            None,
            "base",
            None,
            None,
            None,
            (),
            None,
        ),
        ("base", "slot", "path"): (
            "path",
            "path",
            0,
            0,
            0,
            0,
            0,
            (),
            (),
            (0, 0, 2, 1),
            None,
            "base",
            None,
            None,
            None,
            (3.5,),
            None,
        ),
        ("base", "slot", "point"): (
            "point",
            "point",
            5,
            6,
            90,
            0,
            0,
            (),
            (),
            (),
            None,
            "base",
            None,
            None,
            None,
            (),
            None,
        ),
        ("linkedSkin", "slot", "linked"): (
            "linkedmesh",
            "linked",
            0,
            0,
            0,
            0,
            0,
            (),
            (),
            (),
            "mesh",
            "base",
            True,
            None,
            None,
            (),
            None,
        ),
    }
    assert _attachment_records(doc) == expected
    for mutate in (
        lambda a: a["mesh"].update(vertices=[1, 2, 3, 5]),
        lambda a: a["mesh"].update(uvs=[0, 0, 0.9, 0]),
        lambda a: a["weighted"].update(vertices=[1, 0, 1, 2, 3, 0.3, 1, 4, 5, 0.7]),
        lambda a: a["linked"].update(parent="region"),
    ):
        corrupted = json.loads(json.dumps(doc))
        attachments = corrupted["skins"]["base"]["slot"]
        attachments.update({"linked": corrupted["skins"]["linkedSkin"]["slot"]["linked"]})
        mutate(attachments)
        assert _attachment_records(corrupted) != expected


@pytest.mark.parametrize("target_version", SPINE_38_TARGETS)
def test_38_99_feature_fixture_direct_route_semantic_evaluation(target_version: str) -> None:
    source = json.loads(
        (Path(__file__).parent / "fixtures" / "b2_semantic" / "spine_3_8_99.json").read_text()
    )
    result = SkeletonConverter().convert(json.dumps(source).encode(), target_version)
    assert result.output is not None, result.diagnostics
    assert len(result.route) == 2
    left, right = semantic_view(source), semantic_view(json.loads(result.output))
    assert left["bones"] == right["bones"]
    assert left["slots"] == right["slots"]
    assert left["attachments"] == right["attachments"]
    assert left["color"] == right["color"]
    assert left["attachment_timeline"] == right["attachment_timeline"]
    assert left["events"] == right["events"]
    assert left["event_definitions"] == right["event_definitions"]
    assert left["duration"] == right["duration"]
    assert left["draw_order"] == right["draw_order"]
    sample_times = (0.0, 0.17, 0.5, 0.83, 1.0)
    for time in sample_times:
        before = evaluate(left["rotation"], time, ("angle",))
        after = evaluate(right["rotation"], time, ("angle",))
        assert before == pytest.approx(after, abs=2e-5)


def test_unsupported_feature_stays_rejected_on_required_downgrade() -> None:
    source = json.loads(
        (Path(__file__).parent / "fixtures" / "b2_semantic" / "spine_4_3_13.json").read_text()
    )
    source["constraints"] = [
        {
            "type": "transform",
            "name": "rig",
            "order": 0,
            "bones": ["child"],
            "target": "root",
            "mixRotate": 0.5,
        }
    ]
    result = SkeletonConverter().convert(json.dumps(source).encode(), "3.8.99")
    assert result.status is ConversionStatus.REJECTED
    assert result.output is None
    assert result.details.get("failed_hop") is not None
    assert result.details["failed_hop"]["source_version"] == "4.3.13"
    assert result.details["failed_hop"]["target_version"] == "4.2.43"
    assert result.details["failed_hop"]["diagnostic_codes"] == ("UNSUPPORTED_TARGET_FEATURE",)
    assert "transform" in result.details["failed_hop"]["diagnostics"][0]


def test_independent_evaluator_handles_negative_delta_step_and_invalid_order() -> None:
    frames = ({"time": 0.0, "value": 12.0, "curve": "stepped"}, {"time": 1.0, "value": -8.0})
    assert evaluate(frames, 0.999, ("value",)) == (12.0,)
    assert evaluate(frames, 1.0, ("value",)) == (-8.0,)
    with pytest.raises(ValueError, match="strictly increasing"):
        evaluate(({"time": 0, "value": 1}, {"time": 0, "value": 2}), 0.0, ("value",))


@pytest.mark.parametrize(("source_version", "target_version"), ROUTES)
def test_composed_asset_set_returns_reinspected_bundle_and_preserves_source(
    tmp_path: Path, source_version: str, target_version: str
) -> None:
    fixture = (
        Path(__file__).parent
        / "fixtures"
        / "b2_semantic"
        / (f"spine_{source_version.replace('.', '_')}.json")
    )
    skeleton_bytes = fixture.read_bytes()
    (tmp_path / "asset.json").write_bytes(skeleton_bytes)
    texture = (Path(__file__).parent / "fixtures" / "spine38" / "golden_ingot.png").read_bytes()
    (tmp_path / "asset.png").write_bytes(texture)
    modern_atlas = source_version.startswith(("4.2.", "4.3."))
    geometry = (
        "  rotate: 0\n  bounds: 0, 0, 16, 12\n  offsets: 0, 0, 16, 12\n"
        if modern_atlas
        else "  rotate: false\n  xy: 0, 0\n  size: 16, 12\n  orig: 16, 12\n  offset: 0, 0\n"
    )
    (tmp_path / "asset.atlas").write_text(
        "asset.png\nsize: 1718,891\nformat: RGBA8888\nfilter: Linear,Linear\n"
        "repeat: none\nbadge\n" + geometry + "  index: -1\n"
    )
    before = {path.name: path.read_bytes() for path in tmp_path.iterdir()}
    converter = AssetSetConverter()
    result = converter.convert(tmp_path, "asset.json", target_version)
    assert result.status is ConversionStatus.STRUCTURALLY_VERIFIED, result.diagnostics
    assert result.outputs is not None
    assert result.route[0] == source_version and result.route[-1] == target_version
    assert result.outputs["asset.png"] == texture
    assert sha256(result.outputs["asset.png"]).digest() == sha256(texture).digest()
    assert result.details["textures_unchanged"] is True
    assert len(result.details["per_hop"]) == len(result.route) - 1
    assert {path.name: path.read_bytes() for path in tmp_path.iterdir()} == before
    repeated = converter.convert(tmp_path, "asset.json", target_version)
    assert repeated.outputs == result.outputs
    output_root = tmp_path / "returned"
    output_root.mkdir()
    for name, payload in result.outputs.items():
        (output_root / name).write_bytes(payload)
    inspected = InspectionService().inspect(str(output_root))
    assert inspected.ok, inspected.diagnostics
