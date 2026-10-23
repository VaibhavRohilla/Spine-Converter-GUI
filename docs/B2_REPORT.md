# FNX Spine Forge B2 conversion report

## Final implementation pass — 2026-10-23

This status update records work performed against the live branch and supersedes
older completion claims wherever they conflict. Prior route evidence remains
scoped to the specific assets and tests cited below.

### A. Architecture

- Added a direct exact-patch 4.0.31→3.8.99 writer. It retains setup hierarchy,
  named skin records, and compatible attachments; converts linked-mesh
  `timelines` to `deform`; and converts attachment-nested deform timelines to
  the older deform group.
- The writer rejects attachment sequences, skin-scoped bones/constraints,
  non-deform attachment timelines, malformed source structures, and 4.0
  per-channel Bézier arrays. Spine 3.8's shared normalized curve can represent
  those only if every channel has mathematically identical normalized easing.
  The current writer does not have typed per-timeline endpoints to establish
  this; it emits `incompatible_per_channel_bezier_curves` rather than guessing.
  No curve segments were converted on this route, so it has no numerical curve
  equivalence samples to report.
- `ConversionPlanner` searches deterministic paths over registered exact-patch
  edges and exposes candidate intermediate versions. It marks multi-hop paths
  non-executable until end-to-end semantic qualification exists. Actual
  multi-hop conversion, per-hop validation, feature-capability admission,
  diagnostics aggregation, and transactional composition remain unimplemented.
- Atlas conversion accepts 4.0.31→3.8.99 and reparses its serialized output.
  Existing direct 3.8 routes remain in place.

### B. Compatibility matrix

Legend: **D** direct route registered for a documented subset; **R** direct
route with explicit blocking restrictions; **I** exact-version identity only;
**N** no direct route. A registered route is not a composed conversion claim.

| Source \\ Target | 3.5 | 3.6 | 3.7 | 3.8 | 4.0 | 4.1 | 4.2 | 4.3 |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| 3.5.51 | I | D | N | N | N | N | N | N |
| 3.6.53 | D | I | D | N | N | N | N | N |
| 3.7.94 | N | D | I | D | N | N | N | N |
| 3.8.75 / 3.8.99 | D | D | D | I | D | D | D | D |
| 4.0.31 | N | N | N | R | I | D | N | N |
| 4.1.56 | N | N | N | N | D | I | D | N |
| 4.2.43 | N | N | N | N | N | D | I | D |
| 4.3.13 | N | N | N | N | N | N | D | I |

This classifies all 56 ordered distinct family pairs by direct registration;
it does not qualify every pair end to end. 3.8.75 and 3.8.99 retain separate
exact source policies. No other 3.8 patch inherits their routes. The new
4.0.31→3.8.99 route is restricted to timelines without per-channel Bézier
curves and other unsupported 4.0-only features. All non-direct pairs remain
not implemented as composed conversions, even if edges form a graph path.

### C. Route execution

- Added tests for a representable no-curve 4.0.31→3.8.99 skeleton, a
  per-channel Bézier rejection with feature diagnostics, and display of an
  unqualified composed path as non-executable.
- Existing direct 3.8 routes were not replaced. The requested composed
  examples (3.5→4.3, 3.6→4.2, 3.7→4.1, 4.3→3.8, 4.2→3.6, and 4.1→3.5) were
  not run as conversions; any planner candidate is non-executable.
- Installed CLI plan for 4.0.31→3.8.99 returned its direct route.
- Installed CLI conversion of the real 3.8.75 fixture to 4.2.43 correctly
  refused by default with `SOURCE_EXPORT_KNOWN_BUG`, retaining the declared
  source patch.

### D. Runtime evidence

No runtime was run in this final pass. The earlier recorded exact 4.0.31,
4.1.56, 4.2.43, and 4.3.13 runtime smoke evidence remains limited to those
specific routes/assets and checks. Historical 3.5.51, 3.6.53, and 3.7.94
runtimes were not qualified. Runtime parsing, animation-state evaluation, and
visual equivalence remain separate claims.

### E. Asset fidelity

