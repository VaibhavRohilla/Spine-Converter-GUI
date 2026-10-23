from __future__ import annotations

import json
import os
import stat
import subprocess
import sys
import warnings
from pathlib import Path
from zipfile import ZipFile

import pytest

from fnx_spine_forge.config import InspectionConfig
from fnx_spine_forge.dependencies import DependencyResolver
from fnx_spine_forge.inspection import InspectionService
from fnx_spine_forge.models import Severity
from fnx_spine_forge.parsers import parse_atlas
from fnx_spine_forge.source import AssetSource, SourceLimits, UnsafeSourceError

SKELETON_38 = {
    "skeleton": {"spine": "3.8.75"},
    "bones": [{"name": "root"}],
    "slots": [{"name": "body", "bone": "root", "attachment": "hero"}],
    "skins": {"default": {"body": {"hero": {"name": "hero", "path": "hero"}}}},
    "animations": {"idle": {}},
}
SKELETON_42 = {
    "skeleton": {"spine": "4.2.43"},
    "bones": [{"name": "root"}],
    "slots": [],
    "skins": [{"name": "default", "attachments": {}}],
    "animations": {"idle": {}},
}
ATLAS = (
    b"page one.png\nsize: 64,64\n"
    b"filter: Linear,Linear\n\n"
    b"hero\n  bounds: 0,0,16,16\n"
    b"  custom: preserve\n\n"
    b"page two.png\nsize: 16,16\n"
    b"\nother region\n"
    b"  rotate: false\n"
)


def add_bundle(root: Path, name: str, skeleton: dict = SKELETON_38):
    root.mkdir(parents=True, exist_ok=True)
    (root / f"{name}.json").write_text(json.dumps(skeleton), encoding="utf-8")
    (root / f"{name}.atlas").write_bytes(ATLAS)
    (root / "page one.png").write_bytes(b"png placeholder")
    (root / "page two.png").write_bytes(b"png placeholder")


def test_zip_and_folder_logically_equivalent_and_deterministic(tmp_path):
    folder = tmp_path / "src"
    add_bundle(folder, "hero")
    zip_path = tmp_path / "asset.zip"
    with ZipFile(zip_path, "w") as z:
        for p in sorted(folder.iterdir()):
            z.write(p, p.name)
    service = InspectionService()
    folder_manifest = service.inspect(str(folder))
    zip_manifest = service.inspect(str(zip_path))
    assert [(a.path, a.kind, a.spine_version) for a in folder_manifest.assets] == [
        (a.path, a.kind, a.spine_version) for a in zip_manifest.assets
    ]
    assert folder_manifest.to_dict() == service.inspect(str(folder)).to_dict()

    def logical(manifest):
        payload = manifest.to_dict()
        payload["source"] = "<source>"
        for bundle in payload["bundles"]:
            bundle["source_location"] = "<source>"
        for asset in payload["assets"]:
            asset["source_id"] = "<source>"
        return payload

    assert logical(folder_manifest) == logical(zip_manifest)
    assert folder_manifest.ok


def test_multiple_bundles_and_real_version_variants(tmp_path):
    root = tmp_path / "multi"
    add_bundle(root / "one", "hero", SKELETON_38)
    add_bundle(root / "two", "creature", SKELETON_42)
    result = InspectionService().inspect(str(root))
    assert {b.versions[0] for b in result.bundles} == {"3.8.75", "4.2.43"}
    assert len(result.bundles) == 2


def test_missing_page_and_region_and_nonimage_attachment(tmp_path):
    root = tmp_path / "src"
    add_bundle(root, "hero")
    (root / "page two.png").unlink()
    obj = json.loads((root / "hero.json").read_text())
    obj["skins"]["default"]["body"]["hero"]["path"] = "absent-region"
    obj["skins"]["default"]["body"]["bounds"] = {
        "name": "bounds",
        "type": "boundingbox",
        "path": "not-a-region",
    }
    (root / "hero.json").write_text(json.dumps(obj))
    codes = {d.code for d in InspectionService().inspect(str(root)).diagnostics}
    assert "MISSING_TEXTURE" in codes and "ATLAS_REGION_MISSING" in codes
    assert "not-a-region" not in str(InspectionService().inspect(str(root)).diagnostics)


def test_ambiguous_basename_is_not_selected_arbitrarily(tmp_path):
    root = tmp_path / "tree"
    (root / "atlas").mkdir(parents=True)
    (root / "a").mkdir()
    (root / "b").mkdir()
    (root / "atlas/x.atlas").write_bytes(b"page.png\nsize: 1,1\n")
    (root / "a/page.png").write_bytes(b"a")
    (root / "b/page.png").write_bytes(b"b")
    result = InspectionService().inspect(str(root))
    dep = next(d for d in result.dependencies if d.kind == "texture_page")
    assert (
        dep.resolved is None
        and dep.status == "ambiguous"
        and "AMBIGUOUS_TEXTURE" in {d.code for d in result.diagnostics}
    )


