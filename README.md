# FNX Spine Forge — B1 foundation

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

`--strict` makes warnings fail with exit code 2. Unsafe or invalid source inputs and error/blocker diagnostics also return exit code 2. `plan` rejects routes until actual migration code is implemented and registered.

## Shared API

```python
from fnx_spine_forge import InspectionService

manifest = InspectionService().inspect("./assets.zip")
print(manifest.to_dict())
```

Resource limits are configured through `InspectionConfig` and `SourceLimits`. Core interfaces and contracts are documented in [`docs/architecture.md`](docs/architecture.md), [`docs/manifest-schema.md`](docs/manifest-schema.md), and [`docs/version-registry.md`](docs/version-registry.md).

The B2 conversion package includes a structural 3.8.75 to 4.2.43 JSON and atlas migration, plus conservative exact-version skeleton JSON round trips. The migration is numerically checked for supported Bézier channels and structurally reinspected; it is not runtime or visual certification. See [`docs/B2_REPORT.md`](docs/B2_REPORT.md) for the qualified route, limitations, and executed verification evidence. B1 inspection details remain in [`docs/B1_REPORT.md`](docs/B1_REPORT.md).

## Spine licensing

This repository includes no Esoteric Software runtime/editor binaries or third-party converter code. Before shipping a viewer with official Spine runtimes, review the Spine Editor and Runtimes license terms and include applicable notices.
