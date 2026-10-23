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
from .migrate_37_to_38 import migrate_37_to_38
from .migrate_38_to_4x import MigrationError, migrate_38_to_target
from .migrate_38_to_legacy import legacy_target_profile, migrate_38_to_legacy
from .migrate_40_to_41 import migrate_40_to_41
from .migrate_41_to_42 import migrate_41_to_42
from .migrate_42_to_43 import migrate_42_to_43
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
        attachment_timelines = animation.get("attachments", animation.get("deform", {}))
        for skin in attachment_timelines.values():
            for slot in skin.values():
                for attachment in slot.values():
                    if isinstance(attachment, list):
                        record("attachment.deform", attachment)
                    elif isinstance(attachment, Mapping):
                        for name, frames in attachment.items():
                            record(f"attachment.{name}", frames)
        record("drawOrder", animation.get("drawOrder", animation.get("draworder")))
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
                ("3.8.99", "4.2.43"),
                ("3.8.75", "4.1.56"),
                ("3.8.99", "4.1.56"),
                ("3.8.75", "4.0.31"),
                ("3.8.99", "4.0.31"),
                ("3.8.75", "4.3.13"),
                ("3.8.99", "4.3.13"),
                ("3.8.75", "3.7.94"),
                ("3.8.99", "3.7.94"),
                ("3.8.75", "3.6.53"),
                ("3.8.99", "3.6.53"),
                ("3.8.75", "3.5.51"),
                ("3.8.99", "3.5.51"),
                ("4.2.43", "4.3.13"),
                ("4.1.56", "4.2.43"),
                ("4.0.31", "4.1.56"),
                ("3.7.94", "3.8.99"),
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
        if (canonical.version, target_version) in {
            ("3.7.94", "3.8.99"),
            ("4.0.31", "4.1.56"),
            ("4.1.56", "4.2.43"),
            ("4.2.43", "4.3.13"),
        }:
            try:
                if canonical.version == "3.7.94":
                    migrated, metrics = migrate_37_to_38(
                        canonical.document, canonical.version, target_version
                    )
                elif canonical.version == "4.0.31":
                    migrated, metrics = migrate_40_to_41(
                        canonical.document, canonical.version, target_version
                    )
                elif canonical.version == "4.1.56":
                    migrated, metrics = migrate_41_to_42(
                        canonical.document, canonical.version, target_version
                    )
                else:
                    migrated, metrics = migrate_42_to_43(
                        canonical.document, canonical.version, target_version
                    )
                output = (
                    json.dumps(migrated, ensure_ascii=False, separators=(",", ":"), allow_nan=False)
                    + "\n"
                ).encode()
            except (MigrationError, TypeError, ValueError) as exc:
                message = str(exc)
                direct_unsupported: tuple[str, ...] = ()
                codes: tuple[str, ...] = ()
                if target_version == "4.3.13" and (
                    "transform constraints" in message or "uniform IK" in message
                ):
                    direct_unsupported = ("transform_constraints",)
                    codes = ("UNSUPPORTED_TARGET_FEATURE",)
                return ConversionResult(
                    canonical.version,
                    target_version,
                    plan.route,
                    None,
                    ConversionStatus.REJECTED,
                    (message,),
                    unsupported_features=direct_unsupported,
                    diagnostic_codes=codes,
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
            attachment_counts = Counter(
                attachment.get("type", "region")
                for skin in migrated.get("skins", [])
                for attachments in skin.get("attachments", {}).values()
                for attachment in attachments.values()
                if isinstance(attachment, dict)
            )
            timelines, keys = _animation_metrics(migrated)
            compatibility = {
                "implemented_route_features": "supported_and_structurally_verified",
                "animation_curves": "target_channel_controls_preserved_exactly",
                "target_runtime": "not_executed_during_conversion",
                "visual_equivalence": "not_assessed",
            }
            if target_version == "4.3.13":
                compatibility.update(
                    {
                        "ik_constraints": "supported_by_target_schema",
                        "path_constraints": "supported_by_target_schema",
                        "transform_constraints": "unsupported_blocking",
                    }
                )
            elif target_version == "4.2.43":
                compatibility["bone_transform"] = "4.1_transform_to_4.2_inherit_verified"
            elif target_version == "3.8.99":
                compatibility["skin_schema"] = "3.7_object_map_to_3.8_named_skin_array"
            else:
                compatibility.update(
                    {
                        "linked_mesh": "4.0_deform_flag_to_4.1_timelines_flag",
                        "deform_animation": "4.0_group_to_4.1_attachment_timeline",
                    }
                )
            stats = {
                "bones": len(canonical.bones),
                "slots": len(canonical.slots),
                "skins": len(canonical.skins),
                "animations": len(canonical.animations),
                "bezier_segments": metrics["bezier_segments"],
                "max_numerical_error": metrics["max_curve_error"],
                "timeline_count": sum(timelines.values()),
                "keyframes": sum(keys.values()),
                **{f"attachment_{kind}": count for kind, count in attachment_counts.items()},
            }
            return ConversionResult(
                canonical.version,
                target_version,
                plan.route,
                output,
                ConversionStatus.STRUCTURALLY_VERIFIED,
                statistics=stats,
                details={
                    "animation_names": list(canonical.animations),
                    "timeline_counts_by_type": timelines,
                    "keyframe_counts_by_type": keys,
                    "unsupported_features": [],
                    "structural_verification": "passed",
                    "feature_compatibility": compatibility.copy(),
                },
                feature_compatibility=compatibility,
            )
        if canonical.version in {"3.8.75", "3.8.99"} and target_version in {
            "3.5.51",
            "3.6.53",
            "3.7.94",
        }:
            try:
                migrated, metrics = migrate_38_to_legacy(
                    canonical.document, canonical.version, target_version
                )
                output = (
                    json.dumps(migrated, ensure_ascii=False, separators=(",", ":"), allow_nan=False)
                    + "\n"
                ).encode()
            except (MigrationError, TypeError, ValueError) as exc:
                message = str(exc)
                legacy_unsupported: tuple[str, ...] = ()
                diagnostic_code = "SOURCE_SCHEMA_INVALID"
                if "skin-specific bones or constraints" in message:
                    legacy_unsupported = ("skin_specific_constraints_or_bones",)
                    diagnostic_code = "UNSUPPORTED_TARGET_FEATURE"
                elif "IK softness" in message:
                    legacy_unsupported = ("ik_softness",)
                    diagnostic_code = "UNSUPPORTED_TARGET_FEATURE"
                elif "unsupported timeline" in message:
                    legacy_unsupported = ("unsupported_timeline_type",)
                    diagnostic_code = "UNSUPPORTED_TARGET_FEATURE"
                return ConversionResult(
                    canonical.version,
                    target_version,
                    plan.route,
                    None,
                    ConversionStatus.REJECTED,
                    (message,),
                    unsupported_features=legacy_unsupported,
                    diagnostic_codes=(diagnostic_code,),
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
            attachment_counts = Counter(
                attachment.get("type", "region")
                for skin in migrated["skins"].values()
                for slot in skin.values()
                for attachment in slot.values()
                if isinstance(attachment, dict)
            )
            timeline_counts, keyframe_counts = _animation_metrics(migrated)
            stats = {
                "bones": len(canonical.bones),
                "slots": len(canonical.slots),
                "skins": len(canonical.skins),
                "animations": len(canonical.animations),
                "bezier_segments": metrics["bezier_segments"],
                "max_numerical_error": metrics["max_curve_error"],
                "timeline_count": sum(timeline_counts.values()),
                "keyframes": sum(keyframe_counts.values()),
                **{f"attachment_{kind}": count for kind, count in attachment_counts.items()},
            }
            feature_compatibility = {
                "implemented_route_features": "supported_and_structurally_verified",
                "source_export_fidelity": "known_export_risk_unverified"
                if known_export_issue
                else "not_independently_proven",
                "target_runtime": "not_executed",
                "visual_equivalence": "not_assessed",
            }
            return ConversionResult(
                canonical.version,
                target_version,
                plan.route,
                output,
                ConversionStatus.STRUCTURALLY_VERIFIED,
                (),
                statistics=stats,
                details={
                    "animation_names": list(canonical.animations),
                    "timeline_counts_by_type": timeline_counts,
                    "keyframe_counts_by_type": keyframe_counts,
                    "unsupported_features": [],
                    "structural_verification": "passed",
                    "target_schema": legacy_target_profile(target_version),
                    "verification_level": "structural_only",
                    "feature_compatibility": feature_compatibility.copy(),
                },
                diagnostic_codes=("SOURCE_EXPORT_KNOWN_BUG",) if known_export_issue else (),
                provenance={
                    "declared_source_version": canonical.version,
                    "source_export_known_issue": known_export_issue,
                    "potentially_affected_features": "unspecified by official notice"
                    if known_export_issue
                    else "not applicable",
                    "recommended_action": "authentically re-export from Spine 3.8.99"
                    if known_export_issue
                    else "none",
                    "source_fidelity": "unverified_without_trusted_baseline",
                },
                feature_compatibility=feature_compatibility,
            )
        if canonical.version in {"3.8.75", "3.8.99"} and target_version in {
            "4.1.56",
            "4.2.43",
            "4.0.31",
            "4.3.13",
        }:
            try:
                migrated, metrics = migrate_38_to_target(
                    canonical.document, canonical.version, target_version
                )
                output = (
                    json.dumps(migrated, ensure_ascii=False, separators=(",", ":"), allow_nan=False)
                    + "\n"
                ).encode()
            except (MigrationError, TypeError, ValueError) as exc:
                message = str(exc)
                route_unsupported: tuple[str, ...] = ()
                diagnostic_codes: tuple[str, ...] = ()
                if target_version == "4.3.13" and (
                    "transform constraints" in message or "uniform IK" in message
                ):
                    route_unsupported = (
                        ("transform_constraints",)
                        if "transform constraints" in message
                        else ("uniform_ik_constraint_mode",)
                    )
                    diagnostic_codes = ("UNSUPPORTED_TARGET_FEATURE",)
                return ConversionResult(
                    canonical.version,
                    target_version,
                    plan.route,
                    None,
                    ConversionStatus.REJECTED,
                    (message,),
                    unsupported_features=route_unsupported,
                    diagnostic_codes=diagnostic_codes,
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
            feature_compatibility = {
                "implemented_route_features": "supported_and_structurally_verified",
                "source_export_fidelity": "supported_with_limitations"
                if known_export_issue
                else "not_independently_proven",
                "runtime_load": "separate_optional_harness_not_executed_during_conversion",
                "visual_equivalence": "not_implemented",
            }
            if target_version == "4.3.13":
                feature_compatibility.update(
                    {
                        "ik_constraints": "supported_and_verified",
                        "path_constraints": "supported_and_verified",
                        "transform_constraints": "unsupported_blocking",
                        "legacy_uniform_ik_mode": "unsupported_blocking",
                    }
                )
                details["feature_compatibility"] = feature_compatibility.copy()
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
                feature_compatibility=feature_compatibility,
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
