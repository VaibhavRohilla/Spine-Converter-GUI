"""Production admission, evidence integrity, and immutable reporting regressions."""

from __future__ import annotations

import json
from copy import deepcopy
from hashlib import sha256
from importlib.resources import files
from pathlib import Path

import pytest

from fnx_spine_forge.conversion import (
    ConversionQualificationRegistry,
    QualificationService,
    SkeletonConverter,
    SourceFeature,
)
from fnx_spine_forge.conversion.curves import _color_channels
from fnx_spine_forge.conversion.document import require_number, require_records
from fnx_spine_forge.conversion.errors import MigrationError
from fnx_spine_forge.conversion.migrate_41_to_42 import migrate_41_to_42
from fnx_spine_forge.conversion.models import ConversionStatus
from fnx_spine_forge.conversion.qualification import load_qualification_records
from fnx_spine_forge.conversion.registry import bone_mode_field
from fnx_spine_forge.inspection import InspectionService
from fnx_spine_forge.json_types import decode_json_object, require_json_object

FIXTURES = Path(__file__).parent / "fixtures"


def evidence_document():
    return json.loads(
        files("fnx_spine_forge.conversion").joinpath("qualification_evidence.json").read_bytes()
    )


def hierarchy_document():
    source = json.loads((FIXTURES / "b2_semantic/spine_3_8_99.json").read_bytes())
    return {
        "skeleton": source["skeleton"],
        "bones": source["bones"],
        "slots": [],
        "skins": [],
        "animations": {},
    }


def test_packaged_evidence_matches_actual_fixture_bytes_and_qualified_inventory():
    records = load_qualification_records(json.dumps(evidence_document()).encode())
    assert len(records) == 9
    assert sum(bool(record.supported_features) for record in records) == 8
    for record in records:
        for fixture in record.fixtures:
            assert (
                sha256((Path(__file__).parent.parent / fixture.identity).read_bytes()).hexdigest()
                == fixture.sha256
            )
            assert fixture.provenance
        assert not record.runtime_verified and not record.visually_verified
        assert not record.supported_features & record.unverified_features
        assert not record.unsupported_features & record.unverified_features


@pytest.mark.parametrize(
    "mutation",
    [
        lambda d: d.update(schema_version=True),
        lambda d: d.update(extra="unrecognized"),
        lambda d: d["records"].append(deepcopy(d["records"][0])),
        lambda d: d["records"][0].update(extra="unrecognized"),
        lambda d: d["records"][0].update(path=["3.8.99", "4.9.99"]),
        lambda d: d["records"][0].update(supported_features=["future_construct"]),
        lambda d: d["records"][0].update(semantic_evidence=[]),
        lambda d: d["records"][0].update(structural_evidence=[]),
        lambda d: d["records"][0].update(numerical_evidence=[]),
        lambda d: d["records"][0].update(runtime_verified=True),
        lambda d: d["records"][0].update(visually_verified=True),
        lambda d: d["records"][0].update(semantic_evidence=[""]),
        lambda d: d["records"][0]["fixtures"][0].update(sha256="not-a-digest"),
        lambda d: d["records"][0]["fixtures"][0].update(extra="unrecognized"),
    ],
)
def test_malformed_or_inflated_qualification_evidence_fails_closed(mutation):
    document = evidence_document()
    # Select a semantic record, rather than relying on packaged record ordering.
    document["records"] = [r for r in document["records"] if r["supported_features"]]
    mutation(document)
    with pytest.raises(ValueError):
        load_qualification_records(json.dumps(document).encode())


def test_qualification_policy_comes_from_admitted_records_not_code_special_cases():
    service = QualificationService(ConversionQualificationRegistry(records=()))
    result = service.evaluate(
        "3.8.99", "4.2.43", ("3.8.99", "4.2.43"), frozenset({SourceFeature.HIERARCHY})
    )
    assert not result.qualified
    assert result.unqualified_features == (SourceFeature.HIERARCHY,)
    assert result.missing_evidence


@pytest.mark.parametrize("path", [(), ("3.8.99",), ("3.8.99", "4.2.43", "3.8.99")])
def test_incomplete_or_cyclic_qualification_paths_return_rejection(path):
    result = QualificationService().evaluate(
        "3.8.99", "4.2.43", path, frozenset({SourceFeature.HIERARCHY})
    )
    assert not result.qualified
    assert result.diagnostic_codes


@pytest.mark.parametrize(
    "payload",
    [
        b'{"bones":[],"bones":[{"name":"root"}]}',
        b'{"nested":{"x":1,"x":2}}',
        b'{"x":NaN}',
        b'{"x":Infinity}',
        b'{"x":' + b"[" * 2000 + b"0" + b"]" * 2000 + b"}",
    ],
)
def test_json_boundary_rejects_ambiguous_or_unrepresentable_input(payload):
    with pytest.raises(ValueError):
        decode_json_object(payload, "source")


def test_json_admission_detaches_nested_mutable_values_and_rejects_cycles():
    original = {"nested": [{"x": 3}]}
    admitted = require_json_object(original, "source")
    original["nested"][0]["x"] = 7
    assert admitted == {"nested": [{"x": 3}]}
    cycle = {}
    cycle["self"] = cycle
    with pytest.raises(ValueError, match="cycle|nesting"):
        require_json_object(cycle, "source")


