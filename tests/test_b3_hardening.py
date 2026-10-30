"""Behavioral regressions for B3's typed-owner and validation cutover."""

from __future__ import annotations

import json
import struct
from dataclasses import FrozenInstanceError, replace
from pathlib import Path
from threading import Thread
from zipfile import ZipFile
from zlib import compress, crc32

import pytest

from fnx_spine_forge.atomic_io import stage_files, write_bytes_exclusive
from fnx_spine_forge.binary import BinaryErrorCode, BinaryLimits
from fnx_spine_forge.bundle import BundleService
from fnx_spine_forge.bundle_models import (
    BundleOutcome,
    BundleRequest,
    JobStatus,
    PackageContainer,
    SkeletonFormat,
    VerificationState,
)
from fnx_spine_forge.config import InspectionConfig
from fnx_spine_forge.detection import VersionDiagnosticCode, recognize_skeleton
from fnx_spine_forge.packaging import PackageSettings
from fnx_spine_forge.progress import CancellationToken
from fnx_spine_forge.source import AssetSource, SourceLimits, UnsafeSourceError
from fnx_spine_forge.texture import TextureLimits, validate_png

FIXTURES = Path(__file__).parent / "fixtures"


def setup_source(root: Path) -> Path:
    """Synthetic setup skeleton with real, unchanged atlas/texture resources."""
    root.mkdir()
    (root / "setup.json").write_text(
        json.dumps(
            {
                "skeleton": {"spine": "3.8.99"},
                "bones": [{"name": "root"}],
                "slots": [],
                "skins": [],
                "animations": {},
            }
        )
    )
    for name in ("golden_ingot.atlas", "golden_ingot.png"):
        (root / name).write_bytes((FIXTURES / "spine38" / name).read_bytes())
    return root


def chunk(kind: bytes, content: bytes) -> bytes:
    return (
        len(content).to_bytes(4, "big")
        + kind
        + content
        + (crc32(content, crc32(kind)) & 0xFFFFFFFF).to_bytes(4, "big")
    )


def png(width: int, height: int, rows: bytes, interlace: int = 0) -> bytes:
    header = struct.pack(">IIBBBBB", width, height, 8, 6, 0, 0, interlace)
    return (
        b"\x89PNG\r\n\x1a\n"
        + chunk(b"IHDR", header)
        + chunk(b"IDAT", compress(rows))
        + chunk(b"IEND", b"")
    )


def test_explicit_selection_ignores_unselected_limits_and_symlinks(tmp_path: Path) -> None:
    (tmp_path / "a").write_bytes(b"a")
    (tmp_path / "b").write_bytes(b"b")
    (tmp_path / "unselected-large").write_bytes(b"oversized")
    (tmp_path / "unselected-link").symlink_to(tmp_path / "unselected-large")
    limits = SourceLimits(max_members=2, max_member_uncompressed=2)
    with AssetSource((tmp_path / "b", tmp_path / "a"), limits) as source:
        assert source.names() == ["a", "b"]
        assert source.read("a") == b"a"
    with pytest.raises(UnsafeSourceError):
        with AssetSource(tmp_path, limits):
            pass


def test_selected_symlink_ancestor_rejected(tmp_path: Path) -> None:
    folder = tmp_path / "actual"
    folder.mkdir()
    (folder / "a").write_bytes(b"a")
    (tmp_path / "link").symlink_to(folder, target_is_directory=True)
    with pytest.raises(UnsafeSourceError, match="symlink"):
        with AssetSource((tmp_path / "link/a",)):
            pass


def test_prefix_collisions_reject_before_any_staging_writes(tmp_path: Path) -> None:
    with pytest.raises(UnsafeSourceError, match="conflict"):
        stage_files(tmp_path, {"a": b"file", "A/child": b"other"})
    assert list(tmp_path.iterdir()) == []
    archive = tmp_path / "collision.zip"
    with ZipFile(archive, "w") as writer:
        writer.writestr("a", b"file")
        writer.writestr("a/child", b"other")
    with pytest.raises(UnsafeSourceError, match="conflict"):
        with AssetSource(archive):
            pass