def test_invalid_json_missing_and_future_versions_are_diagnostic(tmp_path):
    root = tmp_path / "src"
    root.mkdir()
    (root / "broken.json").write_text("{")
    (root / "missing.json").write_text(
        json.dumps({"skeleton": {}, "bones": [{"name": "root"}], "slots": []})
    )
    (root / "future.json").write_text(
        json.dumps({"skeleton": {"spine": "9.0.1"}, "bones": [{"name": "root"}], "slots": []})
    )
    result = InspectionService().inspect(str(root))
    codes = {d.code for d in result.diagnostics}
    assert {"MALFORMED_JSON", "SKELETON_VERSION_MISSING", "UNSUPPORTED_VERSION"} <= codes


def test_atlas_duplicate_regions_and_unknown_attributes():
    atlas = parse_atlas(
        b"page.png\nsize: 2,2\n\nregion\n  xy: 0,0\n  mystery: kept\n\nregion\n  rotate: true\n"
    )
    assert atlas.duplicate_regions == ("region",)
    assert ("mystery", "kept") in atlas.unknown_attributes


def test_zip_traversal_duplicates_and_symlink(tmp_path):
    for entry, expected in [("../bad.txt", "Unsafe path"), ("a/../bad.txt", "Unsafe path")]:
        path = tmp_path / (str(len(list(tmp_path.iterdir()))) + ".zip")
        with ZipFile(path, "w") as z:
            z.writestr(entry, "x")
        with pytest.raises(UnsafeSourceError, match=expected):
            with AssetSource(path):
                pass
    dup = tmp_path / "dup.zip"
    with ZipFile(dup, "w") as z:
        z.writestr("A/one.txt", "1")
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            z.writestr("a/ONE.txt", "2")
    with pytest.raises(UnsafeSourceError, match="collision"):
        with AssetSource(dup):
            pass
    link = tmp_path / "link.zip"
    with ZipFile(link, "w") as z:
        i = __import__("zipfile").ZipInfo("escape")
        i.create_system = 3
        i.external_attr = (stat.S_IFLNK | 0o777) << 16
        z.writestr(i, "../../outside")
    with pytest.raises(UnsafeSourceError, match="symlink"):
        with AssetSource(link):
            pass


def test_zip_limits_and_compression_ratio(tmp_path):
    path = tmp_path / "big.zip"
    with ZipFile(path, "w", compression=8) as z:
        z.writestr("large", "A" * 10000)
    limits = SourceLimits(
        max_member_uncompressed=20000,
        max_member_compressed=20000,
        max_total_uncompressed=20000,
        max_total_compressed=20000,
        max_compression_ratio=2,
    )
    with pytest.raises(UnsafeSourceError, match="ratio"):
        with AssetSource(path, limits):
            pass
    limits = SourceLimits(max_members=0)
    with pytest.raises(UnsafeSourceError, match="Too many"):
        with AssetSource(path, limits):
            pass


def test_folder_symlink_rejected_without_following_outside(tmp_path):
    root = tmp_path / "root"
    root.mkdir()
    outside = tmp_path / "outside"
    outside.write_text("secret")
    try:
        (root / "link").symlink_to(outside)
    except OSError:
        pytest.skip("symlink creation unavailable")
    with pytest.raises(UnsafeSourceError, match="symlink"):
        with AssetSource(root):
            pass


def test_source_read_limit_and_no_mutation(tmp_path):
    root = tmp_path / "folder"
    add_bundle(root, "x")
    before = {p.name: p.read_bytes() for p in root.iterdir()}
    with AssetSource(root, SourceLimits(max_read_bytes=5)) as src:
        with pytest.raises(UnsafeSourceError, match="Read exceeds"):
            src.read("x.json")
    InspectionService().inspect(str(root))
    assert before == {p.name: p.read_bytes() for p in root.iterdir()}


def test_cli_exit_codes(tmp_path):
    root = tmp_path / "bad"
    root.mkdir()
    (root / "x.json").write_text("{")
    env = {**os.environ, "PYTHONPATH": "src"}
    good = subprocess.run(
        [sys.executable, "-m", "fnx_spine_forge", "inspect", str(root), "--json"],
        env=env,
        capture_output=True,
        text=True,
    )
    strict = subprocess.run(
        [sys.executable, "-m", "fnx_spine_forge", "inspect", str(root), "--strict"],
        env=env,
        capture_output=True,
        text=True,
    )
    assert good.returncode == 0 and json.loads(good.stdout)["schema_version"] == 1
    assert strict.returncode == 2


def test_zip_uncompressed_and_compressed_size_limits(tmp_path):
    path = tmp_path / "size.zip"
    with ZipFile(path, "w", compression=0) as archive:
        archive.writestr("a.bin", b"1234567890")
    too_large_member = SourceLimits(max_member_uncompressed=5)
    with pytest.raises(UnsafeSourceError, match="uncompressed size"):
        with AssetSource(path, too_large_member):
            pass
    too_large_compressed = SourceLimits(max_member_compressed=5)
    with pytest.raises(UnsafeSourceError, match="compressed size"):
        with AssetSource(path, too_large_compressed):
            pass
    too_large_total = SourceLimits(max_total_uncompressed=5)
    with pytest.raises(UnsafeSourceError, match="total uncompressed"):
        with AssetSource(path, too_large_total):
            pass
    too_large_total_compressed = SourceLimits(max_total_compressed=5)
    with pytest.raises(UnsafeSourceError, match="total compressed"):
        with AssetSource(path, too_large_total_compressed):
            pass