@pytest.mark.parametrize(
    "version,key",
    [
        ("3.8.99", "transform"),
        ("4.0.31", "transform"),
        ("4.1.56", "transform"),
        ("4.2.43", "inherit"),
        ("4.3.13", "inherit"),
    ],
)
def test_exact_bone_mode_schema_is_shared_and_typed(version, key):
    assert bone_mode_field(version) == key
    document = hierarchy_document()
    document["skeleton"]["spine"] = version
    document["bones"][0][key] = "NoScale"
    semantic = SkeletonConverter().read(json.dumps(document).encode()).semantic
    assert semantic.bones[0].transform.mode.value == "noscale"


def test_authored_inheritance_cannot_slip_into_hierarchy_only_qualification():
    document = hierarchy_document()
    document["bones"][0]["transform"] = "noScale"
    result = SkeletonConverter().convert(json.dumps(document).encode(), "4.2.43")
    assert result.output is None
    assert result.status is ConversionStatus.REJECTED
    assert "bone_inheritance" in result.qualification.to_json()["unqualified_features"]


@pytest.mark.parametrize("value", [10**1000, float("inf"), True])
def test_numeric_boundaries_fail_with_actionable_errors_instead_of_overflow(value):
    with pytest.raises(MigrationError):
        require_number(value, "setup x")
    document = hierarchy_document()
    document["bones"][0]["x"] = value
    result = SkeletonConverter().convert(json.dumps(document).encode(), "4.2.43")
    assert result.status is ConversionStatus.REJECTED
    assert result.output is None


def test_shared_color_decoder_uses_typed_scratch_state_and_handles_empty_timelines():
    assert _color_channels([], ("color",), "empty color") == (0, 0.0)
    document = decode_json_object(
        '{"frames":[{"time":0,"color":"ffffffff","curve":0.2,"c2":0.3,'
        '"c3":0.7,"c4":0.8,"__color_components":"authored"},'
        '{"time":1,"color":"ff0000ff"}]}',
        "fixture",
    )
    frames = require_records(document["frames"], "color timeline")
    count, error = _color_channels(frames, ("color",), "color timeline")
    assert count == 4 and error <= 1e-12
    assert frames[0]["__color_components"] == "authored"
    assert "__color_components" not in frames[1]


def test_direct_writer_admission_uses_registered_route_kind():
    source = require_json_object(hierarchy_document(), "source")
    with pytest.raises(MigrationError, match="No registered"):
        migrate_41_to_42(source, "3.8.99", "4.2.43")


def test_inspection_report_serializes_typed_metadata_without_sharing_mutable_values():
    manifest = InspectionService().inspect(str(FIXTURES / "spine38"))
    first = manifest.to_dict()
    encoded = json.dumps(first, allow_nan=False)
    assert json.loads(encoded)["ok"] is True
    first["assets"].clear()
    assert manifest.to_dict()["assets"]


def test_skeleton_conversion_qualifies_the_same_single_source_snapshot(tmp_path, monkeypatch):
    path = tmp_path / "source.json"
    path.write_text(json.dumps(hierarchy_document()))
    original = Path.read_bytes
    reads = []

    def tracked_read(self):
        if self == path:
            reads.append(self)
            if len(reads) > 1:
                return b'{"changed":true}'
        return original(self)

    monkeypatch.setattr(Path, "read_bytes", tracked_read)
    result = SkeletonConverter().convert(path, "4.2.43")
    assert result.output is not None
    assert result.qualification.qualified
    assert len(reads) == 1
    assert json.loads(result.output)["bones"] == hierarchy_document()["bones"]


def test_typed_qualification_is_the_only_conversion_claim():
    from fnx_spine_forge.conversion import QualificationResult

    result = SkeletonConverter().convert(json.dumps(hierarchy_document()).encode(), "4.2.43")
    assert isinstance(result.qualification, QualificationResult)
    assert not hasattr(result, "semantic_qualification")
    assert not hasattr(result, "feature_compatibility")
    assert "qualification" not in result.details
    assert result.qualification.qualified


@pytest.mark.parametrize(
    "field,value",
    [
        ("length", 10),
        ("skin", True),
        ("skinRequired", False),
        ("icon", "bone"),
        ("color", "ffffffff"),
    ],
)
def test_unverified_bone_fields_are_not_lost_from_feature_inspection(field, value):
    source = hierarchy_document()
    source["bones"][0][field] = value
    result = SkeletonConverter().convert(json.dumps(source).encode(), "4.2.43")
    assert result.output is None
    assert SourceFeature.BONE_EXTENSIONS in result.qualification.unqualified_features


def test_unknown_skeleton_metadata_rejects_qualified_execution():
    source = hierarchy_document()
    source["skeleton"]["futureFeature"] = True
    result = SkeletonConverter().convert(json.dumps(source).encode(), "4.2.43")
    assert result.output is None
    assert SourceFeature.UNKNOWN in result.qualification.unqualified_features


def test_structural_evidence_does_not_qualify_unknown_features_at_any_level():
    from fnx_spine_forge.conversion import QualificationLevel

    result = QualificationService().evaluate(
        "3.8.75",
        "4.2.43",
        ("3.8.75", "4.2.43"),
        frozenset({SourceFeature.UNKNOWN}),
        required_level=QualificationLevel.STRUCTURAL,
    )
    assert result.available_level is QualificationLevel.STRUCTURAL
    assert not result.qualified
