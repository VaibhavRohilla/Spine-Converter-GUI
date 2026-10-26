"""B4 service boundary and hostile transport/evidence tests."""

import base64
import json
from hashlib import sha256
from io import BytesIO
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import Request, urlopen
from zipfile import ZipFile

import pytest
from PIL import Image

from fnx_spine_forge.bundle_models import DependencyMappings
from fnx_spine_forge.json_types import decode_json_object
from fnx_spine_forge.parsers import inspect_skeleton
from fnx_spine_forge.progress import CancellationToken
from fnx_spine_forge.viewer.protocol import ViewerRequest
from fnx_spine_forge.viewer.registry import RuntimeRegistry
from fnx_spine_forge.viewer.server import ViewerServer
from fnx_spine_forge.viewer.service import BinarySelection, ViewerService
from fnx_spine_forge.viewer.session import ViewerSession, ViewerSessionManager, ViewerState
from fnx_spine_forge.viewer.verification import VerificationService, VisualPolicy

FIXTURES = Path(__file__).resolve().parents[1] / "viewer" / "fixtures"


@pytest.mark.parametrize(
    "version,family",
    [
        ("3.8.55", "3.8"),
        ("3.8.99", "3.8"),
        ("4.0.64", "4.0"),
        ("4.1.0", "4.1"),
        ("4.2.22", "4.2"),
        ("4.3.75-beta", "4.3"),
    ],
)
def test_runtime_family_matches_major_minor(version, family):
    runtime = RuntimeRegistry().select(version)
    assert runtime.family == family
    assert runtime.supports(version)
    assert not runtime.supports("9.9.9")


@pytest.mark.parametrize("version", ["3.5.51", "3.6.53", "3.7.94", "4.4.1", "garbage"])
def test_unimplemented_registry_rejects(version):
    with pytest.raises(ValueError):
        RuntimeRegistry().select(version)


def test_source_risk_is_not_version_relabeling(tmp_path):
    source = FIXTURES / "3.8"
    for name in ("spineboy-pro.json", "spineboy.atlas", "spineboy.png"):
        (tmp_path / name).write_bytes((source / name).read_bytes())
    path = tmp_path / "spineboy-pro.json"
    document = json.loads(path.read_text())
    document["skeleton"]["spine"] = "3.8.75"
    path.write_text(json.dumps(document))
    before = path.read_bytes()
    asset = ViewerService().prepare(tmp_path, path.name)
    assert asset.source_risk and asset.export_version == "3.8.75"
    assert asset.files[path.name] == before == path.read_bytes()


def test_explicit_bundle_zip_and_folder_have_same_snapshot(tmp_path):
    root = FIXTURES / "4.2"
    archive = tmp_path / "bundle.zip"
    with ZipFile(archive, "w") as zip_file:
        for name in ("spineboy-pro.json", "spineboy.atlas", "spineboy.png"):
            zip_file.write(root / name, name)
    service = ViewerService()
    a = service.prepare(root, "spineboy-pro.json")
    b = service.prepare(archive, "spineboy-pro.json")
    c = service.prepare(tuple(root / name for name in a.files), "spineboy-pro.json")
    assert a.checksums == b.checksums == c.checksums
    with pytest.raises(ValueError):
        service.prepare(root, "")
    with pytest.raises(TypeError):
        a.files["evil"] = b"x"


def test_binary_runtime_identity_separate_from_custom_codec():
    asset = ViewerService().prepare(
        FIXTURES / "3.8", "spineboy-pro.skel", binary=BinarySelection("3.8.55", "spineboy.atlas")
    )
    assert asset.binary and asset.export_version == "3.8.55"
    assert asset.files["spineboy-pro.skel"] == (FIXTURES / "3.8/spineboy-pro.skel").read_bytes()
    with pytest.raises(ValueError):
        ViewerService().prepare(FIXTURES / "3.8", "spineboy-pro.skel")


def test_authored_attachment_name_override_is_canonical():
    payload = json.dumps(
        {
            "skeleton": {"spine": "4.2.43"},
            "bones": [{"name": "root"}],
            "slots": [],
            "skins": [{"name": "a", "attachments": {"slot": {"entry": {"name": "authored/name"}}}}],
        }
    ).encode()
    info = inspect_skeleton(payload)
    assert info and info.attachment_paths == ("authored/name",)


def test_b3_explicit_skin_atlas_mapping_and_pma():
    root = FIXTURES / "features/4.2-goblins"
    asset = ViewerService().prepare(
        root,
        "goblins-pro.json",
        DependencyMappings(atlases={"goblins-pro.json": "goblins-pma.atlas"}),
    )
    assert all(page.pma for page in asset.pages.values())


def test_cancellation_and_limits_before_publication():
    token = CancellationToken()
    token.cancel()
    with pytest.raises(ValueError, match="VIEWER_SESSION_CANCELLED"):
        ViewerService().prepare(FIXTURES / "4.2", "spineboy-pro.json", cancellation=token)
    with pytest.raises(ValueError, match="VIEWER_RESOURCE_LIMIT_EXCEEDED"):
        ViewerService(100).prepare(FIXTURES / "4.2", "spineboy-pro.json")


