# B3 production hardening qualification — package 0.2.0

Decision: **B3 PARTIAL — BUNDLE SUBSYSTEM FROZEN**. Overall B3 remains open.
This checkpoint strengthens the working JSON bundle backend. It does not supply
the missing authenticated binary fixtures or full binary animation codec and
therefore does not satisfy the complete B3 binary acceptance criteria. No
production, runtime or visual certification is inferred from local green gates.

## A. Architecture audit

B1 `AssetSource`, `InspectionService`, manifests, dependency matching and version
recognition remain the canonical inspection infrastructure. B2
`SkeletonConverter`, `AtlasConverter`, `MigrationExecutor`, `AssetSetConverter`,
`ConversionPlanner` and `QualificationService` remain the conversion owners.
No alternate migration implementation was added.

New explicit owners:

- `bundle_models.py`: immutable typed requests, inspection, outcomes and report.
- `progress.py`: shared stage enum, progress events and thread-safe cancellation.
- `packaging.py`: staged package validation and deterministic ZIP/folder export.
- `atomic_io.py`: validated staging and exclusive publication primitives.

`bundle.py` coordinates those owners. The obsolete root `registry.py` graph,
unused root `errors.py` and unused `protocols.py` were deleted. The active
`conversion/registry.py` and `conversion/errors.py` are retained. Historical
version-specific migration code is necessary conversion behavior, not a legacy
compatibility path. Old imports, dict-access adapters and old publisher wrappers
were removed, with direct callers migrated to the canonical interfaces.

## B. Discovery and dependencies

ZIP, folder and explicit `tuple[Path, ...]` selections use B1. Explicit selections
index only selected files rather than scanning an entire shared parent. Paths
and IDs remain canonical relative paths. Shared atlases, nested bundles,
ambiguity and manual atlas/texture overrides retain B1's evidence-based behavior.
Filename similarity cannot resolve equally plausible atlases silently.

Atlas parsing now owns region-to-page assignments for both B1 and B2. A region
whose name ends in `.png` is distinguished using its attribute vocabulary.
Indexed duplicates require distinct explicit nonnegative indices; conflicting
indices are rejected even in standalone experimental atlas conversion. Source
version recognition also has one implementation; `skeleton.spine` must be an
actual version string. The undocumented `skeleton.version` fallback and numeric
coercion were removed.

## C. Conversion and typed contracts

`BundleService.inspect_source`, `list_bundles`, `plan_conversion`,
`convert_bundle` and `convert_batch` remain the shared orchestration API.
`BundleRequest` uses `PackageContainer`, `SkeletonFormat`, `PackageMode`,
`RetentionPolicy`, `SourceRiskPolicy` and `DependencyMappings`. The output
container is explicit, not guessed from a destination suffix. CLI conversion
requires `--container zip|folder`. ZIP destinations must end in `.zip`.

`BundleResult.report` is a `BundleReport`, with typed `BundleOutcome`,
`QualificationResult`, `BinaryOperation`, diagnostics and verification states.
Reports are immutable snapshots; JSON dictionaries exist at serialization
boundaries through `to_dict()`. Inspection and report schemas are **2**. This is
an intentional breaking API in package **0.2.0**, without compatibility adapters.

B2's seven direct restricted hierarchy/setup qualification records remain the
only applicable semantic evidence. Unsupported feature sets reject in default
mode. Experimental structural authorization remains explicit and separate from
3.8.75 source export-risk authorization. Source provenance is not rewritten.
Execution, structure, semantic qualification, runtime, visual verification and
actual binary operation execution are separate fields. An unexecuted encoder
is not reported as passed; an encoder failure is attached to its bundle.

Publication is atomic for one request, including all selected bundles. A batch
contains independent per-request publications; an earlier successful request is
not rolled back when another request fails. Planning does not publish files.

## D. Binary support and verification gap

Only exact **4.2.43** has implemented decoding and encoding, restricted to
hierarchy/setup transforms, inheritance and explicit supported editor metadata.
Slots, attachments, constraints, animation timelines, mesh, deform and events
are unsupported. Both operations require experimental authorization. Other
exact binary versions reject. A decoder does not imply an encoder capability.

Capability records cannot be forged to enable operations or qualifications.
Nonessential output requires explicit FPS and each bone's color/visibility;
ambiguous metadata defaults are not silently fabricated. Count, byte, string,
varint, finite-number, hierarchy-index, trailing-data and truncation checks are
tested. Parent/name lookup uses bounded linear indexing.

The independent hand-authored wire fixture is not an authentic Spine export.
Both its decoding expectations and encoder primitive layout are asserted
independently. The current encoder output was additionally interpreted by the
official `@esotericsoftware/spine-core@4.2.43` reader through
`scripts/verify_binary_reference.mjs`, comparing expected hierarchy values.
That is a restricted parser observation, not full binary semantic/runtime
qualification. Matching authenticated exporter fixtures and complete binary
records remain missing. Registry qualification was not promoted.

## E. Packaging and real asset evidence

Viewer packages contain selected assets without embedded audit reports. Audit
packages contain a prepublication report snapshot. A requested final sidecar is
published independently without overwriting an existing file. Failure to write
a sidecar does not invalidate an already published package.

ZIP ordering, timestamps and metadata are deterministic. Generated ZIPs are
reopened, CRC checked, compared against staged member bytes and reinspected by
B1 before publication. Folder output uses the same validation. Texture bytes
are preserved. The streaming PNG validator checks CRC, critical chunks,
palette/order, bounded DEFLATE, exact scanline lengths, filters and Adam7 pass
structure. Measured PNG dimensions must match declared atlas page sizes. No
image is cropped, resized or re-encoded.

