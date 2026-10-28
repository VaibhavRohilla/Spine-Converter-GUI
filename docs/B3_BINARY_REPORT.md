# B3 animated binary implementation — 2026-10-27

> Superseded for current status by the [2026-10-28 decoder qualification](B3_DECODER_QUALIFICATION.md).
> Exact 4.2.22 now has experimental authentic decoder evidence; release remains blocked.
> The following records the earlier 4.2.43-only checkpoint.

**Decision: B3 PARTIAL — BINARY UNQUALIFIED. No B3 freeze.**

This change replaces the hierarchy-only implementation limitation with a useful
experimental animated codec. It does **not** complete the requested production
qualification. In particular, authentic animated decoder references matching
an admitted export schema are missing, and the required constraint-heavy
acceptance coverage remains incomplete. Successful encoder comparisons and
self-roundtrips are not substituted for those gates.

## Architecture and exact scope

Starting revision: `b36ad14648c4fd1fef171c34a04ae97b6fd3e35c`; clean tree.
The existing bounded primitives, exact-version registry, B1 inspection, B2
semantic records, bundle discovery, packaging transactions, API and CLI are
reused. `binary_animation.py` implements the additional version-specific tail
records. No JSON/atlas migration engine, viewer adapter, B2 qualification record,
or B4 binary trust-policy file was changed. No B5 work was performed.

The only admitted export version remains **4.2.43**. This is distinct from
`@esotericsoftware/spine-core@4.2.43`, the separately pinned runtime package.
No 4.2.22 or general 4.2-family admission is implied. The authentic official
Spineboy binary already in B4 declares **4.2.22**, and fails closed here without
rewriting its header. Its immutable checksum and rejection are recorded in the
[evidence](evidence/B3_binary/qualification.json).

