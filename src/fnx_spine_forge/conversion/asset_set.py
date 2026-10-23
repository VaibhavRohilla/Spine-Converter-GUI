"""Transactional conversion of a B1-resolved skeleton, atlas, and texture set."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from hashlib import sha256
from pathlib import Path

from ..inspection import InspectionService
from ..source import AssetSource
from .atlas import AtlasConverter
from .models import ConversionResult, ConversionStatus, SourceRiskPolicy
from .planner import ConversionPlanner
from .skeleton import SkeletonConverter


@dataclass(frozen=True, slots=True)
class AssetSetResult:
    """Outputs are populated only after every skeleton, atlas, and dependency check passes."""

    source_version: str | None
    target_version: str
    route: tuple[str, ...]
    skeleton_path: str | None
    atlas_paths: tuple[str, ...]
    outputs: Mapping[str, bytes] | None
    status: ConversionStatus
    diagnostics: tuple[str, ...] = ()
    details: Mapping[str, object] | None = None


class AssetSetValidationError(ValueError):
    def __init__(self, message: str, asset: str, feature: str, codes: tuple[str, ...]):
        super().__init__(message)
        self.asset = asset
        self.feature = feature
        self.codes = codes


class AssetSetConverter:
    """Convert one inspected B1 bundle entirely in memory, preserving texture bytes."""

    def __init__(
        self,
        planner: ConversionPlanner | None = None,
        inspection: InspectionService | None = None,
    ) -> None:
        self.planner = planner or ConversionPlanner()
        self.inspection = inspection or InspectionService()
        self.skeletons = SkeletonConverter(self.planner)
        self.atlases = AtlasConverter()

    def convert(
        self,
        origin: str | Path,
        skeleton_path: str,
        target_version: str,
        *,
        source_risk_policy: SourceRiskPolicy = SourceRiskPolicy.REJECT_KNOWN_ISSUES,
    ) -> AssetSetResult:
        manifest = self.inspection.inspect(str(origin))
        bundle = next((item for item in manifest.bundles if item.bundle_id == skeleton_path), None)
        related_paths: set[str] = set()
        if bundle is not None:
            related_paths.update((bundle.bundle_id, *bundle.atlases, *bundle.texture_pages))
        related_failure = any(
            diagnostic.severity.value in {"error", "blocker"}
            and (diagnostic.path is None or diagnostic.path in related_paths)
            for diagnostic in manifest.diagnostics
        )
        if bundle is None or bundle.validation_state != "valid" or related_failure:
            return AssetSetResult(
                None,
                target_version,
                (),
                skeleton_path,
                (),
                None,
                ConversionStatus.REJECTED,
                ("B1 did not resolve a valid logical asset bundle",),
                {"diagnostics": tuple(d.code for d in manifest.diagnostics)},
            )
        if len(bundle.skeletons) != 1 or not bundle.atlases:
            return AssetSetResult(
                None,
                target_version,
                (),
                skeleton_path,
                bundle.atlases,
                None,
                ConversionStatus.REJECTED,
                ("Asset bundle must resolve exactly one JSON skeleton and at least one atlas",),
            )
        try:
            with AssetSource(origin) as source:
                skeleton = source.read(skeleton_path)
                atlas_data = {name: source.read(name) for name in bundle.atlases}
                texture_data = {name: source.read(name) for name in bundle.texture_pages}
        except (OSError, ValueError, KeyError) as exc:
            return AssetSetResult(
                None,
                target_version,
                (),
                skeleton_path,
                bundle.atlases,
                None,
                ConversionStatus.REJECTED,
                (f"Unable to stage asset bundle: {exc}",),
            )
        try:
            source_version = self.skeletons.read(skeleton).version
        except (ValueError, UnicodeError) as exc:
            return AssetSetResult(
                None,
                target_version,
                (),
                skeleton_path,
                bundle.atlases,
                None,
                ConversionStatus.REJECTED,
                (str(exc),),
            )
        plan = self.planner.plan(source_version, target_version)
        route = plan.route
        if not plan.executable and len(route) < 3:
            return AssetSetResult(
                source_version,
                target_version,
                route,
                skeleton_path,
                bundle.atlases,
                None,
                ConversionStatus.REJECTED,
                plan.diagnostics,
            )

        try:
            self._validate_stage(
                {skeleton_path: skeleton, **atlas_data, **texture_data}, skeleton_path
            )
        except (ValueError, UnicodeError) as exc:
            return AssetSetResult(
                source_version,
                target_version,
                route,
                skeleton_path,
                bundle.atlases,
                None,
                ConversionStatus.REJECTED,
                (str(exc),),
                {"failed_stage": "source", "asset": skeleton_path, "reason": str(exc)},
            )

        if (
            source_version == "3.8.75"
            and source_risk_policy is SourceRiskPolicy.REJECT_KNOWN_ISSUES
        ):
            rejected = self.skeletons.convert(
                skeleton, target_version, source_risk_policy=source_risk_policy
            )
            return AssetSetResult(
                source_version,
                target_version,
                route,
                skeleton_path,
                bundle.atlases,
                None,
                ConversionStatus.REJECTED,
                rejected.diagnostics,
                {"diagnostic_codes": rejected.diagnostic_codes, "provenance": rejected.provenance},
            )

        failures: list[dict[str, object]] = []
        for candidate in self.planner.candidate_routes(source_version, target_version):
            attempted = self._execute_route(
                skeleton, atlas_data, texture_data, skeleton_path, candidate, source_risk_policy
            )
            if isinstance(attempted, dict):
                failures.append(attempted)
                continue
            current_skeleton, current_atlases, hop_results = attempted
            outputs = {skeleton_path: current_skeleton, **current_atlases, **texture_data}
            return AssetSetResult(
                source_version,
                target_version,
                candidate,
                skeleton_path,
                bundle.atlases,
                outputs,
                ConversionStatus.STRUCTURALLY_VERIFIED,
                details={
                    "per_hop": tuple(hop_results),
                    "rejected_routes": tuple(failures),
                    "source_risk_warnings": (
                        ("SOURCE_EXPORT_KNOWN_BUG",)
                        if source_version == "3.8.75"
                        and source_risk_policy is SourceRiskPolicy.ALLOW_WITH_DIAGNOSTIC
                        else ()
                    ),
                    "texture_sha256": {
                        name: sha256(data).hexdigest() for name, data in texture_data.items()
                    },
                    "textures_unchanged": True,
                    "structural_verification": "every_hop_and_asset_set",
                },
            )
        failed = (
            failures[0]
            if failures
            else {"reason": plan.diagnostics, "feature": "route", "asset": skeleton_path}
        )
        return AssetSetResult(
            source_version,
            target_version,
            route,
            skeleton_path,
            bundle.atlases,
            None,
            ConversionStatus.REJECTED,
            (str(failed["reason"]),),
            {"failed_hop": failed},
        )

    def _execute_route(
        self,
        skeleton: bytes,
        atlases: dict[str, bytes],
        textures: dict[str, bytes],
        skeleton_path: str,
        route: tuple[str, ...],
        source_risk_policy: SourceRiskPolicy,
    ) -> tuple[bytes, dict[str, bytes], list[dict[str, object]]] | dict[str, object]:
        current_skeleton, current_atlases = skeleton, atlases
        hop_results: list[dict[str, object]] = []
        for left, right in zip(route, route[1:]):
            result = self._convert_hop(current_skeleton, left, right, source_risk_policy)
            if result.output is None or result.status is ConversionStatus.REJECTED:
                return {
                    "source": left,
                    "target": right,
                    "asset": skeleton_path,
                    "feature": result.unsupported_features or "skeleton_migration",
                    "reason": result.diagnostics,
                }
            try:
                next_atlases = {
                    name: self.atlases.convert(data, right, source_version=left)
                    for name, data in current_atlases.items()
                }
                self._validate_stage(
                    {skeleton_path: result.output, **next_atlases, **textures}, skeleton_path
                )
            except (ValueError, UnicodeError, OSError) as exc:
                asset = exc.asset if isinstance(exc, AssetSetValidationError) else next(
                    iter(current_atlases), skeleton_path
                )
                feature = (
                    exc.feature if isinstance(exc, AssetSetValidationError)
                    else "atlas_or_cross_file_reference"
                )
                return {
                    "source": left,
                    "target": right,
                    "asset": asset,
                    "feature": feature,
                    "diagnostic_codes": (
                        exc.codes if isinstance(exc, AssetSetValidationError) else ()
                    ),
                    "reason": str(exc),
                }
            current_skeleton, current_atlases = result.output, next_atlases
            hop_results.append(
                {
                    "source": left,
                    "target": right,
                    "skeleton": "validated",
                    "atlases": len(next_atlases),
                    "texture_pages": len(textures),
                    "statistics": result.statistics,
                    "unsupported_features": result.unsupported_features,
                }
            )
        return current_skeleton, current_atlases, hop_results

    def _convert_hop(
        self,
        source: bytes,
        source_version: str,
        target_version: str,
        source_risk_policy: SourceRiskPolicy,
    ) -> ConversionResult:
        """Execute exactly one registered edge, independent of longer planner paths."""
        return self.skeletons.convert(source, target_version, source_risk_policy=source_risk_policy)

    def _validate_stage(self, files: Mapping[str, bytes], skeleton_path: str) -> None:
        """Re-run B1 dependency resolution over an isolated staged directory."""
        import tempfile

        with tempfile.TemporaryDirectory(prefix="fnx-spine-stage-") as directory:
            root = Path(directory)
            for name, data in files.items():
                target = root.joinpath(*Path(name).parts)
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes(data)
            report = self.inspection.inspect(str(root))
            staged = next(
                (item for item in report.bundles if item.bundle_id == skeleton_path), None
            )
            if staged is None or staged.validation_state != "valid":
                relevant = tuple(
                    diagnostic for diagnostic in report.diagnostics
                    if diagnostic.path == skeleton_path
                    or diagnostic.severity.value in {"error", "blocker"}
                )
                reasons = tuple(f"{item.code}: {item.message}" for item in relevant)
                failed = relevant[0] if relevant else None
                asset = failed.path if failed is not None and failed.path else skeleton_path
                feature = (
                    "skeleton_semantics"
                    if asset == skeleton_path
                    else "atlas_or_texture_reference"
                )
                raise AssetSetValidationError(
                    "Staged skeleton/atlas/texture references failed B1 validation: "
                    + ("; ".join(reasons) or "bundle unresolved"),
                    asset,
                    feature,
                    tuple(item.code for item in relevant),
                )
