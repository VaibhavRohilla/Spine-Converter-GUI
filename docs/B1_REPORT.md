# FNX Spine Forge B1 verification report

## Status

B1 foundation is implemented and locally verified. This is an inspection result only; conversion and runtime certification remain unimplemented.

## Public contracts

- `AssetManifest`, `Asset`, `SpineBundle`, `Dependency`, `Diagnostic`, `Severity`, and `FileType` are immutable dataclasses. Nested metadata, diagnostic context, and summary mappings are frozen; `AssetManifest.to_dict()` emits JSON-compatible deterministic values.
- `InspectionService.inspect(origin)` is the common folder/ZIP pipeline. Pass an `InspectionConfig` for JSON limits and `SourceLimits` for member count, per-member and total compressed/uncompressed bytes, compression ratio, and bounded read limits.
- `VersionRegistry` recognizes Spine 3.5–3.8 and 4.0–4.3. `CompatibilityRegistry` explicitly reports feature capability as not implemented. `MigrationRegistry` remains empty by default.
- `parse_atlas(bytes)` returns `AtlasInfo`, including page and region records with their associated attributes and unknown fields.
- `inspect_skeleton(bytes)` returns structural version/name/count/attachment data for recognized JSON exports and does not rewrite them.
- `DependencyResolver` is independently callable and reports an unresolved ambiguous match rather than choosing an arbitrary file. Exact skeleton/atlas stems only disambiguate after attachment-region evidence.
- `protocols.py` defines UI-independent inspector and atlas-parser service protocols.

## Verification environment

- Python 3.12.15 from `/opt/homebrew/bin/python3.12`; isolated environment at `.venv`.
- Installed project development extra: pytest, Ruff, mypy, and build.
- `PYTHONPYCACHEPREFIX` was set to the workspace `.pycache` directory for bytecode compilation.

## Executed checks

- `.venv/bin/python -m pip install -e '.[dev]'` — passed; editable package and console entry points installed.
- `.venv/bin/python -m pytest -q` — **40 passed**.
- `.venv/bin/ruff check src tests` — passed.
- `.venv/bin/mypy` — passed, strict configuration; 14 source files checked.
- `PYTHONPYCACHEPREFIX="$PWD/.pycache" .venv/bin/python -m compileall -q src tests` — passed.
- `.venv/bin/python -m build` — sdist and wheel built successfully without license metadata warnings.
- The installed `.venv/bin/spine-forge` executable was exercised by automated integration tests on equivalent folder and ZIP fixtures and returned JSON manifests; missing input returned exit code 2. `spine-forge versions` listed all configured families.

Security tests cover ZIP traversal (file and normalized path), duplicate normalized paths, symlink members, corrupt ZIPs, member count, per-member and aggregate compressed/uncompressed size limits, compression ratio, folder symlinks, read limits, bounded JSON inspection, and input immutability. Inspection continues to report safely discoverable assets after a file read error.

## Real asset inspection

Inspections were read-only and used the installed CLI/API against existing workspace assets:

- Golden Pavilion Bonus: 12 assets, two skeletons (3.8.75 and 4.2.43), two atlases, three resolved texture-page dependencies, zero diagnostics. Fire Cracker JSON reported 57 image attachments.
- Golden Pavilion `merged_multi`: 15 assets, one 4.2.43 skeleton, one atlas, two resolved page references, zero diagnostics; 18 animations and 40 image attachments reported.
- Golden Pavilion Wild/Expanding Wild: eight assets, three 4.2.43 skeletons, three atlases, three page references, zero diagnostics; each skeleton matched its atlas using attachment regions and exact stem tie-break evidence.
- GCT asset directory: 77 files were discoverable, but no Spine JSON skeleton or `.atlas` export was present in that directory; no GCT Spine parsing claim is made.

## Remaining limits

- Structural inspection does not decode Spine binary `.skel`; its version is returned as unknown.
- Texture bytes are not decoded or validated as images.
- JSON structure inspection does not validate complete animation semantics, runtime loadability, visual fidelity, or conversion safety.
- Version schemas beyond the tested 3.x and 4.x examples are recognized only where registered; unknown future families remain visible as unsupported.
- Atlas page declarations are identified by supported image filename suffixes. Unusual custom atlas syntax may require a future explicit grammar extension.
- The source repository has no `.git` directory, so no commit SHA or Git working-tree status is available.
