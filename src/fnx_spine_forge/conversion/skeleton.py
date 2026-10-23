"""Conservative lossless JSON skeleton conversion."""

from __future__ import annotations

import json
from collections import Counter
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from ..detection import skeleton_version
from ..parsers import inspect_skeleton
from ..versions import VersionRegistry
from .migrate_38_42 import MigrationError, migrate_38_to_42
from .models import CanonicalSkeleton, ConversionResult, ConversionStatus, SourceRiskPolicy
from .planner import ConversionPlanner


def _records(value: Any) -> list[Mapping[str, Any]]:
    return [item for item in value if isinstance(item, Mapping)] if isinstance(value, list) else []


def _skin_names(skins: Any) -> tuple[str, ...]:
    if isinstance(skins, Mapping):
        return tuple(str(name) for name in skins)
    return tuple(str(item["name"]) for item in _records(skins) if isinstance(item.get("name"), str))


def _animation_metrics(document: dict[str, Any]) -> tuple[dict[str, int], dict[str, int]]:
    timelines: Counter[str] = Counter()
    keyframes: Counter[str] = Counter()

    def record(kind: str, frames: Any) -> None:
        if isinstance(frames, list):
            timelines[kind] += 1
            keyframes[kind] += len(frames)

    for animation in document.get("animations", {}).values():
        for groups in animation.get("bones", {}).values():
            for name, frames in groups.items():
                record(f"bone.{name}", frames)
        for groups in animation.get("slots", {}).values():
            for name, frames in groups.items():
                record(f"slot.{name}", frames)
        for category in ("ik", "transform"):
            for frames in animation.get(category, {}).values():
                record(f"{category}.mix", frames)
        for groups in animation.get("path", {}).values():
            for name, frames in groups.items():
                record(f"path.{name}", frames)
        for skin in animation.get("attachments", {}).values():
            for slot in skin.values():
                for attachment in slot.values():
                    for name, frames in attachment.items():
                        record(f"attachment.{name}", frames)
        record("drawOrder", animation.get("drawOrder"))
        record("event", animation.get("events"))
    return dict(sorted(timelines.items())), dict(sorted(keyframes.items()))


