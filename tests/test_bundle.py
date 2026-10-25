"""B3 integration tests use real B2 conversions and inspect returned artifacts."""

import json
from dataclasses import replace
from pathlib import Path
from zipfile import ZipFile

import pytest

from fnx_spine_forge.bundle import (
    BundleRequest,
    BundleService,
    BundleState,
    CancellationToken,
    DependencyMappings,
    PackageMode,
    RetentionPolicy,
    Stage,
    _rename_exclusive,
)
from fnx_spine_forge.cli import main
from fnx_spine_forge.conversion.models import SourceRiskPolicy
from fnx_spine_forge.inspection import InspectionService

FIXTURES = Path(__file__).parent / "fixtures"


def bundle(root, name="asset", version="3.8.99", directory=""):
    parent = root / directory
    parent.mkdir(parents=True, exist_ok=True)
    document = {
        "skeleton": {"spine": version},
        "bones": [{"name": "root"}],
        "slots": [],
        "skins": [],
        "animations": {},
    }
    (parent / f"{name}.json").write_text(json.dumps(document))
    (parent / f"{name}.atlas").write_text(
        f"{name}.png\nsize: 1,1\nformat: RGBA8888\nfilter: Linear,Linear\nrepeat: none\n"
        "image\n  rotate: false\n  xy: 0,0\n  size: 1,1\n  orig: 1,1\n  offset: 0,0\n  index: -1\n"
    )
    (parent / f"{name}.png").write_bytes((FIXTURES / "spine38/golden_ingot.png").read_bytes())
    return f"{directory + '/' if directory else ''}{name}.json"


def request(source, output, **kwargs):
    kwargs.setdefault("experimental_structural", True)
    return BundleRequest(source, "4.2.43", output, **kwargs)


def test_real_qualified_zip_folder_and_reproducibility(tmp_path):
    source = tmp_path / "source"
    bundle(source)
    before = {p.name: p.read_bytes() for p in source.iterdir()}
    service = BundleService()
    outputs = []
    for name in ("one.zip", "two.zip", "folder"):
        dest = tmp_path / name
        result = service.convert_bundle(request(source, dest))
        assert result.published, result.report
        assert not result.report["bundles"][0]["qualification"]["qualified"]
        assert result.report["runtime_verification"] == "not_run"
        assert InspectionService().inspect(str(dest)).ok
        outputs.append(dest)
    assert outputs[0].read_bytes() == outputs[1].read_bytes()
    with ZipFile(outputs[0]) as z:
        assert z.namelist() == ["asset.atlas", "asset.json", "asset.png"]
        assert z.read("asset.png") == before["asset.png"]
        assert json.loads(z.read("asset.json"))["skeleton"]["spine"] == "4.2.43"
    assert {p.name: p.read_bytes() for p in source.iterdir()} == before
    assert not service.convert_bundle(request(source, outputs[0])).published
    assert not service.convert_bundle(request(source, outputs[2])).published


def test_ambiguity_mapping_selection_and_missing_texture(tmp_path):
    source = tmp_path / "source"
    bundle(source, "one")
    bundle(source, "two")
    service = BundleService()
    inspected = service.inspect_source(source)
    assert inspected.states["one.json"] == BundleState.NEEDS_SELECTION
    mapping = DependencyMappings(atlases={"one.json": "two.atlas"})
    assert service.inspect_source(source, mapping).states["one.json"] == BundleState.READY
    req = request(source, tmp_path / "selected.zip", bundle_ids=("one.json",), mappings=mapping)
    assert service.convert_bundle(req).published
    with ZipFile(req.output) as z:
        assert z.namelist() == ["one.json", "two.atlas", "two.png"]
    (source / "two.png").rename(source / "replacement.png")
    assert service.inspect_source(source, mapping).states["one.json"] == BundleState.INCOMPLETE
    mapping = DependencyMappings(
        {"one.json": "two.atlas"}, {("two.atlas", "two.png"): "replacement.png"}
    )
    fixed = replace(req, output=tmp_path / "fixed.zip", mappings=mapping)
    result = service.convert_bundle(fixed)
    assert result.published, result.report
    with ZipFile(fixed.output) as z:
        assert z.read("two.png") == (source / "replacement.png").read_bytes()
    bad = DependencyMappings({"absent.json": "two.atlas"})
    assert not service.convert_bundle(replace(req, output=tmp_path / "bad", mappings=bad)).published


