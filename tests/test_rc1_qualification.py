"""Release policy regressions, independent of experimental migration coverage."""

import json
from pathlib import Path

import pytest

from fnx_spine_forge.cli import main
from fnx_spine_forge.conversion import (
    AssetSetConverter,
    AtlasConverter,
    ConversionPlanner,
    ConversionQualificationRegistry,
    QualificationLevel,
    QualificationService,
    SkeletonConverter,
    SourceFeature,
    SourceRiskPolicy,
)
from fnx_spine_forge.conversion.models import ConversionStatus
from fnx_spine_forge.conversion.qualification import inspect_features

FIXTURES = Path(__file__).parent / "fixtures"


def subset():
    doc = json.loads((FIXTURES / "b2_semantic/spine_3_8_99.json").read_bytes())
    return {
        "skeleton": doc["skeleton"],
        "bones": doc["bones"],
        "slots": [],
        "skins": [],
        "animations": {},
    }


@pytest.mark.parametrize(
    "target", ["3.5.51", "3.6.53", "3.7.94", "4.0.31", "4.1.56", "4.2.43", "4.3.13"]
)
def test_real_record_qualified_hierarchy_subset(target):
    source = json.dumps(subset()).encode()
    before = source[:]
    result = SkeletonConverter().convert(source, target)
    assert result.output is not None, result.diagnostics
    assert result.qualification.to_json()["qualified"] is True
    assert json.loads(result.output)["bones"] == subset()["bones"]
    assert not result.qualification.runtime_verified and not result.qualification.visually_verified
    assert result == SkeletonConverter().convert(source, target)
    assert source == before
    canonical = SkeletonConverter().read(source)
    plan = ConversionPlanner().plan(
        "3.8.99", target, source_features=inspect_features(canonical.semantic, canonical.document)
    )
    assert plan.executable and plan.qualification.to_json() == result.qualification.to_json()


@pytest.mark.parametrize(
    "extension",
    [
        {"future": {}},
        {"animations": {"motion": {"future": []}}},
        {"animations": {"motion": {"bones": {"root": {"scale": [{"x": 2, "y": 3}]}}}}},
        {"ik": [{"name": "rig", "bones": ["child"], "target": "root"}]},
    ],
)
def test_unknown_advanced_and_feature_combinations_reject(extension):
    doc = subset() | extension
    result = SkeletonConverter().convert(json.dumps(doc).encode(), "4.2.43")
    assert result.status is ConversionStatus.REJECTED
    assert result.output is None


def test_unqualified_composition_and_explicit_experiment():
    source = json.dumps(subset() | {"skeleton": {"spine": "3.5.51"}, "skins": {}}).encode()
    rejected = SkeletonConverter().convert(source, "4.3.13")
    experiment = SkeletonConverter(experimental_structural=True).convert(source, "4.3.13")
    assert rejected.output is None
    assert experiment.output is not None
    assert experiment.details["experimental_structural"] is True
    assert experiment.qualification.to_json()["qualified"] is False
    assert len(experiment.route) > 2


def test_evidence_levels_and_invalid_edges_fail_closed():
    service = QualificationService()
    for level in (QualificationLevel.RUNTIME, QualificationLevel.VISUAL):
        q = service.evaluate(
            "3.8.99", "4.2.43", ("3.8.99", "4.2.43"), frozenset({SourceFeature.HIERARCHY}), level
        )
        assert not q.qualified
        assert q.available_level is QualificationLevel.SEMANTIC
    assert not service.evaluate("3.5.51", "4.3.13", ("3.5.51", "4.3.13"), frozenset()).qualified
    assert not service.evaluate(
        "3.8.75", "4.2.43", ("3.8.75", "4.2.43"), frozenset({SourceFeature.HIERARCHY})
    ).qualified
    assert not ConversionPlanner().plan("3.8.99", "4.2.43").executable
    records = ConversionQualificationRegistry().records()
    assert records == ConversionQualificationRegistry().records()
    assert all(not record.runtime_verified and not record.visually_verified for record in records)