def test_corrupt_zip_is_rejected(tmp_path):
    path = tmp_path / "corrupt.zip"
    path.write_bytes(b"not a ZIP archive")
    result = InspectionService().inspect(str(path))
    assert result.diagnostics[0].severity is Severity.BLOCKER
    assert result.diagnostics[0].code == "INPUT_ERROR"


def test_nested_manifest_data_is_immutable(tmp_path):
    root = tmp_path / "src"
    add_bundle(root, "immutable")
    result = InspectionService().inspect(str(root))
    asset = next(item for item in result.assets if item.kind == "skeleton_json")
    with pytest.raises(TypeError):
        asset.metadata["new"] = "value"
    diagnostic = result.diagnostics
    assert isinstance(diagnostic, tuple)
    assert json.loads(json.dumps(result.to_dict()))["ok"] is True


def test_installed_cli_inspects_zip_and_folder(tmp_path):
    folder = tmp_path / "cli-assets"
    add_bundle(folder, "cli")
    archive = tmp_path / "cli.zip"
    with ZipFile(archive, "w") as zipped:
        for item in sorted(folder.iterdir()):
            zipped.write(item, item.name)
    executable = Path(__file__).resolve().parents[1] / ".venv" / "bin" / "spine-forge"
    if not executable.exists():
        pytest.skip("Installed console script is not available in this environment")
    for source in (folder, archive):
        run = subprocess.run(
            [str(executable), "inspect", str(source), "--json"],
            capture_output=True,
            check=False,
            text=True,
        )
        assert run.returncode == 0, run.stderr
        assert json.loads(run.stdout)["summary"]["skeletons"] == 1


def test_matching_attachment_regions_allow_exact_export_pair_disambiguation(tmp_path):
    root = tmp_path / "assets"
    root.mkdir()
    (root / "hero.json").write_text(json.dumps(SKELETON_38), encoding="utf-8")
    for name in ("hero", "alternate"):
        (root / f"{name}.atlas").write_bytes(b"page.png\nsize: 1,1\n\nhero\n  xy: 0,0\n")
    (root / "page.png").write_bytes(b"texture")
    result = InspectionService().inspect(str(root))
    assert not any(item.code == "AMBIGUOUS_ATLAS" for item in result.diagnostics)
    assert any(
        item.owner == "hero.json" and item.resolved == "hero.atlas" for item in result.dependencies
    )


def test_malformed_skeleton_version_is_reported(tmp_path):
    root = tmp_path / "assets"
    root.mkdir()
    malformed = {**SKELETON_38, "skeleton": {"spine": "4.latest"}}
    (root / "broken-version.json").write_text(json.dumps(malformed), encoding="utf-8")
    result = InspectionService().inspect(str(root))
    assert "SKELETON_VERSION_MALFORMED" in {item.code for item in result.diagnostics}


def test_dependency_paths_cannot_escape_manifest_root():
    resolver = DependencyResolver(["inside/page.png", "outside.png"])
    escaped = resolver.resolve("../../outside.png", "inside/sprite.atlas")
    assert escaped.resolved is None
    safely_relative = resolver.resolve("page.png", "inside/sprite.atlas")
    assert safely_relative.resolved == "inside/page.png"


def test_unreadable_asset_does_not_hide_other_discoverable_files(tmp_path, monkeypatch):
    root = tmp_path / "assets"
    add_bundle(root, "good")
    (root / "bad.json").write_text("{}", encoding="utf-8")
    original_read = AssetSource.read

    def read_with_one_failure(self, name, max_bytes=None):
        if name == "bad.json":
            raise OSError("simulated read failure")
        return original_read(self, name, max_bytes)

    monkeypatch.setattr(AssetSource, "read", read_with_one_failure)
    result = InspectionService().inspect(str(root))
    assert any(asset.path == "good.json" for asset in result.assets)
    assert any(
        item.code == "ASSET_UNREADABLE" and item.path == "bad.json" for item in result.diagnostics
    )


def test_configurable_folder_and_json_limits(tmp_path):
    root = tmp_path / "limited-folder"
    add_bundle(root, "limited")
    folder_limit = SourceLimits(max_members=1)
    result = InspectionService(config=InspectionConfig(source_limits=folder_limit)).inspect(
        str(root)
    )
    assert result.diagnostics[0].severity is Severity.BLOCKER
    json_limited = InspectionService(config=InspectionConfig(max_skeleton_json_bytes=1)).inspect(
        str(root)
    )
    assert "JSON_TOO_LARGE" in {item.code for item in json_limited.diagnostics}