@pytest.mark.parametrize("missing", ["spineboy.atlas", "spineboy.png"])
def test_missing_dependencies_fail(tmp_path, missing):
    root = FIXTURES / "4.2"
    for name in ("spineboy-pro.json", "spineboy.atlas", "spineboy.png"):
        if name != missing:
            (tmp_path / name).write_bytes((root / name).read_bytes())
    with pytest.raises(ValueError):
        ViewerService().prepare(tmp_path, "spineboy-pro.json")


def test_invalid_json_and_traversal_rejected(tmp_path):
    (tmp_path / "bad.json").write_text("{bad")
    with pytest.raises(ValueError):
        ViewerService().prepare(tmp_path, "bad.json")
    archive = tmp_path / "escape.zip"
    with ZipFile(archive, "w") as z:
        z.writestr("../escape.json", "{}")
    with pytest.raises(ValueError):
        ViewerService().prepare(archive, "escape.json")


def test_disposed_generation_cannot_revive():
    session = ViewerSession()
    with pytest.raises(ValueError):
        session.transition(ViewerState.PLAYING)
    session.transition(ViewerState.INSPECTING)
    generation = session.generation
    session.transition(ViewerState.DISPOSING)
    session.transition(ViewerState.DISPOSED)
    with pytest.raises(ValueError):
        session.transition(ViewerState.READY, generation)
    manager = ViewerSessionManager()
    created = manager.create()
    manager.dispose(created.session_id)
    assert not manager.sessions


def test_failed_session_retries_explicitly():
    session = ViewerSession()
    session.transition(ViewerState.INSPECTING)
    session.transition(ViewerState.FAILED)
    session.transition(ViewerState.INSPECTING)
    session.transition(ViewerState.LOADING_RUNTIME)
    assert session.generation == 2


@pytest.mark.parametrize(
    "command,payload",
    [
        ("PLAY", {}),
        ("SEEK", {"seconds": 1.25}),
        ("SET_SKIN", {"name": None}),
        ("SET_BACKGROUND", {"rgba": [0, 0, 0, 0]}),
        ("SET_VIEWPORT", None),
        ("SET_VIEWPORT", {"width": 640, "height": 480, "pixelRatio": 2}),
        (
            "SET_DEBUG",
            dict.fromkeys(
                [
                    "bones",
                    "regions",
                    "meshTriangles",
                    "meshHull",
                    "clipping",
                    "boundingBoxes",
                    "paths",
                    "origin",
                    "bounds",
                ],
                False,
            ),
        ),
    ],
)
def test_protocol_round_trip(command, payload):
    document = {
        "protocolVersion": 1,
        "sessionId": "session",
        "requestId": "request",
        "command": command,
        "payload": payload,
    }
    request = ViewerRequest.decode(json.dumps(document))
    assert request.to_dict() == document


@pytest.mark.parametrize(
    "change",
    [
        {"protocolVersion": 2},
        {"command": "exec"},
        {"payload": {"seconds": float("inf")}},
        {"payload": {"seconds": True}},
        {"payload": {"seconds": -1}},
        {"payload": {"seconds": 601}},
        {"unexpected": 1},
    ],
)
def test_hostile_protocol(change):
    document = {
        "protocolVersion": 1,
        "sessionId": "s",
        "requestId": "r",
        "command": "SEEK",
        "payload": {"seconds": 0},
    }
    document.update(change)
    with pytest.raises(ValueError):
        ViewerRequest.decode(json.dumps(document))


def test_transport_has_no_arbitrary_filesystem_or_cross_origin_access(tmp_path):
    (tmp_path / "index.html").write_text("<html>test</html>")
    asset = ViewerService().prepare(FIXTURES / "4.2", "spineboy-pro.json")
    server = ViewerServer((asset,), tmp_path)
    url = server.start()
    try:
        with urlopen(url + "sessions.json") as response:
            assert "default-src 'none'" in response.headers["Content-Security-Policy"]
            doc = json.load(response)
        assert "source" not in doc[0]
        for path in (
            "../pyproject.toml",
            "asset/0/%2e%2e%2fpyproject.toml",
            "asset/0/LICENSE",
            "asset/99/x",
        ):
            with pytest.raises(HTTPError):
                urlopen(url + path)
        with pytest.raises(HTTPError):
            urlopen(Request(url + "sessions.json", headers={"Origin": "https://evil.example"}))
        with pytest.raises(HTTPError):
            urlopen(Request(url + "sessions.json", headers={"Host": "evil.example"}))
        with urlopen(url + "launch/0.json") as response:
            session = json.load(response)
        session_id = session["sessionId"]
        state_url = url + "state/" + session_id
        with pytest.raises(HTTPError):
            urlopen(
                Request(
                    state_url,
                    data=b'{"protocolVersion":1,"state":"PLAYING"}',
                    headers={"Origin": server.origin, "Content-Type": "application/json"},
                )
            )
        for state in ("DISPOSING", "DISPOSED"):
            with urlopen(
                Request(
                    state_url,
                    data=json.dumps({"protocolVersion": 1, "state": state}).encode(),
                    headers={"Origin": server.origin, "Content-Type": "application/json"},
                )
            ) as response:
                assert response.status == 204
        assert session_id not in server.manager.sessions
    finally:
        server.close()
    assert not server.assets and not server.web_files