def test_nested_multiple_shared_and_source_parity(tmp_path):
    source = tmp_path / "source"
    one = bundle(source, "one", directory="α")
    two = bundle(source, "two", directory="β")
    # Empty-image skeletons need explicit choices in a multi-atlas source.
    mappings = DependencyMappings({one: "α/one.atlas", two: "β/two.atlas"})
    archive = tmp_path / "source.zip"
    with ZipFile(archive, "w") as z:
        for path in source.rglob("*"):
            if path.is_file():
                z.write(path, path.relative_to(source).as_posix())
    service = BundleService()
    assert (
        service.inspect_source(source, mappings).states
        == service.inspect_source(archive, mappings).states
    )
    req = request(archive, tmp_path / "out.zip", mappings=mappings)
    # Final package has ambiguous empty skeletons, so don't pretend that it is portable.
    assert service.convert_bundle(req).published
    selected = replace(req, bundle_ids=(one,), output=tmp_path / "single.zip")
    assert service.convert_bundle(selected).published
    shared = DependencyMappings({one: "α/one.atlas", two: "α/one.atlas"})
    assert service.convert_bundle(
        replace(req, mappings=shared, output=tmp_path / "shared.zip")
    ).published


def test_qualification_risk_and_real_experimental(tmp_path):
    service = BundleService()
    source = FIXTURES / "spine38"
    req = request(source, tmp_path / "real.zip", experimental_structural=True)
    assert not service.convert_bundle(req).published
    permitted = replace(req, source_risk_policy=SourceRiskPolicy.ALLOW_WITH_DIAGNOSTIC)
    result = service.convert_bundle(permitted)
    assert result.published, result.report
    assert result.report["bundles"][0]["source_version"] == "3.8.75"
    assert not result.report["bundles"][0]["qualification"]["qualified"]
    rejected = service.convert_bundle(
        replace(permitted, experimental_structural=False, output=tmp_path / "reject")
    )
    assert not rejected.published


@pytest.mark.parametrize("stage", list(Stage)[:9])
def test_cancellation_before_publication(tmp_path, stage):
    source = tmp_path / "source"
    bundle(source)
    token = CancellationToken()
    events = []

    def progress(event):
        events.append(event.stage)
        if event.stage == stage:
            token.cancel()

    dest = tmp_path / "output.zip"
    result = BundleService().convert_bundle(
        request(source, dest), progress=progress, cancellation=token
    )
    assert result.status == "cancelled", result.report
    assert events[-1] == Stage.CANCELLED
    assert not dest.exists()
    assert not list(tmp_path.glob(".output.zip.*"))


def test_plan_retention_audit_cli_and_explicit_selection(tmp_path, capsys):
    source = tmp_path / "source"
    bundle(source)
    (source / "notes.txt").write_bytes(b"keep me")
    service = BundleService()
    dest = tmp_path / "out.zip"
    req = request(source, dest)
    assert service.plan_conversion(req).status == "planned"
    assert not dest.exists()
    result = service.convert_bundle(
        replace(req, retention=RetentionPolicy.ALL, package_mode=PackageMode.AUDIT)
    )
    assert result.published
    with ZipFile(dest) as z:
        assert z.read("notes.txt") == b"keep me"
        assert json.loads(z.read("fnx-conversion-report.json"))["runtime_verification"] == "not_run"
    explicit = tuple(source.iterdir())
    assert service.convert_bundle(
        replace(req, source=explicit, output=tmp_path / "explicit")
    ).published
    assert main(["bundle", "inspect", str(source)]) == 0
    assert main(["bundle", "list", str(source)]) == 0
    assert (
        main(
            [
                "bundle",
                "plan",
                "--input",
                str(source),
                "--target",
                "4.2.43",
                "--experimental-structural",
            ]
        )
        == 0
    )
    assert (
        main(
            [
                "bundle",
                "convert",
                "--experimental-structural",
                "--input",
                str(source),
                "--target",
                "4.2.43",
                "--output",
                str(tmp_path / "cli.zip"),
            ]
        )
        == 0
    )
    capsys.readouterr()


def test_folder_publication_no_replace(tmp_path):
    source, target = tmp_path / "stage", tmp_path / "occupied"
    source.mkdir()
    target.mkdir()
    with pytest.raises(OSError):
        _rename_exclusive(source, target)
    assert source.is_dir() and target.is_dir()


