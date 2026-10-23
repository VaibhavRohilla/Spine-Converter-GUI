# FNX Spine Forge B2 conversion report

## B2 integration and fidelity closure pass — 2026-10-23

Starting HEAD was `22b65b1a82277740b5bccd8630830559ca5d93df`. The earlier
uncommitted asset-set service was retained and hardened; no migration
implementation was rewritten.

### Implemented and verified in this pass

- Asset-set staging now rejects B1 errors affecting the selected bundle,
  validates the source and every intermediate/final skeleton-atlas-texture set
  through B1, tries deterministic candidate routes after a feature rejection,
  and publishes no output mapping until one complete route passes.
- Added 12 asset-set tests for single-hop output artifacts, two-page atlases,
  linked-mesh semantics, missing regions/textures, ambiguous atlas selection,
  malformed skeleton and atlas intermediates, rollback/no partial output,
  texture SHA-256 identity, repeat determinism, source immutability, and the
  3.8.75 risk policy. A successful composed 4.0.31→4.1.56→4.2.43 test
  re-inspects the returned bundle and compares its skeleton bytes to the same
  direct-edge sequence.
- Added `conversion/semantic.py` typed semantic views consumed by
  `SkeletonConverter.read` for named-skin schemas: exact-patch admission,
  bone transforms/hierarchy, slots, skins, attachment discriminators and
  linked-mesh parents, weighted mesh influence arrays, constraint indexes,
  timeline categories, and per-channel Bézier control groups. Unknown bone,
  slot, and attachment fields block strict admission. Raw JSON remains the
  migration serialization boundary. Legacy object-map skin bodies continue to
  be validated by their existing migration readers.
- Atlas conversion now decodes source-version region geometry into typed
  page/region geometry records and rejects schema/geometry mismatches before
  serialization. The converter continues to preserve raw metadata through its
  validated atlas serialization path.
- Asset-set hop evidence includes migration statistics, numerical curve error,
  rejected candidate routes, unsupported features, and source-risk warnings.

### Pair and composed-route qualification

Status legend: `E-R` = exact route is executable with tested restrictions;
`E-I` = composed execution demonstrated but qualification incomplete; `C` =
candidate path only; `N` = not implemented; `I` = same-version identity. These
statuses describe the representative fixture evidence, not universal feature
support. For 3.8, the 3.8.75 row is separate and risk gated; it must not be
merged with 3.8.99 provenance.

| Source \\ Target | 3.5.51 | 3.6.53 | 3.7.94 | 3.8.99 | 4.0.31 | 4.1.56 | 4.2.43 | 4.3.13 |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| 3.5.51 | I | E-R | C | C | C | C | C | C |
| 3.6.53 | E-R | I | E-R | C | C | C | C | C |
| 3.7.94 | C | E-R | I | E-R | C | C | C | C |
| 3.8.75 (risk gated) | E-R | E-R | E-R | I | E-R | E-R | E-R | E-R |
| 3.8.99 | E-R | E-R | E-R | I | E-R | E-R | E-R | E-R |
| 4.0.31 | C | C | C | E-R | I | E-R | E-I | C |
| 4.1.56 | C | C | C | C | E-R | I | E-R | C |
| 4.2.43 | C | C | C | C | C | E-R | I | E-R |
| 4.3.13 | C | C | C | C | C | C | E-R | I |

The six priority longer family routes remain **candidate-only**, except the
tested asset-set/CLI 4.0.31→4.2.43 route, which remains `E-I` because its
composed feature matrix is incomplete. No end-to-end semantic campaign was run
for the six requested long paths. Existing direct-route tests include numeric
curve sampling and route-specific semantic assertions; the composed test
records nonzero Bézier coverage and per-hop `max_numerical_error <= 1e-12` on
the representative authentic-derived 3.8.75 bundle transformed to 4.0.31.
This evidence does not qualify all animation, weighted mesh, deform, constraint,
event, draw-order, skin, or curve combinations for a composed route. Unsafe
4.0.31→3.8.99 per-channel curves remain rejected without approximation.