def test_cli_and_api_agree(tmp_path, capsys):
    path = tmp_path / "subset.json"
    path.write_text(json.dumps(subset()))
    api = SkeletonConverter().convert(path, "4.2.43")
    assert (
        main(["convert", "skeleton", "--input", str(path), "--target", "4.2.43", "--dry-run"]) == 0
    )
    cli = json.loads(capsys.readouterr().out)
    assert cli["qualification"] == json.loads(json.dumps(api.qualification.to_json()))
    path.write_text(json.dumps(subset() | {"future": []}))
    assert (
        main(["convert", "skeleton", "--input", str(path), "--target", "4.2.43", "--dry-run"]) == 2
    )
    assert json.loads(capsys.readouterr().out)["qualification"]["qualified"] is False


def test_authentic_bundle_and_risk_policy_remain_closed():
    source = FIXTURES / "spine38"
    before = {p.name: p.read_bytes() for p in source.iterdir() if p.is_file()}
    result = SkeletonConverter().convert(source / "golden_ingot.json", "4.2.43")
    assert result.diagnostic_codes == ("SOURCE_EXPORT_KNOWN_BUG",)
    result = AssetSetConverter().convert(
        source,
        "golden_ingot.json",
        "4.2.43",
        source_risk_policy=SourceRiskPolicy.ALLOW_WITH_DIAGNOSTIC,
    )
    assert result.outputs is None
    assert result.qualification.to_json()["qualified"] is False
    with pytest.raises(ValueError, match="QUALIFICATION_EVIDENCE_MISSING"):
        AtlasConverter().convert(source / "golden_ingot.atlas", "4.2.43", source_version="3.8.75")
    assert before == {p.name: p.read_bytes() for p in source.iterdir() if p.is_file()}


def test_executor_enforces_policy_before_calling_hops():
    from fnx_spine_forge.conversion import MigrationExecutor

    calls = []

    def direct(source, target):
        calls.append(target)
        return SkeletonConverter(experimental_structural=True).convert(source, target)

    executor = MigrationExecutor(ConversionPlanner(), direct)
    source = json.dumps(subset()).encode()
    assert executor.execute(source, "3.8.99", "4.2.43").output is not None
    assert calls == ["4.2.43"]
    calls.clear()
    source = json.dumps(subset() | {"skeleton": {"spine": "3.5.51"}, "skins": {}}).encode()
    assert executor.execute(source, "3.5.51", "4.3.13").output is None
    assert calls == []


def test_validated_animation_features_and_atlas_cli_consistency(capsys):
    source = (FIXTURES / "b2_semantic/spine_3_8_99.json").read_bytes()
    canonical = SkeletonConverter().read(source)
    features = inspect_features(canonical.semantic, canonical.document)
    assert {
        SourceFeature.ROTATION,
        SourceFeature.TRANSLATION,
        SourceFeature.BEZIER,
        SourceFeature.EVENTS,
        SourceFeature.SLOTS,
        SourceFeature.ATTACHMENTS,
    } <= features
    atlas = FIXTURES / "spine38/golden_ingot.atlas"
    assert (
        main(
            [
                "convert",
                "atlas",
                "--input",
                str(atlas),
                "--target",
                "4.2.43",
                "--source-version",
                "3.8.75",
                "--dry-run",
            ]
        )
        == 2
    )
    report = json.loads(capsys.readouterr().out)
    expected = AtlasConverter().qualification("3.8.75", "4.2.43").to_json()
    assert report["qualification"] == json.loads(json.dumps(expected))
    assert expected["available_level"] == "structural_only"
    assert not expected["qualified"]


def test_explicit_experiment_never_asserts_qualification_even_for_evidenced_subset():
    source = json.dumps(subset()).encode()
    result = SkeletonConverter(experimental_structural=True).convert(source, "4.2.43")
    assert result.output is not None
    assert result.details["experimental_structural"] is True
    assert result.qualification.to_json()["qualified"] is False
    assert result.qualification.to_json()["available_level"] == "semantic_qualified"
