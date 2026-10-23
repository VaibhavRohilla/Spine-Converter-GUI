# FNX Spine Forge B2 conversion report

## Decision

**B2 OPEN / BLOCKED.** The exact 3.8.75 to 4.2.43 structural migration is executable and passes its fixture and numerical checks. The planned 3.5, 3.6, 3.7, 4.0, 4.1, and 4.3 families remain unimplemented. The first route has not been loaded by a compatible Spine 4.2 runtime, and full 3.8 feature coverage, provider style package dependency checking, and target runtime/playback qualification remain open. No commit or freeze was made.

## A. Implemented conversion architecture

- `conversion/skeleton.py` keeps the independent `SkeletonConverter` API, reads/version-detects input, calls the route-specific transformer, re-inspects output, and reports counts and verification state.
- `conversion/migrate_38_42.py` implements the exact JSON schema transformation. It converts bone transform modes, slot color timelines, rotation values, constraint mix fields/channels, draw-order naming, deform ownership/timeline nesting, linked mesh deform inheritance, and legacy Bézier values. It validates references, attachment geometry, constraints, deform ranges, and the resulting target schema; unknown top-level or timeline groups block conversion.
- `conversion/atlas.py` keeps the independent atlas API. The explicit 3.8.75 to 4.2.43 route converts legacy `xy`/`size`/`orig`/`offset` region declarations into `bounds`/`offsets` and boolean rotation into degrees. It reparses output and compares geometry, trim offsets, original dimensions, rotation, page declarations, region ordering, and indices. Texture bytes are never written.
- `conversion/planner.py` supports an exact-patch route registration in addition to family routes. The executable cross-family pair is `3.8.75 -> 4.2.43` only.
- `cli.py` exposes the route through the existing `convert skeleton` and `convert atlas` commands. Atlas conversion requires `--source-version 3.8.75`, since atlas text has no version marker. Writes still use the existing atomic sibling-file workflow.