def test_rollback_on_write_failure(tmp_path, monkeypatch):
    source = tmp_path / "source"
    bundle(source)

    def fail(*args, **kwargs):
        raise OSError("simulated disk error")

    monkeypatch.setattr("fnx_spine_forge.bundle.os.link", fail)
    dest = tmp_path / "failure.zip"
    result = BundleService().convert_bundle(request(source, dest))
    assert result.status == "failed" and not result.published and not dest.exists()
    assert not list(tmp_path.glob(".failure.zip.*"))


def test_sidecar_completion_callback_and_occupied_sidecar(tmp_path):
    source = tmp_path / "source"
    bundle(source)
    service = BundleService()

    def callback(event):
        if event.stage == Stage.COMPLETED:
            raise RuntimeError("UI has already gone away")

    req = request(source, tmp_path / "viewer.zip")
    result = service.convert_bundle(req, progress=callback)
    assert result.published and result.status == "completed"
    sidecar = tmp_path / "viewer-report.json"
    service.write_report(result, sidecar)
    assert json.loads(sidecar.read_bytes())["report"]["publication"] == "published"
    with pytest.raises(FileExistsError):
        service.write_report(result, sidecar)
    with ZipFile(req.output) as z:
        assert not any("report" in n for n in z.namelist())


def test_multi_page_texture_bytes_and_unsafe_input(tmp_path):
    source = tmp_path / "source"
    bundle(source)
    atlas = source / "asset.atlas"
    text = atlas.read_text()
    atlas.write_text(
        text + "\n" + text.replace("asset.png", "second.png").replace("\nimage\n", "\nother\n")
    )
    texture = source / "asset.png"
    (source / "second.png").write_bytes(texture.read_bytes())
    service = BundleService()
    req = request(source, tmp_path / "pages.zip")
    assert service.convert_bundle(req).published
    with ZipFile(req.output) as z:
        assert z.read("second.png") == texture.read_bytes()
        assert z.read("asset.png") == texture.read_bytes()
    (source / "second.png").write_bytes(b"corrupt PNG")
    damaged = replace(req, output=tmp_path / "corrupt.zip")
    assert not service.convert_bundle(damaged).published
    malicious = tmp_path / "malicious.zip"
    with ZipFile(malicious, "w") as z:
        z.writestr("../escape.json", b"{}")
    assert not service.convert_bundle(replace(req, source=malicious)).published
    assert not (tmp_path / "escape.json").exists()


def test_distinct_attachment_evidence_nested_multi_bundle_and_mixed_versions(tmp_path):
    source = tmp_path / "source"
    ids = []
    for folder, region, version in (("α", "red", "3.8.99"), ("β", "blue", "4.2.43")):
        name = bundle(source, "same", version=version, directory=folder)
        ids.append(name)
        path = source / name
        doc = json.loads(path.read_bytes())
        doc["slots"] = [{"name": "body", "bone": "root", "attachment": region}]
        doc["skins"] = [
            {"name": "default", "attachments": {"body": {region: {"width": 1, "height": 1}}}}
        ]
        path.write_text(json.dumps(doc))
        atlas = path.with_suffix(".atlas")
        atlas.write_text(atlas.read_text().replace("\nimage\n", f"\n{region}\n"))
    service = BundleService()
    inspection = service.inspect_source(source)
    assert set(inspection.states.values()) == {BundleState.READY}
    assert {a.spine_version for a in inspection.manifest.assets if a.spine_version} == {
        "3.8.99",
        "4.2.43",
    }
    output = tmp_path / "mixed.zip"
    result = service.convert_bundle(request(source, output))
    assert result.published, result.report
    assert len(result.report["bundles"]) == 2
    with ZipFile(output) as z:
        assert set(z.namelist()) == {
            "α/same.json",
            "α/same.atlas",
            "α/same.png",
            "β/same.json",
            "β/same.atlas",
            "β/same.png",
        }


def test_batch_reports_all_jobs_and_qualification_rejection(tmp_path):
    source = tmp_path / "source"
    bundle(source)
    service = BundleService()
    req = request(source, tmp_path / "experimental.zip")
    results = service.convert_batch(
        (
            replace(req, experimental_structural=False),
            replace(req, output=tmp_path / "allowed.zip"),
            replace(req, target="9.9.9", output=tmp_path / "unsupported.zip"),
        )
    )
    assert [r.status for r in results] == ["failed", "completed", "failed"]
    assert results[0].report["bundles"][0]["qualification"]["unqualified_features"] == (
        "atlas_geometry",
    )
    assert not req.output.exists()


