# Headless inspection and conversion architecture

`AssetSource` is the bounded, read-only folder/ZIP adapter. `InspectionService`
sequences discovery, typed classification, skeleton/atlas parsing, dependency
resolution, and immutable manifest construction. ZIP contents are read in place.
`SourceLimits` and `InspectionConfig` configure resource limits.

`json_types.py` owns the recursive JSON transport types and checked decoder.
Decoder output enters as `object`, then is reconstructed as validated JSON.
Duplicate keys, non-finite values, unsupported Python values and excessive
nesting reject. Inspection metadata is immutable JSON data, not arbitrary Python
objects; manifest serialization has explicit typed field ownership.

`conversion/registry.py` owns exact directed implementation edges, their writer
kinds, and operational patch policies. Each writer admits its edge through
`require_route()`. Historical version writers are supported conversion behavior;
they are distinct from compatibility wrappers.

`conversion/document.py`, `errors.py`, `schema.py` and `curves.py` own checked
mutable access, migration failures, shared schema operations and channel-aware
curve mathematics respectively. Route writers consume these owners directly;
shared functionality is not imported from a particular migration implementation.
`semantic.py` builds typed semantic records before source feature classification.

`conversion/qualification_evidence.json` contains the finite executed evidence
inventory, fixture identities, provenance and SHA-256 values. Its loader rejects
unknown fields, invalid paths/features, incomplete evidence and unsupported
certification claims. Records are immutable and the registry never derives a
composed qualification from constituent edges.

`QualificationService` is the qualification policy owner. Planner, skeleton
converter, executor, atlas converter and asset-set converter consume it.
`ConversionResult.qualification` and `AssetSetResult.qualification` expose the
same immutable `QualificationResult` used by planning. CLI JSON serializes it
under the top-level `qualification` field. `None` means admission failed before
a qualification result was available; it never denotes success.

Default execution requires semantic qualification. Explicit experimental
structural execution never asserts qualification. Skeleton execution captures
source bytes once. Asset-set qualification uses the staged source snapshot and
selected path; dependencies are reinspected at every stage and complete outputs
are published atomically. The known 3.8.75 export-risk policy remains independent.

Runtime and visual verification are separate evidence categories. Structural
inspection, schema conversion, numerical samples and engineering qualification
do not establish runtime or visual certification. The restricted support matrix
and current release evidence are in [B2_REPORT.md](B2_REPORT.md).

All production modules and the independent numerical test reader are checked
with strict mypy plus explicit/implicit `Any` rejection. No type suppressions or
unchecked casts are retained. There are no compatibility forwarders for removed
APIs or modules.


## B3 canonical owners (0.2)

- `source.py`: bounded folders/ZIPs/explicit selections and canonical member paths.
  Selection limits apply to selected files; unrelated siblings are not scanned.
- `detection.py` and `versions.py`: one typed JSON skeleton recognition operation
  and version syntax/family authority. Numeric/alternate version fields are not
  coerced into an export version.
- `parsers.py`: sole atlas grammar and region/page ownership, including indexed
  regions. B2 consumes its ownership records directly, without a second scan.
- `bundle_models.py`: immutable/slotted request, report, target and operation
  contracts. Operational state is typed; JSON is produced only at serialization.
- `progress.py`: one typed phase/event vocabulary shared by B2 and B3, with
  cooperative thread-safe cancellation.
- `bundle.py`: B1/B2 orchestration and selected-bundle transactions. Qualification
  still belongs to B2.
- `packaging.py`: package construction, measured texture dependencies, deterministic
  archives, final validation and publication receipts.
- `atomic_io.py`: shared staging/path checks and native exclusive file/directory
  publication. CLI and bundle workflows use this owner; replacement is unsupported.
- `texture.py`: configured, streaming PNG structural validation. Image bytes are
  immutable artifacts, not rendered approximations.
- `binary.py`: exact registered codec evidence, typed capability features/errors
  and independent decode/encode operations. Capability records cannot be forged
  into a different version or wider qualification through codec construction.

Retired `registry.py`, root `errors.py`, and `protocols.py` have no forwarders.
`conversion/registry.py` is the only migration graph. Recognition does not expose
placeholder family-level reader/writer capability fields. Fixed binary/PNG/ZIP
wire constants are explicitly distinct from configured operational limits.

Every new public contract is checked by `tests/b3_contracts.py`. Installed clients
receive PEP 561 type information. There are no `Any` suppressions or missing-import
silencers. Checked FFI/unpack narrowing is limited to native integer/float formats.