`spine-forge inspect tests/fixtures/spine38 --json` passed B1 inspection: one
3.8.75 skeleton, one atlas, one texture, with skeleton-to-atlas and
atlas-to-PNG references resolved. The authentic 3.8.99 fixture remains
unavailable; no metadata relabeling was used. No visual-frame comparison was
performed. The new route regression uses a minimal synthetic skeleton, not a
real export.

### F. Testing

- `.venv/bin/python -m pytest -q` — **99 passed**.
- `.venv/bin/ruff check src tests` — **passed**.
- `.venv/bin/mypy` — **passed**, 34 source files.
- `.venv/bin/python -m build` — **passed**, sdist and wheel.
- Installed CLI planning and B1 real fixture folder inspection — **passed**.
- Installed CLI conversion of the 3.8.75 real fixture — **correctly rejected**
  by source-risk policy.
- The new route converted zero Bézier segments; no numerical error or sample
  count is claimed for it. Existing numerical evidence remains limited to the
  previously documented routes.

### G. Remaining work and freeze decision

- Implement actual multi-hop conversion with semantic capability checks,
  per-hop revalidation, aggregated diagnostics, and transactional output.
- Qualify advertised subsets across every ordered family pair; current matrix
  records direct registration and non-implementation only.
- Support 4.0 per-channel to 3.8 shared curves only after proving normalized
  channel equivalence and adding numerical sample checks.
- Add composed-route positive/negative fixtures, archive conversion and
  reinspection, and determinism/source-immutability evidence for composition.
- Obtain authentic 3.8.99 and expanded 3.8 fixtures; qualify exact historical
  3.x runtimes if tooling and license permit.
- Runtime-qualify the new 4.0.31→3.8.99 supported subset.

**B2 OPEN / BLOCKED.** Existing direct routes remain intact and the restricted
4.0.31→3.8.99 route is implemented. Graph route discovery is present, but
composed execution and cross-version qualification are not complete. No freeze
or universal lossless downgrade capability is claimed.

### H. Git for this pass

- Starting branch: `codex/b2-conversion-engine`.
- Starting HEAD: `505f800a99890a32da690d8e24d82d8fe624a12f`.
- Starting worktree: clean.
- Implementation checkpoint: `685c0b2176516615deb80cc9387cf9aa03e7218d`.
- Branch after checkpoint: `codex/b2-conversion-engine`.
- Worktree after checkpoint: clean. The report records the implementation
  checkpoint; its documentation-only follow-up commit is the final HEAD.

## Decision

**B2 OPEN / BLOCKED.** Exact 3.8.75 and 3.8.99 sources have executable routes to all seven requested target patches. Five adjacent directed historical 3.x edges and six adjacent 4.x edges have tested supported subsets, but cross-family composition and other non-adjacent routes remain incomplete. Exact 4.x runtimes passed the previously recorded forward routes; newly added downgrade edges have structural/B1 verification without runtime qualification. The authentic 3.8.99 fixture is unavailable. No full any-version matrix or freeze is claimed.

## A. Architecture

