"""Capture evidence and thresholded image metrics without conversion promotion."""

from __future__ import annotations

import base64
import tempfile
from dataclasses import dataclass
from hashlib import sha256
from io import BytesIO
from pathlib import Path

from PIL import Image, ImageChops

from ..atomic_io import publish_directory
from ..json_types import JSONDocument, encode_json, is_document
from .service import ViewerAssetSet


@dataclass(frozen=True)
class VisualPolicy:
    reference_id: str
    reference_sha256: str
    provenance: str
    accepted_by: str
    channel_tolerance: int = 8
    max_changed_fraction: float = 0.005
    max_mean_error: float = 0.5

    def __post_init__(self) -> None:
        if not all((self.reference_id, self.provenance, self.accepted_by)):
            raise ValueError("Accepted reference provenance and review authority are required")
        if len(self.reference_sha256) != 64:
            raise ValueError("Reference checksum required")
        if not 0 <= self.channel_tolerance <= 255:
            raise ValueError("Channel tolerance outside byte range")
        if not 0 <= self.max_changed_fraction <= 1 or not 0 <= self.max_mean_error <= 255:
            raise ValueError("Invalid visual thresholds")


@dataclass(frozen=True)
class ImageMetrics:
    width: int
    height: int
    changed_pixels: int
    changed_fraction: float
    mean_absolute_error: float
    maximum_channel_error: int
    alpha_changed_pixels: int
    alpha_mean_error: float

    def to_dict(self) -> JSONDocument:
        return {
            "width": self.width,
            "height": self.height,
            "changed_pixels": self.changed_pixels,
            "changed_fraction": self.changed_fraction,
            "mean_absolute_error": self.mean_absolute_error,
            "maximum_channel_error": self.maximum_channel_error,
            "alpha_changed_pixels": self.alpha_changed_pixels,
            "alpha_mean_error": self.alpha_mean_error,
        }


@dataclass(frozen=True)
class ComparisonResult:
    status: str
    metrics: ImageMetrics
    reference_sha256: str
    candidate_sha256: str
    policy: VisualPolicy | None
    diff_png: bytes
    overlay_png: bytes

    def to_dict(self) -> JSONDocument:
        policy = self.policy
        return {
            "status": self.status,
            "metrics": self.metrics.to_dict(),
            "reference_sha256": self.reference_sha256,
            "candidate_sha256": self.candidate_sha256,
            "conversion_qualification_changed": False,
            "policy": None
            if policy is None
            else {
                "reference_id": policy.reference_id,
                "provenance": policy.provenance,
                "accepted_by": policy.accepted_by,
                "channel_tolerance": policy.channel_tolerance,
                "max_changed_fraction": policy.max_changed_fraction,
                "max_mean_error": policy.max_mean_error,
            },
        }


def _image(payload: bytes) -> Image.Image:
    if len(payload) > 128 * 1024 * 1024:
        raise ValueError("VIEWER_RESOURCE_LIMIT_EXCEEDED")
    image = Image.open(BytesIO(payload))
    if image.format != "PNG" or image.width * image.height > 16777216:
        image.close()
        raise ValueError("FRAME_CAPTURE_FAILED: expected bounded PNG")
    try:
        return image.convert("RGBA")
    finally:
        image.close()


def _png(image: Image.Image) -> bytes:
    stream = BytesIO()
    image.save(stream, format="PNG")
    return stream.getvalue()