def test_explicit_bundle_selection_respects_only_selected_files(tmp_path: Path) -> None:
    source = setup_source(tmp_path / "source")
    selected = tuple(source.iterdir())
    (source / "unrelated").write_bytes(b"unrelated")
    service = BundleService(InspectionConfig(source_limits=SourceLimits(max_members=3)))
    request = BundleRequest(
        selected, "4.2.43", tmp_path / "selected.zip", experimental_structural=True
    )
    result = service.convert_bundle(request)
    assert result.status == JobStatus.COMPLETED, result.report
    assert result.report.input_checksums
    assert len(result.report.input_checksums) == 3
    assert not service.inspect_source(source).manifest.ok


def test_typed_reports_and_snapshots_are_immutable(tmp_path: Path) -> None:
    source = setup_source(tmp_path / "source")
    service = BundleService()
    result = service.plan_conversion(
        BundleRequest(source, "4.2.43", tmp_path / "out.zip", experimental_structural=True)
    )
    assert result.status == JobStatus.PLANNED
    with pytest.raises(FrozenInstanceError):
        result.report.output = "mutated"
    details = {"owner": {"value": 1}}
    outcome = BundleOutcome("asset", details=details)
    details["owner"]["value"] = 2
    assert outcome.to_dict()["details"] == {"owner": {"value": 1}}
    assert result.to_dict()["report"]["schema_version"] == 2
    inspected = service.inspect_source(source)
    target = inspected.targets["setup.json"]["4.2.43"]
    assert not target.qualification.qualified
    assert target.target_formats == (SkeletonFormat.JSON, SkeletonFormat.BINARY)


def test_no_guessed_container_or_source_version(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match=".zip"):
        BundleRequest(tmp_path, "4.2.43", tmp_path / "folder")
    request = BundleRequest(
        tmp_path, "4.2.43", tmp_path / "folder.zip", container=PackageContainer.FOLDER
    )
    assert request.container == PackageContainer.FOLDER
    missing = recognize_skeleton({"skeleton": {"version": "3.8.99"}, "bones": []})
    assert missing is not None and missing.version is None
    assert (
        missing.diagnostic is not None and missing.diagnostic.code == VersionDiagnosticCode.MISSING
    )
    numeric = recognize_skeleton({"skeleton": {"spine": 3.8}, "bones": []})
    assert numeric is not None and numeric.version is None
    assert (
        numeric.diagnostic is not None
        and numeric.diagnostic.code == VersionDiagnosticCode.MALFORMED
    )


def test_png_scanline_and_adam7_validation() -> None:
    assert validate_png(png(1, 1, b"\0" * 5)).width == 1
    # Independently specified 3x3 RGBA Adam7 pass row sizes, no decoder-derived expected value.
    interlaced = b"".join(b"\0" * (size + 1) for size in (4, 4, 8, 4, 4, 12))
    assert validate_png(png(3, 3, interlaced, 1)).interlaced
    for rows in (b"\5" + bytes(4), bytes(4), bytes(6), b"x" * 10000):
        with pytest.raises(ValueError):
            validate_png(png(1, 1, rows))
    with pytest.raises(ValueError, match="decoded"):
        validate_png(png(1, 1, bytes(5)), TextureLimits(max_decoded_bytes=4))
    with pytest.raises(ValueError, match="chunk count"):
        validate_png(png(1, 1, bytes(5)), TextureLimits(max_chunks=2))


def test_crc_correct_invalid_deflate_rejected() -> None:
    header = struct.pack(">IIBBBBB", 1, 1, 8, 6, 0, 0, 0)
    data = (
        b"\x89PNG\r\n\x1a\n"
        + chunk(b"IHDR", header)
        + chunk(b"IDAT", b"invalid zlib")
        + chunk(b"IEND", b"")
    )
    with pytest.raises(ValueError, match="compressed"):
        validate_png(data)


def test_binary_job_reports_encoder_failure_not_success(tmp_path: Path) -> None:
    source = setup_source(tmp_path / "source")
    request = BundleRequest(
        source,
        "4.2.43",
        tmp_path / "binary.zip",
        experimental_structural=True,
        skeleton_format=SkeletonFormat.BINARY,
    )
    result = BundleService(
        InspectionConfig(binary_limits=BinaryLimits(max_bytes=40))
    ).convert_bundle(request)
    assert not result.published
    assert (
        result.report.diagnostic is not None
        and result.report.diagnostic.code == BinaryErrorCode.SIZE_LIMIT
    )
    row = result.report.bundles[0]
    assert row.execution_success is False
    assert (
        row.binary_encode is not None and row.binary_encode.verification == VerificationState.FAILED
    )
    assert not request.output.exists()