- `conversion/skeleton.py` owns the independent Python converter API, exact source/target route gate, source risk handling, structural reinspection, deterministic JSON output, statistics, and structured diagnostics.
- `conversion/migrate_38_to_legacy.py` migrates 3.8 skin arrays to 3.5/3.6/3.7 object-map skins. Its exact target profiles are 3.5.51, 3.6.53, and 3.7.94. It validates source structure, references, linked-mesh parents, geometry, constraints, deform ranges, timeline types, and legacy Bézier controls. It rejects skin-scoped bones or constraints and IK softness that the legacy readers cannot represent.
- `conversion/migrate_37_to_38.py` converts exact 3.7.94 object-map skins directly to 3.8.99 named skin records, retaining supported legacy timelines and blocking unknown groups.
- `conversion/migrate_36_to_37.py` converts exact 3.6.53 to 3.7.94 directly. Both use legacy skin/timeline layouts; the 3.7 writer explicitly adds its new IK constraint and animation flags as `false`, matching the official 3.7 reader defaults. Newer IK fields in a declared 3.6 source block.
- `conversion/migrate_35_to_36.py` converts exact 3.5.51 to 3.6.53 and rounds event keyframe times to IEEE single precision, matching the target reader's `toSinglePrecision` behavior. It preserves other legacy animation and skin data, validates event times and Bézier controls, and reports event-frame and curve metrics.
- `conversion/migrate_37_to_36.py` removes only false 3.7 IK flags and default audio event fields. Enabled IK compress/stretch/uniform behavior, audio paths, and non-default audio values block the downgrade.
- `conversion/migrate_36_to_35.py` preserves the 3.6 loader's single-precision event time by writing its exact float32 value into the 3.5 JSON output.
- `conversion/migrate_38_to_4x.py` writes target-specific 4.x schemas for 4.0.31, 4.1.56, 4.2.43, and 4.3.13. It validates attachment geometry and references, constraints, deform ranges, target fields, animation groups, and curve controls. The 4.3 writer supports IK and path constraints in the combined ordered constraint list; unsupported transform constraints and legacy uniform IK are blocking.
- `conversion/migrate_40_to_41.py` independently migrates exact 4.0.31 JSON to 4.1.56. It changes linked-mesh `deform` to `timelines` and moves the 4.0 deform animation group under the 4.1 attachment timeline schema while preserving supported curves.
- `conversion/migrate_41_to_42.py` independently migrates exact 4.1.56 JSON to 4.2.43. It converts bone `transform` modes to `inherit`, preserves supported 4.1 constraint/timeline curves, validates source fields, and rejects 4.2-only bone state in a declared 4.1 source.
- `conversion/migrate_42_to_43.py` independently migrates exact 4.2.43 JSON to 4.3.13. It preserves 4.2 per-channel Bézier controls, transforms linked-mesh `parent` to 4.3 `source`, and combines supported root IK/path definitions into the ordered 4.3 `constraints` array. Transform constraints and legacy uniform IK reject explicitly.
- `conversion/migrate_43_to_42.py` directly downgrades representable 4.3.13 data: ordered IK/path constraints return to 4.2 collections, linked-mesh `source` becomes `parent`, and supported curve and atlas data retain their schema. It blocks 4.3 sequences, bone icons, slot visibility, transform/physics/slider constraints, unsupported IK scale modes, and 4.3-only timelines.
- `conversion/migrate_42_to_41.py` directly downgrades representable 4.2.43 data by restoring bone `inherit` to `transform`. It removes only default `referenceScale`, visible slot flags, and false skin flags; non-default reference scale, hidden slots, physics, skin-scoped constraints/bones, and inherit timelines block.
- `conversion/migrate_41_to_40.py` reverses the linked-mesh and deform timeline schema for 4.1.56→4.0.31: `timelines` becomes `deform`, and attachment-nested deform frames return to the 4.0 `deform` group. Attachment sequences and non-deform attachment timelines block.
- `conversion/atlas.py` independently transforms atlas text and verifies parsed page/region semantics. Legacy targets retain the source 3.8 atlas field encoding; 4.2/4.3 targets use bounds/offsets and degree rotation. Texture bytes are never rewritten.
- `conversion/planner.py` and `cli.py` expose only exact registered routes. Other recognized families do not imply conversion support. Atomic writes and B1 inspection contracts are retained.
- `conversion/runtime.py`, `runtime_smoke.mjs`, and `runtime_extension_loader.mjs` load and evaluate converted bundles only with exact caller-supplied official 4.x runtime packages. Runtime parsing, animation evaluation, and visual equivalence remain separate statuses.

