# FNX Spine Forge

FNX Spine Forge provides a read-only, headless inspection API for Spine export folders and ZIP archives. The same typed inspection service is intended for the CLI and later desktop workflows.

B1 discovers skeleton JSON, binary skeleton files, atlases, textures, and other files; inspects skeleton structure and atlas pages/regions; resolves dependencies; recognizes Spine version families; and returns a deterministic JSON manifest. Inspection is structural. It does not convert assets, decode full binary skeletons, load a Spine runtime, or certify animation fidelity.

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

Qualification records are loaded from packaged, validated evidence data. Python
results expose `qualification: QualificationResult | None`; CLI reports use the
same top-level field. The superseded `SemanticQualification` enum,
`feature_compatibility` maps, `InspectionReport` alias, internal
`conversion.json_types` module and version-specific runtime forwarders have been
removed. No compatibility aliases are provided. JSON types now live in
`fnx_spine_forge.json_types`; runtime probes use `run_spine_runtime_smoke`.

Strict mypy rejects explicit and implicit `Any` across production code and the
independent numerical test reader. See [B2_REPORT.md](docs/B2_REPORT.md) for the
restricted matrix and executed evidence. Runtime and visual certification remain
unverified. B1 inspection evidence remains in [B1_REPORT.md](docs/B1_REPORT.md).

## Spine licensing

This repository includes no Esoteric Software runtime/editor binaries or third-party converter code. Before shipping a viewer with official Spine runtimes, review the Spine Editor and Runtimes license terms and include applicable notices.