def test_standalone_publication_never_overwrites_source(tmp_path: Path) -> None:
    path = tmp_path / "asset.json"
    path.write_bytes(b"original")
    with pytest.raises(FileExistsError):
        write_bytes_exclusive(path, b"replacement")
    assert path.read_bytes() == b"original"
    assert not list(tmp_path.glob(".asset.json.*"))


def test_cancellation_token_is_thread_safe() -> None:
    token = CancellationToken()
    thread = Thread(target=token.cancel)
    thread.start()
    thread.join()
    assert token.cancelled


def test_package_settings_and_measured_page_dimensions(tmp_path: Path) -> None:
    source = setup_source(tmp_path / "source")
    atlas = source / "golden_ingot.atlas"
    atlas.write_bytes(atlas.read_bytes().replace(b"size: 1718,891", b"size: 1,1"))
    result = BundleService(package_settings=PackageSettings(compression_level=0)).convert_bundle(
        BundleRequest(source, "4.2.43", tmp_path / "bad.zip", experimental_structural=True)
    )
    assert not result.published and result.report.diagnostic is not None
    assert "disagree" in result.report.diagnostic.message
    with pytest.raises(ValueError):
        PackageSettings(compression_level=10)


def test_codec_cannot_forge_version_or_qualification() -> None:
    from fnx_spine_forge.binary import BinaryCodecRegistry, BinaryError, BinarySkeletonCodec

    capability = BinaryCodecRegistry().capabilities()[0]
    for forged in (
        replace(capability, version="4.3.13"),
        replace(capability, semantically_qualified=True),
        replace(capability, runtime_qualified=True),
        replace(capability, fixture_evidence=()),
    ):
        with pytest.raises(BinaryError) as error:
            BinarySkeletonCodec(forged, experimental=True)
        assert error.value.code == BinaryErrorCode.CAPABILITY_INVALID


def test_duplicate_selection_is_not_silently_collapsed(tmp_path: Path) -> None:
    path = tmp_path / "asset"
    path.write_bytes(b"bytes")
    with pytest.raises(UnsafeSourceError, match="collision"):
        with AssetSource((path, path)):
            pass


def test_unicode_references_use_the_same_canonical_resolver() -> None:
    from fnx_spine_forge.dependencies import DependencyResolver, resolve_relative_path

    resolver = DependencyResolver(["textures/téxture.png"])
    assert (
        resolver.resolve("../textures/te\u0301xture.png", "atlas/a.atlas").resolved
        == "textures/téxture.png"
    )
    assert (
        resolve_relative_path("../textures/te\u0301xture.png", "atlas/a.atlas")
        == "textures/téxture.png"
    )
    assert resolve_relative_path("../../escape.png", "atlas/a.atlas") is None


def test_atlas_ownership_is_parsed_once_including_png_region_names() -> None:
    from fnx_spine_forge.conversion.atlas import AtlasConverter
    from fnx_spine_forge.parsers import parse_atlas

    payload = (
        b"page.png\nsize: 64,64\nregion.png\n  bounds: 0,0,1,1\n"
        b"  offsets: 0,0,1,1\n  index: 0\n\nsecond.png\nsize: 64,64\n"
        b"other\n  bounds: 0,0,1,1\n  offsets: 0,0,1,1\n"
    )
    parsed = parse_atlas(payload)
    assert parsed.pages == ("page.png", "second.png")
    assert parsed.regions == ("region.png", "other")
    assert parsed.region_pages == (0, 1)
    assert AtlasConverter().read(payload).region_pages == parsed.region_pages


@pytest.mark.parametrize(
    "indices,conflicting", [(("0", "1"), False), (("0", "0"), True), (("-1", "1"), True)]
)
def test_conflicting_region_indices_fail_closed(
    indices: tuple[str, str], conflicting: bool
) -> None:
    from fnx_spine_forge.parsers import parse_atlas

    payload = (
        "page.png\nsize: 64,64\n"
        + "".join(f"region\n  bounds: 0,0,1,1\n  index: {index}\n" for index in indices)
    ).encode()
    assert bool(parse_atlas(payload).duplicate_regions) is conflicting


def test_standalone_atlas_cannot_bypass_dependency_ambiguity() -> None:
    from fnx_spine_forge.conversion.atlas import AtlasConverter

    payload = (
        b"page.png\nsize: 64,64\nregion\n  bounds: 0,0,1,1\n  index: 0\n"
        b"region\n  bounds: 1,1,1,1\n  index: 0\n"
    )
    with pytest.raises(ValueError, match="Conflicting"):
        AtlasConverter(experimental_structural=True).convert(
            payload, "4.3.13", source_version="4.2.43"
        )