def test_inspection_invalid_explicit_input_is_a_serializable_result(tmp_path):
    service = BundleService()
    result = service.inspect_source((tmp_path / "missing.json",))
    encoded = json.loads(json.dumps(result.to_dict()))
    assert encoded["source_state"] == "INVALID"
    assert encoded["diagnostics"][0]["code"] == "INPUT_ERROR"


def test_ui_target_and_risk_contract_serialization():
    document = json.loads(
        json.dumps(BundleService().inspect_source(FIXTURES / "spine38").to_dict())
    )
    assert document["source_state"] == "READY"
    assert document["required_decisions"] == [
        {"asset_id": "golden_ingot.json", "code": "SOURCE_EXPORT_RISK_AUTHORIZATION_REQUIRED"}
    ]
    target = document["targets"]["golden_ingot.json"]["4.2.43"]
    assert target["structural_route_available"]
    assert target["target_formats"] == ["json", "binary"]
    assert target["source_risk_authorization_required"] and not target["qualified"]
    assert document["binary_capabilities"][0]["semantically_qualified"] is False


@pytest.mark.parametrize("second_weight", [0.49999, 0.50001])
def test_exported_weight_sum_tolerance_endpoints_preserve_values(second_weight):
    from fnx_spine_forge.conversion.semantic import _decode_vertex_stream

    values = (2.0, 0.0, 0.0, 0.0, 0.5, 1.0, 0.0, 0.0, second_weight)
    decoded = _decode_vertex_stream(values, 1, 2, "boundary")
    assert decoded[0][0][3] == 0.5 and decoded[0][1][3] == second_weight


@pytest.mark.parametrize("second_weight", [0.499989, 0.500011])
def test_weight_sums_outside_tolerance_still_reject(second_weight):
    from fnx_spine_forge.conversion.semantic import _decode_vertex_stream

    with pytest.raises(ValueError, match="sum to one"):
        _decode_vertex_stream((2.0, 0.0, 0.0, 0.0, 0.5, 1.0, 0.0, 0.0, second_weight), 1, 2, "bad")


@pytest.mark.parametrize(
    "rotation,degrees", [("true", 90), ("false", 0), ("180", 180), ("270", 270)]
)
def test_real_modern_atlas_boolean_rotation_vocabulary(rotation, degrees):
    from fnx_spine_forge.conversion.atlas import AtlasConverter

    payload = (
        f"page.png\nsize: 64,64\nregion\n  bounds: 1,2,3,4\n"
        f"  offsets: 0,0,3,4\n  rotate: {rotation}\n"
    ).encode()
    converter = AtlasConverter(experimental_structural=True)
    converted = converter.convert(payload, "4.3.13", source_version="4.2.43")
    assert converter.read(converted).geometry("4.3.13")[0].rotation_degrees == degrees
    assert converter.read(payload).geometry("4.2.43") == converter.read(converted).geometry(
        "4.3.13"
    )
    if degrees in (0, 90):
        legacy = converter.convert(payload, "4.1.56", source_version="4.2.43")
        assert converter.read(legacy).geometry("4.1.56")[0].rotation_degrees == degrees


def test_modern_atlas_invalid_rotation_still_rejects():
    from fnx_spine_forge.conversion.atlas import AtlasConverter

    payload = (
        b"page.png\nsize: 64,64\nregion\n  bounds: 1,2,3,4\n  offsets: 0,0,3,4\n  rotate: 91\n"
    )
    with pytest.raises(ValueError):
        AtlasConverter(experimental_structural=True).convert(
            payload, "4.3.13", source_version="4.2.43"
        )


def test_inspection_exposes_b2_source_admission_errors(tmp_path):
    source = tmp_path / "source"
    bundle(source)
    path = source / "asset.json"
    document = json.loads(path.read_bytes())
    document["bones"][0]["scaleX"] = "invalid-number"
    path.write_text(json.dumps(document))
    inspected = BundleService().inspect_source(source)
    assert inspected.states["asset.json"] == BundleState.UNSUPPORTED
    assert any(d.code == "CONVERSION_SOURCE_UNSUPPORTED" for d in inspected.manifest.diagnostics)


def test_failed_dependency_reports_are_deterministic_and_use_original_source(tmp_path):
    source = tmp_path / "source"
    bundle(source)
    (source / "asset.png").unlink()
    service = BundleService()
    req = request(source, tmp_path / "missing.zip")
    first, second = service.convert_bundle(req), service.convert_bundle(req)
    assert first.status == "failed" and first.to_dict() == second.to_dict()
    assert first.report["inspection"]["source"] == str(source)