Wire implementation references are the installed exact-version official
`SkeletonBinary.js` and `SkeletonJson.js`; the binary reader source SHA-256 is
`83efaec2af4cbc7538f83ca436f921741c027f26f3dd44c98fada3e5139ba250`.
The generic [binary format](https://esotericsoftware.com/spine-binary-format),
[JSON format](https://esotericsoftware.com/spine-json-format), and
[versioning documentation](https://esotericsoftware.com/spine-versioning) are
context, not substitutes for the pinned implementation.

| Construct | Implemented | Independent evidence in this change |
|---|---|---|
| Header, bones, hierarchy, setup, inheritance, explicit nonessential metadata | Yes | Existing hierarchy wire/layout tests preserved |
| Slots, setup RGBA/dark RGB, blend, skin names | Yes | Specified-fixture official reader/pose comparisons; simple independent wire vector |
| Region attachments | Yes | Encoder poses/world vertices; independent simple decoder vector |
| Unweighted and weighted meshes | Yes | Weighted quadrilateral encoder world vertices; unweighted path not independently qualified |
| Linked meshes, named skins, timeline inheritance | Yes | Alternate skin with inherited deform encoder evaluation |
| Rotate, translate, scale, shear and separate-axis forms | Yes | Combined rotate/translate/scale/shear sampled; separate-axis forms unqualified |
| Linear, stepped, per-channel Bézier curves | Yes | Bone and deform sampled; RGBA Bézier implemented but not independently exercised |
| Slot attachment and RGBA timelines | Yes | RGBA sampled; attachment timeline implemented but not independently exercised |
| Deform timelines | Meshes only | Weighted and inherited linked deform encoder sampling |
| Draw order | Yes | Positive/negative offsets and reset sampled |
| IK setup | One/two bones, no skin requirement | One-bone animated-target encoder fixture only |
| Other attachments | No | Typed rejection |
| Other constraints, skin constraint lists, constraint timelines | No | Typed rejection |
| Physics, events/payloads, sequences, inherit timelines, other slot color categories | No | Typed rejection |

Bounding box, clipping, path and point attachments are not implemented. Transform
and path constraints, physics, IK-parameter animation and event ordering are not
qualified or advertised. Exact nonessential metadata remains deliberately
strict: implicit bone editor metadata is not inferred; incompatible hashes are
rejected, never truncated. Mesh nonessential dimensions/edges require explicit
nonessential export metadata. Source JSON objects are not mutated.

The central capability record exposes formats, feature lists, restrictions,
experimental status and separate decoder/encoder evidence. Both qualification
booleans remain false. Qualified/default actions remain blocked. Executable
cross-version steps do not promote composed routes or widen B2-RC1.

## Independent runtime evidence

The new test-only `scripts/qualify_binary42.mjs` loads original JSON and FNX
binary separately with the official readers, builds separate `Skeleton` and
`AnimationState` instances, and compares setup and animation poses. It checks
bone world matrices, slot color/dark color/attachment, region and mesh world
vertices, deform, draw order, skins, animation identity/duration and event lists.
Event lists are empty in these fixtures; they do not qualify event support.

The driver explicitly selects local fixtures. Each reader child has a 30-second
wall-clock timeout, a 256 MiB V8 heap limit and bounded input files. This is a
trusted local qualification utility, not an OS security sandbox or upload
endpoint. It never writes the B4 approval manifest. Tests confirm that generated
binaries still fail B4 production admission.

| Independently specified fixture | Samples | Numeric comparisons | Maximum absolute error |
|---|---:|---:|---:|
| Animated region | 42 | 1,135 | 7.0042e-7 |
| Weighted mesh, linked skin, deform, draw order | 84 | 3,934 | 7.2148e-7 |
| One-bone IK with animated target | 42 | 1,387 | 2.6116e-7 |
| Total | 168 | 6,456 | 7.2148e-7 |

All comparisons passed `3e-4 + 2e-6 * abs(reference)` tolerance; the focused tests
also require maximum error below `1e-5` for these fixtures. There are 41 animation
samples per skin plus setup. Fresh-state samples are appropriate for this
non-physics profile; no physics or long-running lifecycle result is inferred.
Runtime reader, fixture, atlas, generated-output and implementation hashes are
in `evidence/B3_binary/qualification.json`. Generated binaries and decoded JSON
are retained beside that record.

The decoder has a new independent hand-authored region/rotate wire test.
Mesh/deform/IK decoding currently has self-roundtrip, invariant and malformed
input evidence, **not independent authentic decoder qualification**. Existing
B4 loading of authentic binaries is not evidence for FNX decoding or encoding.

## Bundle/API/CLI and packaging

The existing `BundleService` automatically consumes the extended registered
codec through its existing binary-to-JSON and JSON-to-binary paths. No duplicate
service or CLI decision logic was added. B1 reinspection decodes the resulting
binary and validates dependencies before atomic publication. This establishes
structural package validity only; runtime qualification is not assigned to
arbitrary user-generated experimental packages.

Focused integration verifies source immutability, byte-identical PNG reuse,
complete ZIP contents, binary ZIP to JSON folder/ZIP conversion, deterministic
ZIP bytes, overwrite rejection, unsupported-content rollback, and default-mode
qualification rejection. Existing multi-page atlas, path, source-risk and
transaction tests remain in the full regression suite.

Example (experimental authorization is mandatory):

```sh
spine-forge binary-capabilities
spine-forge bundle inspect /path/to/source
spine-forge bundle convert --input /path/to/source --target 4.2.43 \
  --container zip --skeleton-format binary --output /path/to/new.zip \
  --experimental-structural
spine-forge bundle convert --input /path/to/new.zip --target 4.2.43 \
  --container folder --output /path/to/new-json --experimental-structural
```

An isolated installed-wheel CLI executed capabilities, inspection, animated
binary ZIP export, JSON folder export and default-mode rejection from `/tmp`.
The generated package's binary also passed the official runtime comparison;
PNG identity and source hashes were checked. Exact commands and results are in
[evidence/B3_binary/installed-wheel.json](evidence/B3_binary/installed-wheel.json).

## Safety and regression

Limits cover file bytes, string bytes, collection counts, aggregate declared
records, input tree depth/complexity, finite float32, references and enums.
Additional checks cover mesh vertex/influence/triangle counts and bounds,
weight range/sums, linked parent existence/type/cycles, deform ranges, strict
float32 frame ordering, curve dimensions/counts, duplicate records, draw-order
permutations and terminal curves. Unknown data is rejected, never skipped.
Exceptions use structured binary diagnostic codes. B2 semantic validation is
reused; binary-only editor visibility is checked by the codec and excluded only
from the B2 runtime-semantic validation projection, not from the returned data.

Executed full gate: `bash scripts/verify_b4.sh` — **489 Python tests and 146
viewer/browser tests passed**, Ruff passed, strict mypy passed (60 files), Python
wheel/sdist and TypeScript builds passed, TypeScript typecheck and lint passed,
`git diff --check` passed. The script executes all four separately requested
Python validation commands. The initial sandboxed run failed solely because
macOS denied a loopback-server bind; the authorized external run passed.
No 30-minute soak was repeated: no viewer resource ownership code changed.

The 24 new tests include all-byte truncations of three animated binaries,
single-byte mutation sweeps, malformed features/references/geometry/curves,
float32 time collapse, official-reader subprocesses, bundle transactions and
unchanged B4 denial. The 465-test Python baseline remains intact.

## Freeze gates and publication

B3 remains open. The required authentic decoder evidence, complete independent
feature coverage, constraint-heavy acceptance case, and production qualified
binary packaging gate are not met. No missing evidence is reclassified as a
supported capability. The implementation is useful experimental progress, not
completion of the user's B3 final-binary mission.

The verified implementation/report are committed together; resolve their exact
publication revision with `git log -1 --format=%H -- docs/B3_BINARY_REPORT.md`.
The final response records the exact commit SHA and post-commit working-tree
state. B1, B2-RC1, and the B4 restricted checkpoint retain their prior status.