class SkeletonConverter:
    """Read/serialize JSON skeletons without claiming unimplemented migrations."""

    def __init__(self, planner: ConversionPlanner | None = None) -> None:
        self.planner = planner or ConversionPlanner(
            {
                ("3.5", "3.5"),
                ("3.6", "3.6"),
                ("3.7", "3.7"),
                ("3.8", "3.8"),
                ("4.0", "4.0"),
                ("4.1", "4.1"),
                ("4.2", "4.2"),
                ("4.3", "4.3"),
                ("3.8.75", "4.2.43"),
            }
        )
        self.versions = VersionRegistry()

    def read(self, source: bytes | str | Path) -> CanonicalSkeleton:
        payload = source if isinstance(source, bytes) else Path(source).read_bytes()
        valid, version, error = skeleton_version(payload)
        if not valid or version is None or error:
            raise ValueError(error or "Input is not a versioned Spine JSON skeleton")
        obj = json.loads(payload.decode("utf-8-sig"))
        if not isinstance(obj, dict):
            raise ValueError("Skeleton root must be an object")
        family = self.versions.family_for(version)
        if family is None:
            raise ValueError(f"Unsupported Spine version family: {version}")
        bones = tuple(
            str(row["name"])
            for row in _records(obj.get("bones"))
            if isinstance(row.get("name"), str)
        )
        slots = tuple(
            str(row["name"])
            for row in _records(obj.get("slots"))
            if isinstance(row.get("name"), str)
        )
        animations = (
            tuple(obj.get("animations", {}).keys())
            if isinstance(obj.get("animations", {}), dict)
            else ()
        )
        return CanonicalSkeleton(
            version, obj, bones, slots, _skin_names(obj.get("skins", {})), animations
        )

    def convert(
        self,
        source: bytes | str | Path,
        target_version: str,
        *,
        source_risk_policy: SourceRiskPolicy = SourceRiskPolicy.REJECT_KNOWN_ISSUES,
    ) -> ConversionResult:
        try:
            canonical = self.read(source)
        except (OSError, ValueError, UnicodeError, json.JSONDecodeError) as exc:
            return ConversionResult(
                None, target_version, (), None, ConversionStatus.REJECTED, (str(exc),)
            )
        plan = self.planner.plan(canonical.version, target_version)
        if not plan.executable:
            return ConversionResult(
                canonical.version,
                target_version,
                plan.route,
                None,
                ConversionStatus.REJECTED,
                plan.diagnostics,
            )
        known_export_issue = canonical.version == "3.8.75"
        if known_export_issue and source_risk_policy is SourceRiskPolicy.REJECT_KNOWN_ISSUES:
            return ConversionResult(
                canonical.version,
                target_version,
                plan.route,
                None,
                ConversionStatus.REJECTED,
                (
                    "Spine 3.8.75 exports are affected by officially acknowledged export issues; "
                    "re-export from Spine 3.8.99 when the original project is available, or pass "
                    "an explicit allow-with-diagnostic source risk policy.",
                ),
                diagnostic_codes=("SOURCE_EXPORT_KNOWN_BUG",),
                provenance={"declared_source_version": canonical.version},
            )
        if canonical.version == "3.8.75" and target_version == "4.2.43":
            try:
                migrated, metrics = migrate_38_to_42(canonical.document)
                output = (
                    json.dumps(migrated, ensure_ascii=False, separators=(",", ":"), allow_nan=False)
                    + "\n"
                ).encode()
            except (MigrationError, TypeError, ValueError) as exc:
                return ConversionResult(
                    canonical.version,
                    target_version,
                    plan.route,
                    None,
                    ConversionStatus.REJECTED,
                    (str(exc),),
                )
            info = inspect_skeleton(output)
            if info is None or info.version != target_version:
                return ConversionResult(
                    canonical.version,
                    target_version,
                    plan.route,
                    None,
                    ConversionStatus.REJECTED,
                    ("Migrated skeleton failed target structural reinspection",),
                )
            counts = {
                "region": 0,
                "mesh": 0,
                "linkedmesh": 0,
                "boundingbox": 0,
                "path": 0,
                "point": 0,
                "clipping": 0,
            }
            for skin in migrated.get("skins", []):
                for attachments in skin.get("attachments", {}).values():
                    for name, attachment in attachments.items():
                        kind = attachment.get("type", "region")
                        if kind in counts:
                            counts[kind] += 1
            stats = {
                "bones": len(canonical.bones),
                "slots": len(canonical.slots),
                "skins": len(canonical.skins),
                "animations": len(canonical.animations),
                "bezier_segments": metrics["bezier_segments"],
                "max_numerical_error": metrics["max_curve_error"],
                "timeline_count": metrics["timeline_count"],
                "keyframes": metrics["keyframes"],
                "attachment_region": counts["region"],
                "attachment_mesh": counts["mesh"],
                "attachment_linkedmesh": counts["linkedmesh"],
                "attachment_boundingbox": counts["boundingbox"],
                "attachment_path": counts["path"],
                "attachment_point": counts["point"],
                "attachment_clipping": counts["clipping"],
            }
            timeline_counts, keyframe_counts = _animation_metrics(migrated)
            details: dict[str, Any] = {
                "animation_names": list(canonical.animations),
                "timeline_counts_by_type": timeline_counts,
                "keyframe_counts_by_type": keyframe_counts,
                "unsupported_features": [],
                "structural_verification": "passed",
            }
            return ConversionResult(
                canonical.version,
                target_version,
                plan.route,
                output,
                ConversionStatus.STRUCTURALLY_VERIFIED,
                (),
                stats,
                details,
                diagnostic_codes=("SOURCE_EXPORT_KNOWN_BUG",) if known_export_issue else (),
                provenance=(
                    {
                        "declared_source_version": canonical.version,
                        "known_source_export_risk": True,
                        "potentially_affected_features": "unspecified by official notice",
                        "recommended_action": "authentically re-export from Spine 3.8.99",
                        "source_fidelity": "unverified_without_trusted_baseline",
                    }
                    if known_export_issue
                    else {"declared_source_version": canonical.version}
                ),
                feature_compatibility={
                    "implemented_route_features": "supported_and_structurally_verified",
                    "source_export_fidelity": "supported_with_limitations",
                    "runtime_load": "separate_optional_harness_not_executed_during_conversion",
                    "visual_equivalence": "not_implemented",
                },
            )
        # Same-family serialization is only accepted for an exact exporter version.
        if canonical.version != target_version:
            return ConversionResult(
                canonical.version,
                target_version,
                plan.route,
                None,
                ConversionStatus.REJECTED,
                ("Only exact-version semantic round trips are implemented",),
            )
        output = (
            json.dumps(canonical.document, ensure_ascii=False, separators=(",", ":")) + "\n"
        ).encode()
        info = inspect_skeleton(output)
        if info is None:
            return ConversionResult(
                canonical.version,
                target_version,
                plan.route,
                None,
                ConversionStatus.REJECTED,
                ("Serialized skeleton failed structural reinspection",),
            )
        stats = {
            "bones": len(canonical.bones),
            "slots": len(canonical.slots),
            "skins": len(canonical.skins),
            "animations": len(canonical.animations),
        }
        return ConversionResult(
            canonical.version,
            target_version,
            plan.route,
            output,
            ConversionStatus.STRUCTURALLY_VERIFIED,
            (),
            stats,
        )
