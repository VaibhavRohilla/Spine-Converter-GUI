# FNX Spine Forge

FNX Spine Forge provides headless inspection, qualification-gated JSON/atlas
migration, and atomic bundle packaging. Service models are strongly typed and
independent of desktop UI frameworks. Recognition, implementation support,
semantic qualification and runtime/visual evidence are separate contracts.

Version 0.2 is the B3 contract cutover. Binary support remains restricted to an
experimental, unqualified 4.2.43 hierarchy codec; full B3 binary acceptance is
still open. Current evidence and limitations are in
[the hardening report](docs/B3_HARDENING_REPORT.md).

## Development

Python 3.11 or newer is required. A Python 3.12 development setup:

```bash
python3.12 -m venv .venv
.venv/bin/python -m pip install -e '.[dev]'
.venv/bin/pytest
.venv/bin/ruff check src tests
.venv/bin/mypy
```

## CLI

```bash
spine-forge inspect ./assets.zip
spine-forge inspect ./assets --json
spine-forge inspect ./assets --strict
spine-forge versions
spine-forge plan --from-version 3.8.75 --to-version 4.2.43
```

`--strict` makes warnings fail with exit code 2. Unsafe or invalid source inputs and error/blocker diagnostics also return exit code 2. `plan` reports candidate paths and rejects qualified execution without inspected source features. Implementation connectivity alone is not qualification.

## Shared API

```python
from fnx_spine_forge import InspectionService

manifest = InspectionService().inspect("./assets.zip")
print(manifest.to_dict())
```

Resource limits are configured through `InspectionConfig` and `SourceLimits`. Core interfaces and contracts are documented in [`docs/architecture.md`](docs/architecture.md), [`docs/manifest-schema.md`](docs/manifest-schema.md), and [`docs/version-registry.md`](docs/version-registry.md).

The B2 conversion package provides exact-patch migration writers with central
route/feature qualification. Default execution accepts only the recorded
hierarchy/setup subset on seven direct 3.8.99 routes. Attachments, animation,
composed routes and complete asset sets require explicit experimental structural
opt-in and remain unqualified. The separate known 3.8.75 export-risk allowance
remains mandatory for that source.

```python
from fnx_spine_forge.conversion import SkeletonConverter

result = SkeletonConverter().convert("source.json", "4.2.43")
if result.qualification is not None:
    print(result.qualification.to_json())
```

```bash
spine-forge convert skeleton --input source.json --target 4.2.43 --output target.json
# Explicitly unqualified structural experiment on the known-risk source:
spine-forge convert-asset-set --input ./assets --skeleton golden_ingot.json \
  --target 4.2.43 --output-dir ./converted \
  --experimental-structural --allow-known-source-export-risk
```

Qualification records are loaded from packaged, validated evidence data.
Historical Spine writers remain active supported functionality. The retired
family-only graph, unused protocol/error scaffolding and duplicate parsers and
publishers are removed. There are no compatibility modules for removed symbols.

Strict mypy rejects explicit/implicit `Any` and missing imports. The distribution
ships `py.typed`, and an independent typed client checks its public contracts.
Existing B2 qualifications remain unchanged; see [B2_REPORT.md](docs/B2_REPORT.md).

## Spine licensing

This repository includes no Esoteric Software runtime/editor binaries or third-party converter code. Before shipping a viewer with official Spine runtimes, review the Spine Editor and Runtimes license terms and include applicable notices.

## B3 headless bundle API

`fnx_spine_forge.bundle.BundleService` is the shared entry point for CLI and
future viewer/UI integrations. It accepts folders, bounded ZIPs and explicit
`tuple[Path, ...]` selections. `inspect_source` exposes B1 manifests, logical
bundle states, mapping decisions, source risks and per-target B2 qualification.
`plan_conversion` performs an isolated conversion rehearsal without publishing.
`convert_bundle` publishes a validated ZIP or folder, and `convert_batch`
returns an independent result for every request. See [B3_REPORT.md](docs/B3_REPORT.md)
for the original checkpoint; [B3_HARDENING_REPORT.md](docs/B3_HARDENING_REPORT.md)
documents the current schema-2 API.

```python
from pathlib import Path
from fnx_spine_forge.bundle import BundleService
from fnx_spine_forge.bundle_models import BundleRequest, PackageContainer
from fnx_spine_forge.progress import CancellationToken

service = BundleService()
inspection = service.inspect_source(Path("assets.zip"))
request = BundleRequest(Path("assets.zip"), "4.2.43", Path("converted.zip"),
                        container=PackageContainer.ZIP)
plan = service.plan_conversion(request)
result = service.convert_bundle(request, cancellation=CancellationToken())
```

Qualified mode remains the default and enforces B2's frozen feature restrictions.
A complete atlas bundle currently requires experimental structural authorization
because atlas geometry is outside RC1 semantic evidence. Known 3.8.75 source risk
requires a separate authorization. Neither flag certifies runtime or visual fidelity.

```
spine-forge bundle inspect assets.zip
spine-forge bundle list assets.zip
spine-forge bundle plan --input assets.zip --target 4.2.43
spine-forge bundle convert --input assets.zip --target 4.2.43 \
  --container zip --output converted.zip
spine-forge binary-capabilities
```

Use `--experimental-structural` only to explicitly authorize unqualified output;
`--allow-known-source-export-risk` is separate. `--bundle-id` is repeatable.
`--skeleton-format binary` exposes only the implemented experimental 4.2.43
hierarchy codec; attachments, slots, constraints and animations are rejected.
`--retention all` preserves unrelated files. Excluded paths are always reported.
Viewer mode adds no report member. Audit mode embeds a prepublication validation
snapshot. `--report-output report.json` explicitly exports the final result as a
sidecar, with its own atomic no-overwrite publication; sidecar failure never
undoes a valid package. ZIP/folder publication is atomic per request, including
all selected bundles; separate batch requests publish independently.

### Typed contract and policy configuration

Import service orchestration from `fnx_spine_forge.bundle` and domain contracts
from `fnx_spine_forge.bundle_models`. `BundleResult.report` is an immutable
`BundleReport`; access named fields such as `result.report.bundles` and
`result.report.output`. Call `to_dict()` only at a JSON boundary. Report and
inspection schema 2 have no dictionary-access adapters or legacy import aliases.

The output container is an explicit `PackageContainer`. A folder can have any
name, including a `.zip` suffix; names no longer choose service behavior.
CLI conversion requires `--container zip` or `--container folder`.
`InspectionConfig` owns source and binary resource limits. `PackageSettings`
owns ZIP compression and `TextureLimits`. All stages consume these same policy
objects. Fixed wire constants remain fixed format facts, not user configuration.

PNG validation bounds file/chunk/pixel/decoded sizes and checks CRC, DEFLATE,
scanlines and Adam7 structure. Atlas-declared PNG sizes must match measured
headers. Validation never crops, resizes or re-encodes the authored textures.

Standalone CLI output is exclusive as well: existing files are rejected rather
than replaced. Nonessential binary metadata must provide explicit FPS, bone
color and visibility when enabled; metadata defaults are not inferred from a
different JSON/editor/runtime contract.
