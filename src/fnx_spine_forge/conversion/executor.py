"""Transactional execution of registered, individually validated migrations."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, replace

from .models import ConversionResult, ConversionStatus
from .planner import ConversionPlanner
from .qualification import QualificationService, inspect_features
from .registry import KNOWN_EXPORT_ISSUE_PATCHES


@dataclass(frozen=True, slots=True)
class MigrationHopEvidence:
    source_version: str
    target_version: str
    status: str
    diagnostics: tuple[str, ...]
    diagnostic_codes: tuple[str, ...]
    structural_verification: str
    statistics: dict[str, int | float] | None


class MigrationExecutor:
    """Try shortest registered paths and publish output only after every hop passes.

    ``convert_direct`` must execute one registered route and perform its version
    specific feature checks and structural reinspection. Intermediate outputs are
    held only in memory and are never published by this class.
    """

    def __init__(
        self,
        planner: ConversionPlanner,
        convert_direct: Callable[[bytes, str], ConversionResult],
        *,
        experimental_structural: bool = False,
    ) -> None:
        self.experimental_structural = experimental_structural
        self._planner = planner
        self._convert_direct = convert_direct

    def execute(self, source: bytes, source_version: str, target_version: str) -> ConversionResult:
        from .skeleton import SkeletonConverter

        if not self.experimental_structural:
            try:
                canonical = SkeletonConverter().read(source, migration_target=target_version)
            except (ValueError, UnicodeError) as exc:
                return ConversionResult(
                    source_version, target_version, (), None, ConversionStatus.REJECTED, (str(exc),)
                )
            if canonical.version != source_version:
                return ConversionResult(
                    source_version,
                    target_version,
                    (),
                    None,
                    ConversionStatus.REJECTED,
                    ("Declared source version does not match input",),
                    diagnostic_codes=("QUALIFICATION_PATH_INVALID",),
                )
            if source_version in KNOWN_EXPORT_ISSUE_PATCHES:
                return ConversionResult(
                    source_version,
                    target_version,
                    (),
                    None,
                    ConversionStatus.REJECTED,
                    ("Known source export risk requires explicit policy",),
                    diagnostic_codes=("SOURCE_EXPORT_KNOWN_BUG",),
                )
            path = self._planner.structural_plan(source_version, target_version).route
            q = QualificationService().evaluate(
                source_version,
                target_version,
                path,
                inspect_features(canonical.semantic, canonical.document),
            )
            if not q.qualified:
                return ConversionResult(
                    source_version,
                    target_version,
                    path,
                    None,
                    ConversionStatus.REJECTED,
                    q.missing_evidence,
                    details={"experimental_structural": False},
                    qualification=q,
                    diagnostic_codes=tuple(q.diagnostic_codes),
                )
        result = self._execute_structural(source, source_version, target_version)
        if result.output is None:
            return result
        canonical = SkeletonConverter().read(source, migration_target=target_version)
        q = QualificationService().evaluate(
            source_version,
            target_version,
            result.route,
            inspect_features(canonical.semantic, canonical.document),
            experimental_structural=self.experimental_structural,
        )
        details = dict(result.details or {})
        details["experimental_structural"] = self.experimental_structural
        if not q.qualified and not self.experimental_structural:
            return replace(
                result,
                output=None,
                status=ConversionStatus.REJECTED,
                diagnostics=q.missing_evidence,
                diagnostic_codes=tuple(q.diagnostic_codes),
                details=details,
                qualification=q,
            )
        return replace(
            result,
            details=details,
            qualification=q,
        )

    def _execute_structural(
        self, source: bytes, source_version: str, target_version: str
    ) -> ConversionResult:
        candidates = self._planner.candidate_routes(source_version, target_version)
        if not candidates:
            planned = self._planner.structural_plan(source_version, target_version)
            return ConversionResult(
                source_version,
                target_version,
                planned.route,
                None,
                ConversionStatus.REJECTED,
                planned.diagnostics,
            )

        failures: list[tuple[str, ...]] = []
        evidence_by_route: list[tuple[MigrationHopEvidence, ...]] = []
        for route in candidates:
            current = source
            hop_evidence: list[MigrationHopEvidence] = []
            failed = False
            for left, right in zip(route, route[1:]):
                result = self._convert_direct(current, right)
                hop_evidence.append(
                    MigrationHopEvidence(
                        left,
                        right,
                        result.status.value,
                        result.diagnostics,
                        result.diagnostic_codes,
                        "passed" if result.output is not None else "failed",
                        result.statistics,
                    )
                )
                if result.output is None or result.status is ConversionStatus.REJECTED:
                    failures.append(
                        result.diagnostics or (f"Migration hop {left} -> {right} failed",)
                    )
                    evidence_by_route.append(tuple(hop_evidence))
                    failed = True
                    break
                current = result.output
            if failed:
                continue
            return ConversionResult(
                source_version,
                target_version,
                route,
                current,
                ConversionStatus.STRUCTURALLY_VERIFIED,
                details={
                    "structural_verification": "every_hop_passed",
                    "hop_evidence": [
                        {
                            "source_version": hop.source_version,
                            "target_version": hop.target_version,
                            "status": hop.status,
                            "diagnostics": hop.diagnostics,
                            "diagnostic_codes": hop.diagnostic_codes,
                            "structural_verification": hop.structural_verification,
                            "statistics": hop.statistics,
                        }
                        for hop in hop_evidence
                    ],
                    "failed_candidates": len(failures),
                },
                diagnostics=tuple(
                    diagnostic for hop in hop_evidence for diagnostic in hop.diagnostics
                ),
            )

        best_evidence = evidence_by_route[0] if evidence_by_route else ()
        first_failure = (
            failures[0] if failures else ("No feature-compatible route passed validation",)
        )
        return ConversionResult(
            source_version,
            target_version,
            candidates[0],
            None,
            ConversionStatus.REJECTED,
            first_failure,
            details={
                "failed_hop": (
                    {
                        "source_version": best_evidence[-1].source_version,
                        "target_version": best_evidence[-1].target_version,
                        "diagnostics": best_evidence[-1].diagnostics,
                        "diagnostic_codes": best_evidence[-1].diagnostic_codes,
                    }
                    if best_evidence
                    else None
                ),
                "hop_evidence": [
                    {
                        "source_version": hop.source_version,
                        "target_version": hop.target_version,
                        "status": hop.status,
                        "diagnostics": hop.diagnostics,
                        "diagnostic_codes": hop.diagnostic_codes,
                        "structural_verification": hop.structural_verification,
                        "statistics": hop.statistics,
                    }
                    for hop in best_evidence
                ],
            },
        )