class VerificationService:
    def compare(
        self,
        reference: bytes,
        candidate: bytes,
        reference_normalization: JSONDocument,
        candidate_normalization: JSONDocument,
        policy: VisualPolicy | None = None,
    ) -> ComparisonResult:
        required = {
            "camera",
            "width",
            "height",
            "dpr",
            "background",
            "debug",
            "colorSpace",
            "antialias",
        }
        if (
            not required <= reference_normalization.keys()
            or not required <= candidate_normalization.keys()
        ):
            raise ValueError("VISUAL_COMPARISON_UNAVAILABLE: normalization metadata missing")
        if any(reference_normalization[k] != candidate_normalization[k] for k in required):
            raise ValueError("VISUAL_COMPARISON_UNAVAILABLE: viewport/camera normalization differs")
        ref_hash, candidate_hash = sha256(reference).hexdigest(), sha256(candidate).hexdigest()
        if policy and ref_hash != policy.reference_sha256:
            raise ValueError("VISUAL_COMPARISON_UNAVAILABLE: accepted reference checksum differs")
        with _image(reference) as a, _image(candidate) as b:
            if a.size != b.size:
                raise ValueError("VISUAL_COMPARISON_UNAVAILABLE: image dimensions differ")
            if (
                a.width != reference_normalization["width"]
                or a.height != reference_normalization["height"]
            ):
                raise ValueError("VISUAL_COMPARISON_UNAVAILABLE: dimensions do not match metadata")
            difference = ImageChops.difference(a, b)
            tolerance = policy.channel_tolerance if policy else 8
            pixels = a.width * a.height
            changed = 0
            alpha_changed = 0
            total = 0
            alpha_total = 0
            maximum = 0
            # Raw bytes avoid Pillow's untyped pixel API and retain alpha errors.
            values = difference.tobytes()
            for offset in range(0, len(values), 4):
                channels = values[offset : offset + 4]
                top = max(channels)
                changed += top > tolerance
                alpha_changed += channels[3] > tolerance
                total += sum(channels)
                alpha_total += channels[3]
                maximum = max(maximum, top)
            metrics = ImageMetrics(
                a.width,
                a.height,
                changed,
                changed / pixels,
                total / (pixels * 4),
                maximum,
                alpha_changed,
                alpha_total / pixels,
            )
            # Make alpha-only changes visible in the exported diff.
            visual = Image.new("RGBA", a.size)
            rendered = bytearray(values)
            for offset in range(0, len(rendered), 4):
                alpha_error = rendered[offset + 3]
                for channel in range(3):
                    rendered[offset + channel] = max(rendered[offset + channel], alpha_error)
                rendered[offset + 3] = 255
            visual.frombytes(bytes(rendered))
            overlay = Image.blend(a, b, 0.5)
            status = "FRAME_COMPARED_NO_ACCEPTED_REFERENCE"
            if policy:
                status = (
                    "VISUALLY_VERIFIED"
                    if metrics.changed_fraction <= policy.max_changed_fraction
                    and metrics.mean_absolute_error <= policy.max_mean_error
                    else "VISUAL_CHECK_FAILED"
                )
            return ComparisonResult(
                status, metrics, ref_hash, candidate_hash, policy, _png(visual), _png(overlay)
            )

    def record_capture(
        self,
        assets: ViewerAssetSet,
        capture: JSONDocument,
        destination: Path,
    ) -> JSONDocument:
        encoded = capture.get("png")
        checksum = capture.get("sha256")
        if not isinstance(encoded, str) or not encoded.startswith("data:image/png;base64,"):
            raise ValueError("FRAME_CAPTURE_FAILED")
        if len(encoded) > 180 * 1024 * 1024:
            raise ValueError("VIEWER_RESOURCE_LIMIT_EXCEEDED")
        payload = base64.b64decode(encoded.split(",", 1)[1], validate=True)
        if sha256(payload).hexdigest() != checksum:
            raise ValueError("FRAME_CAPTURE_FAILED: checksum mismatch")
        with _image(payload) as image:
            if image.size != (capture.get("width"), capture.get("height")):
                raise ValueError("FRAME_CAPTURE_FAILED: dimensions mismatch")
            if image.getchannel("A").getextrema()[1] == 0:
                raise ValueError("FRAME_CAPTURE_FAILED: empty transparent canvas")
        pose = capture.get("pose")
        if not is_document(pose):
            raise ValueError("FRAME_CAPTURE_FAILED: pose missing")
        if pose.get("exportVersion") != assets.export_version:
            raise ValueError("RUNTIME_VERSION_MISMATCH")
        expected = f"{assets.runtime.family}@{assets.runtime.revision}"
        if pose.get("runtime") != expected:
            raise ValueError("RUNTIME_VERSION_MISMATCH")
        report: JSONDocument = {
            "status": "FRAME_CAPTURED",
            "runtime_verified": "specific_capture_only",
            "visually_verified": False,
            "conversion_qualification_changed": False,
            "binary_codec_qualified": False,
            "asset_id": assets.asset_id,
            "source_risk": assets.source_risk,
            "checksums": dict(assets.checksums),
            "capture": {key: value for key, value in capture.items() if key != "png"},
        }
        destination.parent.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(
            prefix=".fnx-capture-", dir=destination.parent
        ) as temporary:
            stage = Path(temporary) / "capture"
            stage.mkdir()
            (stage / "frame.png").write_bytes(payload)
            (stage / "report.json").write_bytes(encode_json(report))
            publish_directory(stage, destination)
        return report