The legacy mappings were checked against the official [Spine 3.5](https://github.com/EsotericSoftware/spine-runtimes/blob/3.5/spine-ts/core/src/SkeletonJson.ts), [3.6](https://github.com/EsotericSoftware/spine-runtimes/blob/3.6/spine-ts/core/src/SkeletonJson.ts), and [3.7](https://github.com/EsotericSoftware/spine-runtimes/blob/3.7/spine-ts/core/src/SkeletonJson.ts) readers; the 4.x mappings were checked against their corresponding official readers. Official release listings identify the exact older patch targets [3.5.51, 3.6.53, and 3.7.94](https://us.esotericsoftware.com/spine-skeleton-viewer). The historical loaders share the object-map skin and normalized curve encoding; the writer records the exact target patch and does not advertise a runtime result without execution.

The 3.6→3.7 schema delta was inspected in those versioned readers: 3.7 adds IK `compress`, `stretch`, and `uniform`, plus optional audio event data. For tested 3.6 input, absent IK flags are semantically false in 3.7; the migration writes them explicitly. Existing event definitions and event timelines are preserved unchanged. 3.6 and 3.7 atlas fields remain semantically identical and are parsed/re-emitted without changing texture content.

The 3.5→3.6 reader comparison showed event timeline construction changed to round event times to single precision. The migration performs that exact rounding before output; other tested timeline values remain unchanged. The synthetic route test compares 257 samples of its preserved legacy Bézier segment. Atlas page and region encoding are the same for this route; complete bundle inspection verifies the referenced region and unchanged PNG.

## B. Exact 3.8 route matrix

Each row applies separately to source `3.8.75` and `3.8.99`. No other 3.8 patch inherits route qualification.

| Target | Schema transformation | Verification status |
|---|---|---|
| 3.5.51 | Skin array to legacy object-map; legacy timeline encoding retained | Structural, route-specific tests, atlas dependency tests; runtime not executed |
| 3.6.53 | Skin array to legacy object-map; legacy timeline encoding retained | Structural, route-specific tests, atlas dependency tests; runtime not executed |
| 3.7.94 | Skin array to legacy object-map; legacy timeline encoding retained | Structural, route-specific tests, atlas dependency tests; runtime not executed |
| 4.0.31 | Target-specific transform, linked-mesh, deform, constraints, and curve schema | Structural tests; exact 4.0.31 runtime parsed and evaluated the real 3.8.75 asset |
| 4.1.56 | Target-specific transform, linked-mesh and deform schema | Structural tests; exact 4.1.56 runtime parsed and evaluated the real 3.8.75 asset |
| 4.2.43 | `inherit`, linked-mesh timelines, nested deform, absolute per-channel Bézier controls, atlas bounds/offsets | Structural and sampled numerical tests; exact 4.2.43 runtime parsed and evaluated the real 3.8.75 asset |
| 4.3.13 | Combined ordered constraints, linked-mesh `source`, target atlas encoding; transform constraints and uniform legacy IK blocked | Structural tests; exact 4.3.13 runtime parsed and evaluated the real 3.8.75 asset; synthetic IK/path runtime evaluation passed |

All routes are registered independently for source patches `3.8.75` and `3.8.99` (14 exact skeleton routes). Historical targets are limited to constructs verified by their loaders. Unknown or malformed schemas reject. Lossy mode is not implemented.

Feature coverage for the 3.8 routes:

| Construct group | 3.5.51 / 3.6.53 / 3.7.94 | 4.0.31 / 4.1.56 / 4.2.43 | 4.3.13 |
|---|---|---|---|
| Skeleton, hierarchy, slots, setup bindings, events, draw order | Supported; legacy skin-map rewrite | Supported; target schemas validated | Supported; target schemas validated |
| Region, mesh, weighted/linked mesh, clipping, bounding box, path, point | Supported by matching legacy reader; geometry and parent checks | Supported; geometry, UV, weight, link, and path checks | Supported; linked source rewrite and geometry/reference checks |
| Rotation, translation, scale, shear, slot attachment/color/two-color, deform, draw order, events | Legacy timelines preserved; 257-sample curve equality | Converted to target timeline layouts and channel curves; numerical check | Converted to target timeline layouts and channel curves; numerical check |
| IK and path constraints/timelines | Supported when representable; references validated | Supported; fields and timelines transformed | Supported and runtime-smoked for IK/path; ordered combined target list |
| Transform constraints/timelines | Supported; legacy fields preserved | Supported; target fields transformed | Unsupported and blocking |
| Skin-scoped bones/constraints, IK softness, unknown timeline groups | Unsupported and blocking | Unsupported and blocking | Unsupported and blocking |
| Verification | Structural and B1 dependency only; runtime not executed | Structural; real fixture load/evaluation in exact runtime for 4.0/4.1/4.2 | Structural; real fixture load/evaluation in exact runtime; transform and uniform IK blocked |

Independent general routes currently registered:

| Exact source | Exact target | Schema changes | Verification |
|---|---|---|---|
| 4.2.43 | 4.3.13 | Root IK/path arrays become ordered typed constraints; linked-mesh `parent` becomes `source`; 4.2 channel curves remain unchanged | Structural, atlas, B1 dependency, and exact 4.3.13 runtime tests passed; 8 animation samples |
| 4.1.56 | 4.2.43 | Bone `transform` modes become `inherit`; 4.1 atlas `xy`/`size` becomes 4.2 bounds/offsets; animation channel controls stay unchanged | Structural, 257-sample curve equivalence, atlas, B1 dependency, and exact 4.2.43 runtime tests passed; 8 animation samples |
| 4.0.31 | 4.1.56 | Linked-mesh deform flag becomes timelines flag; deform group becomes attachment-nested deform timeline | Structural synthetic deform/linked-mesh tests, atlas, B1 dependency, and exact 4.1.56 runtime tests passed; 8 animation samples |
| 3.7.94 | 3.8.99 | Legacy object-map skins become named skin records; normalized timelines remain in legacy representation | Synthetic structural and atlas tests plus complete B1 dependency inspection passed; target runtime not executed |
| 3.6.53 | 3.7.94 | Preserves legacy skin/timeline forms; adds 3.7 false defaults for IK constraint and IK timeline options | Synthetic route tests, deterministic conversion, atlas conversion, and full B1 bundle/texture dependency inspection passed; historical runtime not executed |
| 3.5.51 | 3.6.53 | Rounds event timeline times to target single precision; retains legacy skin and timeline schemas | Synthetic route tests, 257-sample legacy Bézier equality, deterministic conversion, atlas conversion, and full B1 bundle/texture dependency inspection passed; historical runtime not executed |
| 3.7.94 | 3.6.53 | Removes false 3.7 IK defaults and default audio fields; enabled 3.7-only behavior blocks | Positive/default and unsupported-feature tests; 257-sample normalized Bézier equality; full B1 atlas/texture dependency inspection passed; historical runtime not executed |
| 3.6.53 | 3.5.51 | Writes event keyframe times as the source 3.6 runtime's exact single-precision values | Float32 event-time equivalence, 257-sample normalized Bézier equality, deterministic conversion, and full B1 atlas/texture dependency inspection passed; historical runtime not executed |
| 4.3.13 | 4.2.43 | Ordered supported IK/path constraints return to 4.2 arrays; linked `source` returns to `parent`; unsupported 4.3-only features block | Synthetic constraint/linked-mesh downgrade and negative tests; real golden fixture 4.2→4.3→4.2 bundle reinspection passed; CLI conversion passed; exact 4.2 runtime was not executed for this route |
| 4.2.43 | 4.1.56 | Bone `inherit` returns to `transform`; atlas bounds/offsets return to `xy`/`size`/`orig`/`offset`; nonrepresentable 4.2 additions block | 257-sample preserved curve test; hidden-slot, physics, inherit-timeline and 180-degree atlas negative cases; real golden bundle 4.1→4.2→4.1 B1 reinspection passed; exact 4.1 runtime not executed for downgrade |
| 4.1.56 | 4.0.31 | Linked-mesh `timelines` returns to `deform`; attachment-nested deform timelines return to 4.0 deform group | Synthetic linked-mesh/deform curve checks and sequence negative test; real golden bundle 4.0→4.1→4.0 B1 reinspection passed; runtime not executed for downgrade |

## C. Spine 3.8.75 risk policy

Spine maintainers acknowledge defective 3.8.75 exports and state that official 3.8 runtimes reject that exact version ([issue 2428](https://github.com/EsotericSoftware/spine-runtimes/issues/2428)). The cited evidence does not enumerate affected constructs; the converter therefore records affected feature categories as unknown instead of guessing. Default conversion blocks with `SOURCE_EXPORT_KNOWN_BUG`. Explicit `SourceRiskPolicy.ALLOW_WITH_DIAGNOSTIC` or `--allow-known-source-export-risk` permits a controlled attempt and preserves `declared_source_version` and unverified source-fidelity provenance. It never changes source metadata before reading. An authentic re-export from 3.8.99 is recommended when the Spine project is available. No authentic 3.8.99 export fixture is present.

## D. Real asset results

Real input: `tests/fixtures/spine38/golden_ingot.json`, `golden_ingot.atlas`, and `golden_ingot.png`; exact source version `3.8.75`. The same source file was converted independently to every target in the matrix.

| Output | Bones | Slots | Skins | Attachments | Animations | Timelines / keys | Bézier segments / max error |
|---|---:|---:|---:|---|---|---|---|
| 3.5.51 | 5 | 8 | 1 | 8 region | idle, winning | 5 / 25 | 20 / 0 (legacy representation retained) |
| 3.6.53 | 5 | 8 | 1 | 8 region | idle, winning | 5 / 25 | 20 / 0 (legacy representation retained) |
| 3.7.94 | 5 | 8 | 1 | 8 region | idle, winning | 5 / 25 | 20 / 0 (legacy representation retained) |
| 4.0.31 | 5 | 8 | 1 | 8 region | idle, winning | 5 / 25 | 42 / 2.731148640577885e-14 |
| 4.1.56 | 5 | 8 | 1 | 8 region | idle, winning | 5 / 25 | 42 / 2.731148640577885e-14 |
| 4.2.43 | 5 | 8 | 1 | 8 region | idle, winning | 5 / 25 | 42 / 2.731148640577885e-14 |
| 4.3.13 | 5 | 8 | 1 | 8 region | idle, winning | 5 / 25 | 42 / 2.731148640577885e-14 |

The older targets use the same official legacy normalized curve representation; tests sample each source and target curve at 257 matching normalized times and verify exact equality. 4.x targets decode source controls, emit the target per-channel absolute controls, sample 257 shared times per supported channel, and report maximum deviation. Negative deltas and channel defaults are covered by synthetic tests. The target keyframe totals remain 25; no animation timelines are removed on successful conversion.

For direct 3.8→4.x outputs, exact matching runtime packages parsed the real skeleton and atlas, resolved attachments, instantiated setup pose, and evaluated two animations at four timestamps each: 8 samples per runtime with no runtime exception or non-finite world transform. The synthetic 3.8 IK/path fixture loaded and evaluated 4 samples in runtime 4.3.13. Direct 4.0.31→4.1.56, 4.1.56→4.2.43, and 4.2.43→4.3.13 conversions of real intermediate outputs each passed B1 bundle inspection and exact matching official runtime parsing and animation-state evaluation for 8 samples. These results do not certify rendered visual equivalence. Historical 3.x target runtimes were not executed.

An authentic 3.8.99 fixture remains unavailable. Synthetic 3.8.99 fixtures exercised each of the seven target writers; synthetic 3.8.99 bundles targeting 3.5.51, 3.6.53, and 3.7.94 passed B1 dependency inspection. Separate synthetic 4.x bundle tests exercise target schema and curve behavior.

## E. Atlas and complete asset integrity

The real 3.8.75 bundle was converted and re-inspected through B1 for the 3.5.51, 3.6.53, and 3.7.94 targets. Skeleton attachment paths, atlas regions, page references, and texture page dependencies resolved; the PNG bytes were unchanged. A synthetic 3.8.99 bundle with a region attachment and atlas page passed the same checks for each legacy target. A synthetic 3.7.94 bundle passed full B1 inspection after conversion to 3.8.99. A synthetic 3.8 fixture covers meshes and weights, linked meshes, clipping, bounding boxes, paths, points, events, constraints, and animation categories through the legacy writers. The 4.0.31→4.1.56, 4.1.56→4.2.43, and 4.2.43→4.3.13 real fixture bundles also passed B1 inspection. Exact 4.x runtime smoke tests loaded atlas pages and resolved their supported attachments. Atlas tests cover multi-page atlases, indexed regions, rotation, offsets, dimensions, filtering, wrapping, and deterministic serialization.

## F. Testing and qualification

After the direct 3.7→3.6 and 3.6→3.5 additions, `.venv/bin/python -m pytest -q` passed **95 tests**; Ruff passed; strict mypy passed with no issues in 33 source files; and package build produced sdist and wheel. Focused conversion tests passed 53 tests. Installed CLI conversion and planning passed for 3.7→3.6 and 3.6→3.5. Route-specific bundle roundtrips cover both reverse legacy routes plus 4.3→4.2, 4.2→4.1, and 4.1→4.0; each passed B1 reinspection with PNG bytes preserved. Exact historical runtimes were not executed for the new reverse legacy routes.

Required commands:

- `.venv/bin/python -m pytest -q`
- `.venv/bin/ruff check src tests`
- `.venv/bin/mypy`
- `.venv/bin/python -m build`

Route checks also cover installed CLI planning, deterministic output, source immutability, invalid target requests, unknown timeline types, missing linked-mesh parents, invalid constraints/deform data, malformed curves, missing schema fields, known 3.8.75 risk policy, atlas reparse, and dependency resolution. Runtime smoke uses only exact Spine 4.0.31, 4.1.56, 4.2.43, and 4.3.13 packages. No runtime or visual certification is claimed for a target whose runtime did not execute.

## G. Git

- Development branch: `codex/b2-conversion-engine`.
- B2 development checkpoint: `74af8b33b9d7b3303b23762671a50283c417a9a9`.
- Prior 3.8.75→4.2.43 hardening implementation: `b8cc4ac95a0b7ecea80ed81546f0e7ae61d60a0b`.
- Prior 3.8.99→4.2.43 route: `50a2dbc7d9a82fff4b09fc0da7551d0ecdec6920`.
- Complete 3.8 route matrix and direct 4.2.43→4.3.13 development checkpoint: `c6f91a8ad`.
- Current tested implementation checkpoint, including 4.1.56→4.2.43: `b62f01b36`.
- Development checkpoint `3a075e108b1b064d36ba536b2e7dbeea37a55104` records the tested 3.7.94→3.8.99 route.
- Direct 3.6.53→3.7.94 migration checkpoint: `57d89f82cdff1ac342fd03e4b2fbf5e7c855b288`.
- Direct 3.5.51→3.6.53 migration checkpoint: `3f4d23c9e76693e7429367ee9686d95b7c7a649c`.
- Direct 4.3.13→4.2.43 downgrade checkpoint: `431d310cc59004c74323919ad639da7369586091`.
- Direct 4.2.43→4.1.56 downgrade checkpoint: `53c81229381bf416a38fceacd02ea664583851ab`.
- Direct 4.1.56→4.0.31 downgrade checkpoint: `5ef31b38ae7448abc7d7164a93697ba9e57304df`.
- Direct reverse legacy migrations checkpoint: `d0efb910140772db8a0a8dfffc96be96ffde2557`.
- B2 remains open and unfrozen.

## H. Remaining work

- Complete a matching historical Spine 3.5.51, 3.6.53, and 3.7.94 runtime load/evaluation harness or record the exact tooling/license blocker; current verification is structural plus B1 dependency resolution.
- Obtain an authentic 3.8.99 export fixture and run it through all seven target routes.
- Expand real 3.8 fixture coverage to weighted meshes, linked meshes, clipping, bounding boxes, paths, points, and each supported constraint/timeline family.
- Implement and test remaining directed routes where semantically possible. Adjacent 3.5↔3.6, 3.6↔3.7, 3.7→3.8 and 4.0↔4.1, 4.1↔4.2, 4.2↔4.3 edges now have tested supported subsets. Cross-family non-adjacent routes remain incomplete; unrelated migrations are not forced through 3.8. General graph-based composition is not implemented.
- Add graph-based planning only after direct edges exist; qualify every composed route end to end and reject any hop that discards semantics.
- Expand official target runtime coverage and keep parser, animation-state, and visual verification statuses separate.

## I. Freeze decision

**B2 OPEN / BLOCKED.** The complete direct 3.8 patch-to-target route set, five adjacent directed historical 3.x edges, three forward and three supported reverse adjacent 4.x edges are implemented. Cross-family route composition, remaining direct cross-family migrations, historical target runtime qualification, and the broader directed conversion graph remain incomplete. No full matrix or visual equivalence certification is claimed.