def png(color):
    buffer = BytesIO()
    Image.new("RGBA", (4, 4), color).save(buffer, format="PNG")
    return buffer.getvalue()


def normalization():
    return {
        "camera": {"x": 0, "y": 0, "width": 4, "height": 4, "zoom": 1},
        "width": 4,
        "height": 4,
        "dpr": 1,
        "background": [0, 0, 0, 0],
        "debug": {},
        "colorSpace": "srgb",
        "antialias": False,
    }


def test_visual_comparison_never_promotes_without_reference():
    a, b = png((0, 0, 0, 255)), png((1, 0, 0, 200))
    service = VerificationService()
    result = service.compare(a, b, normalization(), normalization())
    assert result.status == "FRAME_COMPARED_NO_ACCEPTED_REFERENCE"
    assert result.metrics.alpha_changed_pixels == 16
    assert result.metrics.maximum_channel_error == 55
    policy = VisualPolicy(
        "official-test", sha256(a).hexdigest(), "synthetic test reference", "test-suite"
    )
    assert (
        service.compare(a, a, normalization(), normalization(), policy).status
        == "VISUALLY_VERIFIED"
    )
    assert (
        service.compare(a, b, normalization(), normalization(), policy).status
        == "VISUAL_CHECK_FAILED"
    )
    with pytest.raises(ValueError, match="normalization differs"):
        service.compare(a, b, normalization(), {**normalization(), "dpr": 2})
    with pytest.raises(ValueError, match="checksum differs"):
        service.compare(b, a, normalization(), normalization(), policy)


def test_capture_checks_png_checksum_dimensions_and_runtime(tmp_path):
    asset = ViewerService().prepare(FIXTURES / "4.2", "spineboy-pro.json")
    image = png((120, 20, 10, 255))
    capture = {
        "png": "data:image/png;base64," + base64.b64encode(image).decode(),
        "sha256": sha256(image).hexdigest(),
        "width": 4,
        "height": 4,
        "pose": {"runtime": "4.2@4.2.43", "exportVersion": asset.export_version},
    }
    # Synthetic byte fixture tests serialization, not runtime or rendering qualification.
    report = VerificationService().record_capture(asset, capture, tmp_path / "capture")
    assert not report["visually_verified"] and not report["binary_codec_qualified"]
    assert (
        decode_json_object((tmp_path / "capture/report.json").read_text(), "report")["status"]
        == "FRAME_CAPTURED"
    )
    with pytest.raises(FileExistsError):
        VerificationService().record_capture(asset, capture, tmp_path / "capture")
    capture["sha256"] = "0" * 64
    with pytest.raises(ValueError, match="checksum mismatch"):
        VerificationService().record_capture(asset, capture, tmp_path / "rejected")
    assert not (tmp_path / "rejected").exists()


def test_render_capability_and_allocation_admission():
    from fnx_spine_forge.viewer.admission import admit_render_document

    with pytest.raises(ValueError, match="UNSUPPORTED_RENDER_FEATURE"):
        admit_render_document(
            {"skins": [{"name": "s", "attachments": {"slot": {"a": {"type": "future-shader"}}}}]},
            "4.2",
        )
    with pytest.raises(ValueError, match="VIEWER_RESOURCE_LIMIT_EXCEEDED"):
        admit_render_document({"bones": [{}] * 10001}, "4.2")
    with pytest.raises(ValueError, match="UNSUPPORTED_RENDER_FEATURE"):
        admit_render_document({"physics": [{}]}, "3.8")


@pytest.mark.parametrize(
    "mutation",
    [
        "duplicate_family", "unknown_capability", "duplicate_capability",
        "missing_identity", "binary_conflict", "unsupported_embedded",
    ],
)
def test_runtime_manifest_rejects_contradictory_capabilities(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, mutation: str
) -> None:
    from fnx_spine_forge.viewer import registry

    document = json.loads(Path(registry.__file__).with_name("runtime_manifest.json").read_text())
    row = next(row for row in document["runtimes"] if row["embeddedImplemented"])
    if mutation == "duplicate_family":
        document["runtimes"].append(row.copy())
    elif mutation == "unknown_capability":
        row["capabilities"].append("PRETEND_RENDERING")
    elif mutation == "duplicate_capability":
        row["capabilities"].append(row["capabilities"][0])
    elif mutation == "missing_identity":
        row["revision"] = None
    elif mutation == "binary_conflict":
        row["binaryImplemented"] = False
    elif mutation == "unsupported_embedded":
        row["capabilities"].append("UNSUPPORTED")
    (tmp_path / "runtime_manifest.json").write_text(json.dumps(document))
    monkeypatch.setattr(registry, "files", lambda package: tmp_path)
    with pytest.raises(ValueError):
        registry.RuntimeRegistry()
