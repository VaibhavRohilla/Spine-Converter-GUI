"""Mypy-qualified client: public B3 application data never crosses as JSON dictionaries."""

from pathlib import Path
from typing import assert_type

from fnx_spine_forge.binary import BinaryErrorCode
from fnx_spine_forge.bundle import BundleService
from fnx_spine_forge.bundle_models import (
    BundleOutcome,
    BundleReport,
    BundleRequest,
    BundleResult,
    JobDiagnosticCode,
    PackageContainer,
    TargetInspection,
)
from fnx_spine_forge.conversion.qualification import QualificationResult


def consume_result(result: BundleResult) -> None:
    assert_type(result.report, BundleReport)
    assert_type(result.report.output, Path)
    for bundle in result.report.bundles:
        assert_type(bundle, BundleOutcome)
        assert_type(bundle.qualification, QualificationResult | None)
        if bundle.binary_encode is not None:
            assert_type(bundle.binary_encode.error, BinaryErrorCode | None)
    if result.report.diagnostic is not None:
        assert_type(result.report.diagnostic.code, JobDiagnosticCode | BinaryErrorCode)


def consume_inspection(service: BundleService, source: Path) -> None:
    inspection = service.inspect_source(source)
    for targets in inspection.targets.values():
        for target in targets.values():
            assert_type(target, TargetInspection)
            assert_type(target.qualification, QualificationResult)
    consume_result(
        service.plan_conversion(
            BundleRequest(source, "4.2.43", Path("converted"), container=PackageContainer.FOLDER)
        )
    )
