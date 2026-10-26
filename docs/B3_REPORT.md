# FNX Spine Forge — B3 qualification report

> Historical checkpoint: this report records the schema-1 B3 implementation.
> The current typed schema-2 contract, cleanup and test evidence are in
> [B3_HARDENING_REPORT.md](B3_HARDENING_REPORT.md). Its API descriptions supersede
> this checkpoint; the original evidence below is retained for audit history.

Decision: **B3 PARTIAL — BUNDLE SUBSYSTEM FROZEN**.

The restricted JSON bundle workflow is implemented and verified. Overall B3
remains open: the required minimum semantically qualified binary target and
complete binary feature implementation are **not achieved**. A genuine,
experimental 4.2.43 hierarchy codec is implemented; it does not fulfill the full
binary acceptance scope. This is not a v1.0 release or runtime/visual certification.

Machine-readable executed evidence: [B3_qualification.json](evidence/B3_qualification.json).

## A. Architecture audit

The starting tree was clean on `codex/b2-conversion-engine` at
`f844cd08d4a8c8e2a6aaf3103b0a3910997b8997`. The supplied freeze commit
`a6173e32fb19d42b67e33b2113366f4006ab509d` is its ancestor. The actual baseline
passed **212 tests**, rather than the earlier supplied 166-test snapshot.

Reused owners:

- B1 `AssetSource`, `SourceLimits`, canonical paths, `InspectionService`, parsers,
  `DependencyResolver`, immutable manifests and logical bundle IDs.
- B2 `AssetSetConverter`, `SkeletonConverter`, `AtlasConverter`, their existing
  per-hop execution/validation, planner, migration registry and
  `QualificationService`. No competing migration implementations were added.
- Existing B2 runtime smoke service, only for external qualification evidence.

Added `bundle.py` for typed requests/results, source selection, B1 discovery
projection, source snapshots, orchestration, packaging and publication;
`binary.py` for bounded primitives, the central binary capability registry and
restricted codec; `texture.py` for PNG container checks; and a read-only external
reference-parser script. ZIP parsing remains exclusively in B1's source reader
for ingestion. ZIP writing uses the standard library, with reopening through B1.

B1 gained validated atlas/texture mapping overrides, directory context for
matching, and registry-backed restricted binary inspection. Duplicate same-stem
atlas candidates retain the frozen ambiguity rejection. B2 gained stage hooks
and source-wide overrides scoped to each isolated asset-set validation stage.