@pytest.mark.parametrize("cleanup_scope", ["package", "snapshot"])
def test_cleanup_after_commit_is_a_warning_not_a_failed_job(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, cleanup_scope: str
) -> None:
    import tempfile

    source = setup_source(tmp_path / "source")
    original = tempfile.TemporaryDirectory.cleanup

    def cleanup(directory: tempfile.TemporaryDirectory[str]) -> None:
        name = Path(directory.name).name
        original(directory)
        if (cleanup_scope == "package" and name.startswith(".complete.zip.")) or (
            cleanup_scope == "snapshot" and name.startswith("fnx-bundle-input-")
        ):
            raise OSError("simulated staging cleanup failure after commit")

    monkeypatch.setattr(tempfile.TemporaryDirectory, "cleanup", cleanup)
    result = BundleService().convert_bundle(
        BundleRequest(source, "4.2.43", tmp_path / "complete.zip", experimental_structural=True)
    )
    assert result.status == JobStatus.COMPLETED and result.published
    assert result.report.cleanup_warning is not None
    assert result.report.diagnostic is None
    assert result.report.package_integrity == VerificationState.PASSED
    with ZipFile(tmp_path / "complete.zip") as archive:
        assert archive.testzip() is None


def test_mypy_rejects_dictionary_report_api_and_string_authorization(tmp_path: Path) -> None:
    import subprocess
    import sys

    client = tmp_path / "invalid_client.py"
    client.write_text("""from pathlib import Path
from fnx_spine_forge.bundle_models import BundleRequest, BundleResult

def invalid(result: BundleResult) -> None:
    result.report["publication"] = "passed"

request = BundleRequest(Path("assets"), "4.2.43", Path("out.zip"),
                        skeleton_format="json", experimental_structural="false")
""")
    process = subprocess.run(
        [sys.executable, "-m", "mypy", "--strict", str(client)],
        capture_output=True,
        text=True,
        check=False,
    )
    assert process.returncode == 1
    assert "[index]" in process.stdout and "[arg-type]" in process.stdout


@pytest.mark.parametrize(
    "name",
    ["NUL", "dir/COM1.txt", "LPT².png", "a:stream.png", "trailing.", "trailing ", "control\n.png"],
)
def test_portable_paths_reject_windows_devices_ads_and_aliases(name: str, tmp_path: Path) -> None:
    archive = tmp_path / "unsafe.zip"
    with ZipFile(archive, "w") as writer:
        writer.writestr(name, b"payload")
    with pytest.raises(UnsafeSourceError):
        with AssetSource(archive):
            pass
    with pytest.raises(UnsafeSourceError):
        stage_files(tmp_path / "stage", {name: b"payload"})
    assert not (tmp_path / "stage").exists()


def test_zip_budget_applies_before_index_allocation(tmp_path: Path) -> None:
    archive = tmp_path / "budget.zip"
    with ZipFile(archive, "w") as writer:
        writer.writestr("asset", b"bytes")
    with pytest.raises(UnsafeSourceError, match="archive byte limit"):
        with AssetSource(archive, SourceLimits(max_archive_bytes=10)):
            pass
    with pytest.raises(UnsafeSourceError, match="metadata limit"):
        with AssetSource(archive, SourceLimits(max_archive_index_bytes=32)):
            pass


def test_zip_index_budget_does_not_limit_member_payload_reads(tmp_path: Path) -> None:
    archive = tmp_path / "large-member.zip"
    content = b"file data" * 2000
    with ZipFile(archive, "w") as writer:
        writer.writestr("asset", content)
    with AssetSource(archive, SourceLimits(max_archive_index_bytes=256)) as source:
        assert source.read("asset") == content


def test_zip_nul_filename_is_rejected_before_stdlib_truncation(tmp_path: Path) -> None:
    archive = tmp_path / "nul.zip"
    with ZipFile(archive, "w") as writer:
        writer.writestr("safeXhidden", b"content")
    archive.write_bytes(archive.read_bytes().replace(b"safeXhidden", b"safe\0hidden"))
    with pytest.raises(UnsafeSourceError, match="Unsafe path"):
        with AssetSource(archive):
            pass