Installed-wheel tests converted authentic Golden Ingot 3.8.75 to 4.2.43 ZIP
and folder with separate experimental/risk authorization, compared output
member bytes, rejected default qualification and occupied destinations, and
selected one skeleton from a shared-atlas multi-bundle source. Two independent
ZIP conversions produced identical bytes. The real `merged_multi` 4.2.43 asset
was converted experimentally to 4.3.13 with both PNG pages preserved exactly.
Machine-readable evidence includes their texture SHA-256 checksums.

## F. B4/B5 handoff

Import orchestration from `fnx_spine_forge.bundle`; domain contracts from
`fnx_spine_forge.bundle_models`; events/cancellation from
`fnx_spine_forge.progress`. `TargetInspection` exposes typed qualification,
route, formats and risk. `DependencyMappings` supports stable path-based atlas
and texture corrections followed by reinspection. States distinguish READY,
NEEDS_SELECTION, INCOMPLETE, UNSUPPORTED and INVALID from target qualification.

Callers consume named report fields, not raw JSON. Progress stages are shared
with the actual B2 asset-set stages. `CancellationToken` uses `threading.Event`
and is checked at safe boundaries before publication. B5 can schedule these
services on its own worker without backend GUI dependencies. B4 can consume
published paths/manifests and verification states; loading/playback and visual
comparison are still B4 responsibilities. No rendering or GUI was implemented.

`py.typed` ships in the wheel. `tests/b3_contracts.py` is checked under strict
mypy. A second strict client outside the checkout successfully imports the
installed wheel's types; negative-client tests reject dict-style report access
and string authorization/format arguments.

## G. Security and publication

`InspectionConfig` owns source/binary limits; `PackageSettings` owns compression
and `TextureLimits`. Archive raw-byte and metadata-read limits apply before
stdlib ZIP indexing allocates the central directory. Member/count/compressed,
uncompressed, ratio and read limits remain enforced. Raw NUL-containing ZIP
names are rejected before stdlib's filename truncation can hide them.

Shared path validation rejects traversal, symlinks, Unicode/case collisions,
file/directory prefix collisions, Windows devices, alternate streams, reserved
characters and trailing dots/spaces. Staging validates all members first.
Standalone CLI writes are exclusive as well as bundle publication.

Files use exclusive hard-link publication; folders use native no-replace
rename (Darwin/Linux), or Windows' no-replace `os.rename` contract. Unsupported
native primitives fail closed. Darwin is exercised locally; Windows/Linux
execution remains a platform verification gap. Cleanup errors after the
publication commit point are warnings, never false reports of an unpublished
artifact. Cancellation/failure before that point leaves no final package.
Filesystem race adversaries changing source directories concurrently and
power-loss durability are not certified by these tests.

## H. Executed quality gates

All commands executed from the repository unless otherwise stated:

```
.venv/bin/python -m pip install -e .
.venv/bin/python -m pytest -q
.venv/bin/ruff check src tests
.venv/bin/mypy
.venv/bin/python -m build
.venv/bin/python -m venv /tmp/fnx-b3-hardening-wheel
/tmp/fnx-b3-hardening-wheel/bin/python -m pip install --no-deps --force-reinstall dist/fnx_spine_forge-0.2.0-py3-none-any.whl
node scripts/verify_binary_reference.mjs /tmp/fnx-b3-reference/package /tmp/fnx-b3-current-encoded.skel tests/fixtures/binary/hierarchy_4_2_43.expected.json
git diff --check
```

Results: **382 tests passed**; Ruff passed; strict mypy passed for **50 source
files**; wheel and sdist built; editable and isolated-wheel installation passed;
installed CLI/API/package/type checks passed. Full source `.py` bytes were
compared against wheel members; `py.typed` is present and deleted modules are
absent. Existing B1/B2 behavior tests remain, with retired API callers migrated
rather than preserving compatibility shims. No tests were weakened to admit
unsupported conversions.

The isolated wheel exercised inspect, conversion, selection, qualification,
overwrite rejection and ZIP/folder parity from `/tmp`. External strict mypy
used `--python-executable /tmp/fnx-b3-hardening-wheel/bin/python`. Local logs and
artifacts are under ignored `dist/b3-hardening-qualification/`. Committed
[evidence](evidence/B3_hardening_qualification.json) records the results and
restricted binary reference observation. Runtime and visual verification are
not claimed for the converted animation bundles.

## I. Remaining limitations

Full B3 binary acceptance remains incomplete; no binary production target is
semantically qualified. Structurally successful advanced JSON migrations remain
experimental under B2. Third-party viewers may have different archive contracts;
portable layout is not universal runtime certification. Optional unknown assets
must be reviewed through explicit retention policy and exclusion reporting.
Native publication branches need Windows/Linux execution evidence. These are
explicit limits, not a 10/10 product certification.

## J. Git

Branch: `codex/b3-production-hardening`. The prior B3 branch and its checkpoint
`784b4e450b27f7dca03b17e799102222f4d72f36` remain preserved. Implementation and
report/evidence are committed separately. Implementation commit: `659dbe4656e93ba8d8c93769a7744fec4aae28ae`. The final report commit is resolved with
`git log -1 --format=%H -- docs/B3_HARDENING_REPORT.md` and supplied in the final
handoff; embedding its own SHA would change it. No deployment or full B3 freeze
is claimed.

Final tracked working tree is clean after the separate report/evidence commit;
ignored builds and local qualification artifacts are retained under `dist/`.