Primary references for the parser correction are the exact official
[4.2.43 TextureAtlas reader](https://unpkg.com/@esotericsoftware/spine-core@4.2.43/dist/TextureAtlas.js)
and [4.3.13 TextureAtlas reader](https://unpkg.com/@esotericsoftware/spine-core@4.3.13/dist/TextureAtlas.js).

Two real integration defects were corrected in existing B2 owners:

1. `merged_multi` weights at the existing inclusive `1e-5` tolerance boundary
   were rejected by subtraction rounding. Accurate summation and inclusive
   floating-point endpoints now admit representation rounding at that boundary.
   No weights are normalized or rewritten. Values immediately outside tolerance
   still reject; dedicated endpoint/negative tests pass.
2. Modern atlas `rotate: true/false` was rejected as non-integer despite both
   exact official 4.2.43 and 4.3.13 `TextureAtlas` readers accepting it. One shared
   rotation parser now handles that vocabulary and existing allowed degrees.
   Unsupported rotations still reject. No qualification records were broadened.

## B. Bundle discovery

Inputs: folders, bounded ZIP archives, and explicit `tuple[Path, ...]` selections.
Explicit selections retain paths relative to their common parent and use B1's
reader/security checks. Input bytes are snapshotted before conversion; all job
checksums and conversions consume that snapshot. Stable IDs remain canonical
relative paths, including duplicate basenames in different directories.

Matching remains B1-owned: image attachment/atlas region evidence, declared atlas
pages, directory context and secondary stem signals. Missing/ambiguous mappings
are surfaced. Indexed regions and non-image attachment classification retain B1
behavior. Shared atlases/pages can be used by multiple independently reported
skeletons. Mixed source versions and selection from multi-bundle ZIPs are tested.
A skeleton's atlas override selects one discovered atlas; unresolved competing
associations are never silently merged.

`DependencyMappings.atlases` maps skeleton path to atlas path;
`textures` maps `(atlas_path, declared_page)` to an existing texture path.
Overrides are validated against discovered assets and declarations. Image-region
coverage remains mandatory. Replacement texture bytes are materialized at the
atlas-declared portable resource path, with collision rejection; source files
are untouched. Required-only output removes superseded resource locations.

Inspection exposes assets, IDs, formats, versions, dependencies, resolved/missing
pages, diagnostic suggestions, target routes/qualification, output formats,
source-risk authorizations and required decisions. Bundle states are `READY`,
`NEEDS_SELECTION`, `INCOMPLETE`, `UNSUPPORTED`, `INVALID`. `READY` describes source
admission/dependencies, not target qualification. B2 admission failures are
surfaced rather than leaving a source apparently ready with no explanation.

## C. Conversion orchestration

`BundleService` selects and validates bundles, delegates each conversion to B2,
merges only byte-identical shared outputs, validates portable resources, builds
and reinspects the complete package, then publishes. A failed selected bundle
prevents the entire request from publishing. Per-bundle records distinguish
executed conversions from work not run. Shared-output conflicts retain every
selected bundle's result and publish nothing. Batch requests are
independent per-job transactions, including when targets differ.

Qualified mode is the default. Existing RC1 hierarchy/setup evidence does **not**
qualify atlas geometry. Complete cross-version atlas bundles consequently still
require explicit `experimental_structural=True`; qualified mode rejects them
with the existing missing-feature evidence. This restriction is preserved,
not hidden or relaxed to obtain a passing conversion.

Known 3.8.75 risk additionally requires
`SourceRiskPolicy.ALLOW_WITH_DIAGNOSTIC`. Experimental authorization alone does
not bypass it. Authentic Golden Ingot remains reported as 3.8.75.

Planning executes an isolated conversion rehearsal and validation without
creating output directories or publishing. Returned fields separately record
execution, structural checks, B2 semantic qualification, experimental consent,
source-risk status, runtime evidence and visual evidence. Failed inspection
reports retain the original source location, not random staging paths.

## D. Binary support

| Exact version | Decode | Encode | Coverage | Semantic qualification | Runtime qualification |
|---|---|---|---|---|---|
| 4.2.43 | Implemented, experimental | Implemented, experimental | Hierarchy/setup, inheritance, bone metadata, header metadata | No | No |
| Every other version | Rejected | Rejected | None advertised | No | No |

Decode and encode capabilities are independent and separately tested; a missing
encoder/decoder is enforced. Both public codec construction and service
conversion require explicit experimental authorization for the current record.
The exact wire version lives in shared version infrastructure and is admitted
through `BinaryCodecRegistry`. Recognition of another JSON family never creates
a binary capability.

The writer emits real binary fields and float32 values. It never renames JSON
bytes or edits a binary version header to migrate. Bundle conversion decodes to
JSON, delegates semantic migration to B2, then invokes only a registered target
encoder. Unsupported hashes/fields are rejected rather than discarded.

Bounds cover file size, UTF-8 byte lengths, canonical 32-bit varints, collection
counts, finite floats, parent ordering/indices, inheritance/boolean values,
truncation and trailing data. Nonessential defaults use the exact official
SkeletonData/BoneData defaults (zero FPS, transparent bone color, hidden editor
flag); independent byte-layout checks guard these values. Nonempty unsupported
record collections reject
before allocation or interpretation. No unsafe deserialization is used.

The independent wire vector is explicitly **hand-authored**, not an authentic
editor export or a fabricated authentic fixture. It was not produced by FNX's
encoder. Decode expectations are independently specified. Encode output is
checked by separate primitive layout assertions and the exact official reader.
The official `@esotericsoftware/spine-core@4.2.43` parser successfully interpreted
both the vector and FNX-encoded hierarchy values. The archive SHA-256 and observed
reference results are in the evidence JSON. Reproduction:

```sh
node scripts/verify_binary_reference.mjs /path/to/spine-core-4.2.43/package \
  /path/to/vector.skel tests/fixtures/binary/hierarchy_4_2_43.expected.json
```

The official Coin binary retrieved from the 4.2 runtime repository identifies
as **4.2.22**. It is rejected; it was not relabeled as 4.2.43. No local `.skel`
exports were found in WorkHub. Matching authentic 4.2.43 exported fixtures were
not obtained. The official reader check is useful restricted parsing evidence,
but does not establish the requested binary semantic qualification.

**Still unimplemented:** slots, skins/attachments, constraints, animation
keyframes/curves, meshes/weighted geometry/deform and events. Those requirements
remain open; this report does not redefine the agreed binary scope around the
hierarchy subset.

## E. Package verification

Viewer mode contains required assets only with the default required-only
retention policy. Golden Ingot ZIP members are exactly its JSON, atlas and PNG.
The real `merged_multi` output contains its JSON, atlas and both PNG pages.
Original relative structure is retained; conflicting resource mappings reject.
Textures remain byte-identical. PNG checks verify signature, bounded chunk
layout, CRCs, header dimensions and the ending; pixel decompression/rendering
and atlas-to-image visual correctness are not certified.

ZIP members are sorted, use fixed 1980 timestamps, consistent Unix file metadata
and DEFLATE level 9. The archive is reopened, CRC-checked, compared byte-for-byte
against the staged members and reinspected using B1. Repeated real Golden Ingot
and `merged_multi` ZIPs were byte-identical. Folder export is also reinspected.
Audit archives include provenance paths, so reproduction includes the same
request/source/destination provenance as well as the same source bytes.

Audit mode embeds a clearly identified **prepublication validation snapshot**.
It cannot truthfully contain its own final package hash/publication result.
The returned result and optional final sidecar contain final publication status,
all packaged-file checksums and the ZIP checksum. Viewer mode embeds no report.
`write_report`/`--report-output` publishes a sidecar separately and exclusively;
sidecar failure does not roll back an already published valid package and the
CLI reports that failure explicitly.

Final local artifacts (intentionally ignored under `dist/`):

- `dist/b3-qualification/final/golden_ingot_4_2.zip`
- `dist/b3-qualification/final/golden_ingot_4_2.report.json`
- `dist/b3-qualification/final/golden_ingot_4_3/`
- `dist/b3-qualification/final/merged_multi_4_3.zip`

Their verified checksums are recorded in the committed evidence JSON. The real
popup source was `/Users/fenix/WorkHub/SL-Games/SL-GoldenPavalion/assets/Main/popups`;
its source skeleton is 4.2.43. Both multi-page textures were compared with source
bytes. No new genuine 3.8.99 fixture was claimed or fabricated.

## F. UI and Viewer handoff

Public imports are from `fnx_spine_forge.bundle`:

- `BundleService.inspect_source(source, mappings=None) -> BundleInspection`.
- `list_bundles(source) -> BundleInspection`.
- `plan_conversion(BundleRequest) -> BundleResult`.
- `convert_bundle(request, *, progress=None, cancellation=None) -> BundleResult`.
- `convert_batch(tuple[BundleRequest, ...]) -> tuple[BundleResult, ...]`.
- `write_report(result, Path)` for a separate atomic sidecar export.

`BundleRequest` carries source, selected path IDs, target, `SkeletonFormat`,
output destination, experimental authorization, `SourceRiskPolicy`,
`RetentionPolicy`, `PackageMode`, and `DependencyMappings`. A `.zip` destination
selects ZIP export; other destinations select folders. Existing destinations
are always rejected; overwrite is not implemented.

`BundleInspection.manifest` supplies filenames/IDs/resource associations without
UI filename matching. Its `states` and `targets` expose admission separately
from qualification, available formats, route availability and source-risk
requirements. `to_dict()` is JSON-serializable. `BundleResult` has `JobStatus`,
`published` and a version-1 report with deterministic JSON serialization.
Failure diagnostic records carry stage, asset ID/path, code, message, technical details,
correction suggestion and publication status. No traceback objects escape.

`ProgressEvent(Stage, asset_id)` reports scanning, discovery, validation,
planning, actual B2 skeleton/atlas hops, verification, packaging, publishing and
terminal outcomes. Repeated per-file/per-hop stages are intentional. A
`CancellationToken` is checked at safe boundaries, including immediately before
publication. Cancellation is a distinct result. Observer failure after
publication cannot turn a valid completed job into a cancellation or undo it.

B4 consumes published asset paths/manifests; it must establish its own runtime
and playback evidence. B5 supplies callbacks/cancellation and adapts these APIs
to its worker infrastructure. No GUI, renderer, viewer controls or playback
implementation was added.

## G. Security and transactions

B1 limits continue to bound members, compressed/uncompressed totals and ratios,
reads and JSON inspection. Sources are never extracted with unrestricted ZIP
extraction. B1 rejects traversal, absolute/drive paths, backslashes, normalized
collisions and symlinks. Output writers apply canonical path/collision checks
again. Source, verification and publication staging directories are isolated.

ZIP publication uses an atomic exclusive hard link on the destination
filesystem. Folder publication uses native no-replace rename (`renamex_np` on
macOS, `renameat2` on Linux), including protection against an occupied empty
directory. Unsupported platforms/filesystems fail closed. Windows folder
publication is not implemented. Only macOS was exercised here; Linux execution
and Windows platform qualification are not claimed.

Every request is atomic across its selected bundles. Separate batch requests
publish independently. Tests cover cancellation before publication, source
immutability, intermediate rejection, corrupted/unsafe inputs, occupied outputs,
simulated publication write errors, staging cleanup, texture collisions and
repeatable failure diagnostics. Corrupted ZIP CRCs and excessive JSON nesting
also return structured job failures instead of leaking parser exceptions. Hard process termination may leave an isolated
staging directory, but never intentionally exposes a partly written final
package. Crash/power-loss durability is not certified.

## H. Executed test evidence

Final commands on the implementation tree:

```sh
.venv/bin/python -m pytest -q
.venv/bin/ruff check src tests
.venv/bin/mypy
.venv/bin/python -m build
.venv/bin/python -m pip install -e .
git diff --check
```

Results: **349 tests passed** (212 frozen baseline tests preserved plus 137 B3
cases), Ruff passed, strict mypy passed over 48 checked files, wheel and sdist
built, editable installation passed. An independent venv installed the wheel
with `pip install --no-deps` and ran the console executable outside the checkout.
Wheel CLI conversion reproduced the real Golden Ingot ZIP bytes and qualified
mode rejection returned exit code 2. `MANIFEST.in` includes fixtures and the
reference harness for reproducible sdist testing.

Installed `bundle inspect/list/plan/convert`, ZIP/folder export, explicit bundle
selection, source-risk rejection, qualification rejection, binary capability
listing and experimental binary JSON/binary outputs were executed. Exact smoke
arguments and exit codes are in the evidence JSON. Full command logs and
returned-artifact reports are under `dist/b3-qualification/`.

Binary tests include every byte truncation of the independent vector, malformed
varints, collection/string/file limits, invalid parents/flags/UTF-8, nonfinite
floats, unsupported records/versions, direction independence, independent wire
layout, round trips and actual B2 bundle integration. Synthetic hierarchy
fixtures are identified as such. Failure injection tests concern filesystem
behavior; converter success evidence comes from real B2 execution.

The existing B2 `runtime-smoke` command independently loaded the converted Golden
Ingot JSON/atlas using official `spine-core@4.2.43` and evaluated **8 samples**
across `idle` and `winning`: parsing and AnimationState evaluation passed.
Visual equivalence was **not assessed**. This isolated smoke does not populate
conversion-job runtime verification fields or certify the migration route.

## I. Remaining limitations and acceptance

Bundle workflow/API/CLI/security gates pass for the documented restricted
contract. Default qualification remains restrictive; no atlas/animation semantic
qualification or visual fidelity is inferred from successful structural output.
Viewer mode is a portable resource layout, not a promise that every third-party
viewer accepts every archive. Ancillary audio/other formats are not inferred as
runtime dependencies; callers must choose retention and review exclusions.

Overall B3 stays open for full binary records, a minimum independently
semantically qualified target, matching authenticated export fixtures and
broader binary semantic comparison. The hierarchy codec is genuine but remains
experimental/unqualified. Additional exact binary versions are unsupported.
No real animation binary conversion is advertised. B4/B5 implementation remains
outside scope. Binary completion will require additional codec implementation
and qualification, not merely switching registry flags.

## J. Git checkpoint

Implementation checkpoint: `ee0a4885d1a571bac75b3b31fe38657b7a08b27a`.
Final implementation/hardening commit: `ff0b9ca42ef2b74ae33880dfbe6ca3a9845d40aa`.

Branch: `codex/b3-bundle-backend`. The original frozen B2 branch was preserved.
Implementation was committed separately from this report/evidence checkpoint.
The report commit's own SHA cannot be embedded in its content without changing
that SHA; obtain it with `git log -1 --format=%H -- docs/B3_REPORT.md` (also given
in the final handoff). The final tracked working tree is clean; ignored
builds, qualification packages and local evidence remain available under `dist/`.
No tag, deployment, binary qualification freeze or overall B3 closure is claimed.