### Runtime and authentic-source evidence

No historical 3.5.51, 3.6.53, 3.7.94, or exact 3.8.99 runtime package is
installed in this workspace. The runtime harness targets official
`@esotericsoftware/spine-core` package identities for 4.x only, so the
historical smoke returns `not_run` because the exact package metadata path is
absent. The official runtime source is available by version branches, but
runtime use is subject to Spine licensing; this environment contains no
provided licensed historical runtime build. The official versioning guide
defines runtime lines by major/minor branches rather than the editor patch
number; no patch string was altered to bypass that distinction. See the
[official versioning guide](https://esotericsoftware.com/spine-versioning) and
[runtime licensing information](https://esotericsoftware.com/spine-runtime-architecture).

The fixture corpus still contains only the authentic exported 3.8.75
`golden_ingot` JSON/atlas/PNG. No authentic 3.8.99 export was available, and no
metadata rewrite was used. The fixture includes real region attachments and
animation curves, but not the full requested set of weighted meshes, deform,
constraint, event, draw-order, multiple-skin, and linked-mesh cases together.
No runtime pose or visual-frame equivalence is claimed.

### Commands and results

- `.venv/bin/python -m pytest -q` — **114 passed**.
- `.venv/bin/ruff check src tests` — **passed**.
- `.venv/bin/mypy` — **passed**, 38 source files.
- `.venv/bin/python -m build` — **passed**, wheel and sdist.
- `.venv/bin/python -m pip install -e '.[dev]'` and
  `.venv/bin/spine-forge --help` — **passed**.
- Installed CLI composed conversion 4.0.31→4.1.56→4.2.43 — **passed**;
  returned output declared 4.2.43 and per-hop metrics reported 42 Bézier
  segments with zero measured numerical error.
- Installed CLI direct conversion 4.2.43→4.3.13 — **passed**; reported 42
  Bézier segments and zero measured numerical error.
- Installed CLI malformed source — **rejected**, exit code 2.
- Asset-set B1 output reinspection, missing-dependency rejection, source
  immutability, texture hash identity, deterministic repeat, and rollback tests
  — **passed**.
- Historical runtime smoke — **UNVERIFIED / not_run**: exact package metadata
  was unavailable. No visual check was run.

**B2 OPEN / BLOCKED.** The asset-set service, typed semantic admission subset,
CLI integration, and focused composed-path evidence are implemented. Freeze
gates remain unmet: all six priority long paths need end-to-end feature and
numerical comparison, the 56-pair matrix needs route/feature qualification,
historical runtime builds and authentic 3.8.99 source evidence are missing, and
the typed boundary does not yet model every version-specific legacy skin,
deform, constraint, and animation schema field.

## B2 final hardening pass — 2026-10-23

Starting state was branch `codex/b2-conversion-engine`, clean at
`22b65b1a82277740b5bccd8630830559ca5d93df` (the stated implementation
checkpoint `afc2050f61f59379014ce116b1bd856843f5ef9` is an ancestor).

### Asset-set service

Added internal `AssetSetConverter` using `InspectionService` B1 bundle
resolution. It reads one skeleton bundle, stages skeleton/atlas/PNG bytes in
memory, chooses the existing exact-patch route, converts the skeleton and each
atlas on every hop, then re-runs B1 dependency resolution against a controlled
temporary directory before advancing. The caller receives the output mapping
only after all hops pass; texture bytes are retained unchanged and SHA-256
digests are returned. Failures identify the hop, relevant asset, feature, and
reason. No ZIP or folder export workflow was added.

Smoke evidence: the authentic available `golden_ingot` bundle converted from
3.8.75 to 4.2.43 when the explicit `ALLOW_WITH_DIAGNOSTIC` policy was supplied;
the output contained JSON, atlas, and PNG. Default conversion still rejects
3.8.75 under the source-risk policy. This one real asset result is structural
and dependency verification only, not runtime or visual certification.

### Qualification and remaining boundary

The current registry and tests continue to define direct-route subsets. The
executor is transactional for skeleton bytes, but its registered candidates
are not a 56-pair feature-aware semantic qualification matrix. The new
asset-set wrapper applies the selected planner route and validates each
intermediate asset set; it does not establish general route eligibility for
every feature combination. Typed semantic schemas for the listed high-risk
constructs have not been comprehensively introduced. Per-channel Bézier
representability remains guarded by existing route checks; no new numerical
curve equivalence campaign was run here.

The planner's exact-patch matrix is classified below. `D` means an exact
direct route is registered and executable subject to its converter's feature
checks; `C` means a graph candidate exists but its composed path is not
end-to-end qualified; `N` means no candidate path. These labels do not imply
full feature, runtime, or visual qualification.

| Source \\ Target | 3.5.51 | 3.6.53 | 3.7.94 | 3.8.99 | 4.0.31 | 4.1.56 | 4.2.43 | 4.3.13 |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| 3.5.51 | I | D | C | C | C | C | C | C |
| 3.6.53 | D | I | D | C | C | C | C | C |
| 3.7.94 | C | D | I | D | C | C | C | C |
| 3.8.75 (risk gated) | D | D | D | D | D | D | D | D |
| 3.8.99 | D | D | D | I | D | D | D | D |
| 4.0.31 | C | C | C | D | I | D | C | C |
| 4.1.56 | C | C | C | C | D | I | D | C |
| 4.2.43 | C | C | C | C | C | D | I | D |
| 4.3.13 | C | C | C | C | C | C | D | I |

`I` is same-version identity serialization. The requested six long routes
(3.5→4.3, 3.6→4.2, 3.7→4.1, 4.3→3.8, 4.2→3.6, and 4.1→3.5) are candidates
only. There is no end-to-end conversion or numerical semantic equivalence
result for them in this pass.

Only 3.8.75 authentic export assets are present in `tests/fixtures`; no
authentic 3.8.99 or historical 3.5/3.6/3.7 runtime package was found in the
workspace. Historical runtime status remains **UNVERIFIED**. The current
runtime harness accepts official 4.x package identities only. No version
string rewriting was used. Structural, runtime, and visual verification remain
separate; no visual verification is claimed.

### Commands and status

- `.venv/bin/python -m pytest -q` — **103 passed** (existing suite).
- `.venv/bin/ruff check src tests` — first run caught formatting/import issues
  in the new service; those were corrected. Final result recorded below.
- `.venv/bin/mypy` — **passed**, 37 source files.
- `.venv/bin/python -m build` — **passed**, sdist and wheel.
- Direct asset-set smoke on the authentic 3.8.75 bundle — **passed** with
  explicit risk allowance; output bytes held until full set passed.
- Installed CLI smoke, 56 end-to-end pair tests, historical runtime loads,
  numerical cross-route animation comparison, and transaction fault-injection
  tests were not completed in this pass.

**B2 OPEN / BLOCKED.** Asset-set transaction and per-hop B1 reinspection are
implemented. Acceptance remains open because the complete feature-aware matrix,
typed semantic contracts, authentic 3.8.99 fixture, numerical composed-path
equivalence, and historical runtime evidence are not established.

## Final implementation pass — 2026-10-23

This status update records work performed against the live branch and supersedes
older completion claims wherever they conflict. Prior route evidence remains
scoped to the specific assets and tests cited below.

## Production hardening follow-up

- Centralized exact patch registrations and typed migration kinds in
  `conversion/registry.py`; the planner, skeleton service, atlas service, and
  CLI now consume this catalog instead of maintaining duplicate route sets.
- Expanded the 4.0.31→3.8.99 writer to reverse representable rotation, `rgba` /
  `rgba2`, transform-mix, path-mix, linked-mesh, and deform timeline mappings.
  It rejects unequal transform/path channels and non-deform attachment
  timelines. Unsupported constructs from this route carry a typed feature code
  instead of relying on parsing exception text.
- Planning uses exact route entries only. It returns a multi-hop candidate for
  visibility but keeps it non-executable until end-to-end qualification exists.
  Exact same-version serialization is handled explicitly.
- Removed the unused `inspect_assets` compatibility function and updated tests
  to call `InspectionService` directly. Removed the unused `CompatibilityRegistry`
  placeholder that returned `NOT_IMPLEMENTED` for every query.
- Static verification remains strict mypy; the schema-transform code still
  contains dynamic JSON dictionaries (`Any`) because the supported Spine JSON
  schemas have not yet been modeled as version-specific `TypedDict` contracts.
  This follow-up does not claim the entire converter is weak-type-free. Replacing
  those dictionaries safely requires schema models and validator migration per
  version family; a mechanical annotation swap would not provide real safety.
- **B2 remains OPEN / BLOCKED.** This route-catalog hardening does not add
  composed execution or complete cross-version qualification.
- Follow-up gates: **101 tests passed**, Ruff passed, mypy passed across 35
  source files, and package build passed. Installed CLI reports 4.0.31→3.8.99
  as a direct route and 3.5.51→4.3.13 as a non-executable composed candidate.

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

- `.venv/bin/python -m pytest -q` — **101 passed**.
- `.venv/bin/ruff check src tests` — **passed**.
- `.venv/bin/mypy` — **passed**, 35 source files.
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

## B2 executor addendum (2026-10-23)

### A. Conversion architecture update

Added `MigrationExecutor` as a transactional in-memory route runner. It enumerates at most 32 simple paths of depth 12 in deterministic breadth-first order, so direct qualified routes precede longer paths. Each hop is sent through the existing `SkeletonConverter` direct-route implementation, which remains responsible for exact-version feature rejection and target structural reinspection. The executor returns final bytes only after every hop passes, with source/target versions, status, diagnostic codes, and statistics for each hop. Failed attempts return no bytes and include the first failed hop. Original input bytes are not mutated. The existing JSON document remains dynamically represented; broad typed semantic models are not yet implemented.

`ConversionPlanner.plan()` deliberately continues to mark discovered composed paths as not independently qualified. `candidate_routes()` exposes bounded candidates to the executor; graph connectivity alone is not reported as a qualification result. Atlas conversion still does not share an executed route with skeleton conversion, and complete multi-hop asset-set conversion/B1 reinspection is outstanding.

### Multi-hop execution evidence

Focused synthetic execution, with per-hop target structural reinspection:

| Route | Result | Evidence |
|---|---|---|
| 3.5.51 → 3.6.53 → 3.7.94 → 3.8.99 → 4.3.13 | Passed | Four recorded successful hops; target version reinspection at each hop; original input remains 3.5.51 |
| 3.7.94 → 3.8.99 → 4.1.56 | Passed | Two recorded successful hops |
| 3.7.94 → 3.8.99 → 4.3.13 with a supported basic fixture | Passed | Two recorded successful hops |
| 4.3.13 → 4.2.43 → … with malformed 4.3 skin schema | Rejected at first hop | No output; failed-hop evidence identifies 4.3.13 → 4.2.43 |

These are synthetic structural checks, not runtime or visual qualification. The requested weighted-mesh/linked-mesh and broader constraint/timeline real-asset coverage remains incomplete.

### Family representative matrix (56 ordered pairs)

The following routes use exact representatives `3.5.51`, `3.6.53`, `3.7.94`, `3.8.99`, `4.0.31`, `4.1.56`, `4.2.43`, and `4.3.13`. `Candidate` means the executor can attempt the shown registered hops and each hop applies its own strict feature checks; it does not imply every input feature subset has been qualified end to end. Structural qualification is limited to the direct routes and explicit synthetic multi-hop rows above. Runtime qualification is only as described in section D; all other composed rows are not runtime-qualified. End-to-end coverage is incomplete for every pair except explicitly tested cases in sections B and this addendum.

| Source | Target | Registered candidate route | Execution / qualification |
|---|---|---|---|
| 3.5.51 | 3.6.53 | 3.5.51 → 3.6.53 | Candidate; feature-gated per hop; end-to-end qualification incomplete |
| 3.5.51 | 3.7.94 | 3.5.51 → 3.6.53 → 3.7.94 | Candidate; feature-gated per hop; end-to-end qualification incomplete |
| 3.5.51 | 3.8.99 | 3.5.51 → 3.6.53 → 3.7.94 → 3.8.99 | Candidate; feature-gated per hop; end-to-end qualification incomplete |
| 3.5.51 | 4.0.31 | 3.5.51 → 3.6.53 → 3.7.94 → 3.8.99 → 4.0.31 | Candidate; feature-gated per hop; end-to-end qualification incomplete |
| 3.5.51 | 4.1.56 | 3.5.51 → 3.6.53 → 3.7.94 → 3.8.99 → 4.1.56 | Candidate; feature-gated per hop; end-to-end qualification incomplete |
| 3.5.51 | 4.2.43 | 3.5.51 → 3.6.53 → 3.7.94 → 3.8.99 → 4.2.43 | Candidate; feature-gated per hop; end-to-end qualification incomplete |
| 3.5.51 | 4.3.13 | 3.5.51 → 3.6.53 → 3.7.94 → 3.8.99 → 4.3.13 | Candidate; feature-gated per hop; end-to-end qualification incomplete |
| 3.6.53 | 3.5.51 | 3.6.53 → 3.5.51 | Candidate; feature-gated per hop; end-to-end qualification incomplete |
| 3.6.53 | 3.7.94 | 3.6.53 → 3.7.94 | Candidate; feature-gated per hop; end-to-end qualification incomplete |
| 3.6.53 | 3.8.99 | 3.6.53 → 3.7.94 → 3.8.99 | Candidate; feature-gated per hop; end-to-end qualification incomplete |
| 3.6.53 | 4.0.31 | 3.6.53 → 3.7.94 → 3.8.99 → 4.0.31 | Candidate; feature-gated per hop; end-to-end qualification incomplete |
| 3.6.53 | 4.1.56 | 3.6.53 → 3.7.94 → 3.8.99 → 4.1.56 | Candidate; feature-gated per hop; end-to-end qualification incomplete |
| 3.6.53 | 4.2.43 | 3.6.53 → 3.7.94 → 3.8.99 → 4.2.43 | Candidate; feature-gated per hop; end-to-end qualification incomplete |
| 3.6.53 | 4.3.13 | 3.6.53 → 3.7.94 → 3.8.99 → 4.3.13 | Candidate; feature-gated per hop; end-to-end qualification incomplete |
| 3.7.94 | 3.5.51 | 3.7.94 → 3.6.53 → 3.5.51 | Candidate; feature-gated per hop; end-to-end qualification incomplete |
| 3.7.94 | 3.6.53 | 3.7.94 → 3.6.53 | Candidate; feature-gated per hop; end-to-end qualification incomplete |
| 3.7.94 | 3.8.99 | 3.7.94 → 3.8.99 | Candidate; feature-gated per hop; end-to-end qualification incomplete |
| 3.7.94 | 4.0.31 | 3.7.94 → 3.8.99 → 4.0.31 | Candidate; feature-gated per hop; end-to-end qualification incomplete |
| 3.7.94 | 4.1.56 | 3.7.94 → 3.8.99 → 4.1.56 | Candidate; feature-gated per hop; end-to-end qualification incomplete |
| 3.7.94 | 4.2.43 | 3.7.94 → 3.8.99 → 4.2.43 | Candidate; feature-gated per hop; end-to-end qualification incomplete |
| 3.7.94 | 4.3.13 | 3.7.94 → 3.8.99 → 4.3.13 | Candidate; feature-gated per hop; end-to-end qualification incomplete |
| 3.8.99 | 3.5.51 | 3.8.99 → 3.5.51 | Candidate; feature-gated per hop; end-to-end qualification incomplete |
| 3.8.99 | 3.6.53 | 3.8.99 → 3.6.53 | Candidate; feature-gated per hop; end-to-end qualification incomplete |
| 3.8.99 | 3.7.94 | 3.8.99 → 3.7.94 | Candidate; feature-gated per hop; end-to-end qualification incomplete |
| 3.8.99 | 4.0.31 | 3.8.99 → 4.0.31 | Candidate; feature-gated per hop; end-to-end qualification incomplete |
| 3.8.99 | 4.1.56 | 3.8.99 → 4.1.56 | Candidate; feature-gated per hop; end-to-end qualification incomplete |
| 3.8.99 | 4.2.43 | 3.8.99 → 4.2.43 | Candidate; feature-gated per hop; end-to-end qualification incomplete |
| 3.8.99 | 4.3.13 | 3.8.99 → 4.3.13 | Candidate; feature-gated per hop; end-to-end qualification incomplete |
| 4.0.31 | 3.5.51 | 4.0.31 → 3.8.99 → 3.5.51 | Candidate; feature-gated per hop; end-to-end qualification incomplete |
| 4.0.31 | 3.6.53 | 4.0.31 → 3.8.99 → 3.6.53 | Candidate; feature-gated per hop; end-to-end qualification incomplete |
| 4.0.31 | 3.7.94 | 4.0.31 → 3.8.99 → 3.7.94 | Candidate; feature-gated per hop; end-to-end qualification incomplete |
| 4.0.31 | 3.8.99 | 4.0.31 → 3.8.99 | Candidate; feature-gated per hop; end-to-end qualification incomplete |
| 4.0.31 | 4.1.56 | 4.0.31 → 4.1.56 | Candidate; feature-gated per hop; end-to-end qualification incomplete |
| 4.0.31 | 4.2.43 | 4.0.31 → 3.8.99 → 4.2.43 | Candidate; feature-gated per hop; end-to-end qualification incomplete |
| 4.0.31 | 4.3.13 | 4.0.31 → 3.8.99 → 4.3.13 | Candidate; feature-gated per hop; end-to-end qualification incomplete |
| 4.1.56 | 3.5.51 | 4.1.56 → 4.0.31 → 3.8.99 → 3.5.51 | Candidate; feature-gated per hop; end-to-end qualification incomplete |
| 4.1.56 | 3.6.53 | 4.1.56 → 4.0.31 → 3.8.99 → 3.6.53 | Candidate; feature-gated per hop; end-to-end qualification incomplete |
| 4.1.56 | 3.7.94 | 4.1.56 → 4.0.31 → 3.8.99 → 3.7.94 | Candidate; feature-gated per hop; end-to-end qualification incomplete |
| 4.1.56 | 3.8.99 | 4.1.56 → 4.0.31 → 3.8.99 | Candidate; feature-gated per hop; end-to-end qualification incomplete |
| 4.1.56 | 4.0.31 | 4.1.56 → 4.0.31 | Candidate; feature-gated per hop; end-to-end qualification incomplete |
| 4.1.56 | 4.2.43 | 4.1.56 → 4.2.43 | Candidate; feature-gated per hop; end-to-end qualification incomplete |
| 4.1.56 | 4.3.13 | 4.1.56 → 4.2.43 → 4.3.13 | Candidate; feature-gated per hop; end-to-end qualification incomplete |
| 4.2.43 | 3.5.51 | 4.2.43 → 4.1.56 → 4.0.31 → 3.8.99 → 3.5.51 | Candidate; feature-gated per hop; end-to-end qualification incomplete |
| 4.2.43 | 3.6.53 | 4.2.43 → 4.1.56 → 4.0.31 → 3.8.99 → 3.6.53 | Candidate; feature-gated per hop; end-to-end qualification incomplete |
| 4.2.43 | 3.7.94 | 4.2.43 → 4.1.56 → 4.0.31 → 3.8.99 → 3.7.94 | Candidate; feature-gated per hop; end-to-end qualification incomplete |
| 4.2.43 | 3.8.99 | 4.2.43 → 4.1.56 → 4.0.31 → 3.8.99 | Candidate; feature-gated per hop; end-to-end qualification incomplete |
| 4.2.43 | 4.0.31 | 4.2.43 → 4.1.56 → 4.0.31 | Candidate; feature-gated per hop; end-to-end qualification incomplete |
| 4.2.43 | 4.1.56 | 4.2.43 → 4.1.56 | Candidate; feature-gated per hop; end-to-end qualification incomplete |
| 4.2.43 | 4.3.13 | 4.2.43 → 4.3.13 | Candidate; feature-gated per hop; end-to-end qualification incomplete |
| 4.3.13 | 3.5.51 | 4.3.13 → 4.2.43 → 4.1.56 → 4.0.31 → 3.8.99 → 3.5.51 | Candidate; feature-gated per hop; end-to-end qualification incomplete |
| 4.3.13 | 3.6.53 | 4.3.13 → 4.2.43 → 4.1.56 → 4.0.31 → 3.8.99 → 3.6.53 | Candidate; feature-gated per hop; end-to-end qualification incomplete |
| 4.3.13 | 3.7.94 | 4.3.13 → 4.2.43 → 4.1.56 → 4.0.31 → 3.8.99 → 3.7.94 | Candidate; feature-gated per hop; end-to-end qualification incomplete |
| 4.3.13 | 3.8.99 | 4.3.13 → 4.2.43 → 4.1.56 → 4.0.31 → 3.8.99 | Candidate; feature-gated per hop; end-to-end qualification incomplete |
| 4.3.13 | 4.0.31 | 4.3.13 → 4.2.43 → 4.1.56 → 4.0.31 | Candidate; feature-gated per hop; end-to-end qualification incomplete |
| 4.3.13 | 4.1.56 | 4.3.13 → 4.2.43 → 4.1.56 | Candidate; feature-gated per hop; end-to-end qualification incomplete |
| 4.3.13 | 4.2.43 | 4.3.13 → 4.2.43 | Candidate; feature-gated per hop; end-to-end qualification incomplete |

The Spine 3.8.75 routes are separately registered as source-risk routes and remain blocked by default under `REJECT_KNOWN_ISSUES`. Explicit allow-with-diagnostic is still required; 3.8.75 is not substituted for the 3.8.99 representative above. Spine 3.8.75 remains subject to the established defect policy. No 3.8.75 defect is bypassed by composition.

### Current gates and decision

- `.venv/bin/python -m pytest -q`: **103 passed**.
- `.venv/bin/ruff check src tests`: **passed**.
- `.venv/bin/mypy`: **passed, 36 source files**.
- `.venv/bin/python -m build`: **passed**, sdist and wheel produced.
- Dedicated regression tests cover a four-hop success, original source immutability, per-hop evidence, and stop-on-first-hop failure with no output.
- Historical 3.5.51/3.6.53/3.7.94 runtime availability and execution remain unverified in this batch. Authentic 3.8.99 fixture and the requested all-route semantic/runtime/asset qualification are also outstanding.

**B2 OPEN / BLOCKED.** The executor makes registered compositions executable only when every existing direct migration accepts and structurally validates its hop. This batch does not complete the required feature-aware whole-route qualification, typed semantic schemas, integrated skeleton+atlas+PNG asset-set conversion, all 56 end-to-end pair qualifications, historical runtime qualification, or authentic 3.8.99 fixture coverage. Graph candidates are not certification. No B3, B4, or B5 work is included.

### Git checkpoint

- Tested implementation checkpoint: `afc2050f61f59379014ce116b1bd856843f5ef9f` (`Add transactional multi-hop migration executor`).
- Branch: `codex/b2-conversion-engine`.
- The checkpoint was created after the required tests, lint, type check, build, installed CLI conversion, and B1 fixture inspection passed. Working tree was clean immediately after that commit.
- This is a development checkpoint; it does not freeze B2.