The field mappings were checked against the official Spine JSON documentation and official Spine TypeScript readers at the recorded runtime branch commits: [Spine JSON export format](https://esotericsoftware.com/spine-json-format), [Spine 3.8 reader source](https://github.com/EsotericSoftware/spine-runtimes/blob/8b4844bd4b193ba9e54487ed397a777993cbad56/spine-ts/core/src/SkeletonJson.ts), [Spine 3.8 animation source](https://github.com/EsotericSoftware/spine-runtimes/blob/8b4844bd4b193ba9e54487ed397a777993cbad56/spine-ts/core/src/Animation.ts), [Spine 4.2 reader source](https://github.com/EsotericSoftware/spine-runtimes/blob/e7dc1435fa4a0083ab431f1b28e083c14a1f5c68/spine-ts/spine-core/src/SkeletonJson.ts), and [Spine 4.2 animation source](https://github.com/EsotericSoftware/spine-runtimes/blob/e7dc1435fa4a0083ab431f1b28e083c14a1f5c68/spine-ts/spine-core/src/Animation.ts). In particular, Spine 4.2 curves use absolute control coordinates and separate channels; 3.8 uses normalized controls. Target time controls are `t0 + cx * (t1 - t0)`, and each target value control is `v0 + cy * (v1 - v0)`.

## B. Supported conversion routes

| Exact source | Exact target | State |
|---|---|---|
| Spine 3.8.75 JSON | Spine 4.2.43 JSON | Executable; structural verification and sampled Bézier equivalence, no runtime verification |
| Spine 3.8.75 atlas | Spine 4.2.43 atlas | Executable when caller supplies exact source version; syntax and semantic reinspection |

The 3.8-to-4.2 converter handles skeleton metadata, bone and slot references, array skins, events, draw order, regions, meshes, weighted vertex encodings, linked meshes, clipping, bounding boxes, paths, and points. It transforms rotation, translation, scale, shear, attachment, color, two-color, deform, draw-order, event, IK, transform-constraint, and path-constraint timeline structures. Unsupported or malformed constructs reject without output.

No route is registered for 3.5, 3.6, 3.7, 4.0, 4.1, or 4.3 migration. Other patch versions do not inherit support from the 3.8.75/4.2.43 qualification. Same-version serialization is still limited to exact declared-version round trips.

## C. Real asset conversion results

The source fixture was copied byte-for-byte from `SL-GoldenPavalion/assets/Main/Bonus/golden_ingot.json`, its `.atlas`, and its `.png` into `tests/fixtures/spine38/`.

- `golden_ingot.json`, declared `3.8.75`, converted to `4.2.43`; 5 bones, 8 slots, 1 skin, 2 animations, 8 region attachments, and 25 keyframes across 5 timeline instances. The route converted and sampled 42 Bézier channel segments.
- `golden_ingot.atlas`, explicitly declared by the caller as 3.8.75, converted to target bounds/offsets syntax; 1 page and 6 regions. Reparse preserved page and region ordering, indices, rotation, packed bounds, trim offsets, and original dimensions.
- The PNG fixture SHA/content remained unchanged across conversion. Skeleton conversion was deterministic across repeated calls; source JSON bytes were unchanged.
- `merged_multi.json` is a 4.2.43 reference asset, not an animation-equivalence counterpart to `golden_ingot.json`; it was not used as a paired semantic comparison.

The synthetic fixture adds coverage for linked mesh parent lookup and inheritance, clipping geometry, point attachments, constraints, deform curves, draw order, events, and mixed animation groups.

## D. Animation verification

For each converted Bézier channel, the converter decodes the legacy normalized controls and emits 4.2 absolute time/value controls. It compares both cubic representations at 257 shared normalized time samples. Across the real fixture, 42 channel segments were checked with maximum numerical error `2.731148640577885e-14`. Synthetic coverage verifies negative differences, channel defaults, and deform curve coordinate conversion. The result reports animation names, timeline counts by type, keyframe counts by type, total counts, and unsupported features.

The numerical check covers curve representation and does not execute the Spine animation runtime. Full animation playback and visual equivalence remain B4 work.

## E. Atlas conversion

Atlas conversion is bound to the exact declared 3.8.75 -> 4.2.43 route. Legacy region declarations must provide `xy` and `size`; rotation must be `true` or `false`. The output retains page attributes, region attributes outside the syntax conversion, all pages, region order, and indexed duplicates. It checks target syntax after reparse and compares converted geometry values. Texture files remain external dependencies and are not changed or copied by this standalone API; package-level attachment-to-atlas and texture existence verification remains open.

## F. Testing and executed checks

- `.venv/bin/python -m pytest -q` — 55 passed.
- `.venv/bin/ruff check src tests` — passed.
- `.venv/bin/mypy` — strict typing, 20 source files, passed.
- `.venv/bin/python -m build` — passed; sdist and wheel built.
- Installed `.venv/bin/spine-forge plan --from-version 3.8.75 --to-version 4.2.43` — executable exact route reported.
- Installed CLI skeleton conversion — structurally verified, 5 bones, 8 slots, 1 skin, 2 animations, 42 curve channel segments, maximum error `2.731148640577885e-14`, 25 keyframes across 5 timeline instances.
- Installed CLI atlas conversion — structurally verified, 1 page and 6 regions.
- Installed CLI inspection of the output bundle — `ok: true`, 1 skeleton, 1 atlas, 1 texture; direct SkeletonInfo reinspection reported target version `4.2.43`, 5 bones, 8 slots, 1 skin, 2 animations.
- Determinism, source JSON/PNG immutability, target atlas reparse, unsupported downgrade rejection, schema rejection, and Bézier sampling — covered by conversion tests.
- Official runtime source was inspected but neither compatible Spine runtime was executed. The Spine 3.8 reader branch explicitly rejects a metadata version of `3.8.75`; this converter therefore reports structural verification only. Target runtime smoke status: not run.

## G. Remaining limitations

- Implement and qualify 3.5, 3.6, 3.7, 4.0, 4.1, and 4.3 routes one at a time, including composed routes only after end-to-end verification.
- Qualify broader real 3.8 assets covering weighted/unweighted meshes, linked-mesh deform, all constraints, setup attachments, and every supported timeline family.
- Add full topology validation for every weighted attachment encoding and validate attachment paths against companion atlas regions in a package-aware flow.
- Execute output with an exact compatible Spine 4.2.43 runtime and keep runtime evidence separate from structural and numerical checks.
- Continue hostile malformed-input coverage, including downgrade cases and atlas edge cases.
- B2 matrix acceptance and freeze remain incomplete.

## H. Freeze decision

**B2 OPEN / BLOCKED.** The initial 3.8.75 -> 4.2.43 path is an implemented structural migration, not completion of the B2 route matrix and not runtime or visual certification. No commit was created; the working tree remains uncommitted.
